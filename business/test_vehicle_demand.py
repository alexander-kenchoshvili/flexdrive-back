import uuid
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import DatabaseError
from django.urls import reverse
from rest_framework.test import APITestCase

from catalog.models import VehicleMake, VehicleModel
from .authentication import BUSINESS_COOKIE, SESSION_KIND, session_store
from .models import VehicleInterest
from .reports import ReportPeriod
from .vehicle_demand import TOKEN_SALT, build_vehicle_demand, lookup_interest_token


class VehicleDemandTests(APITestCase):
    def setUp(self):
        self.make = VehicleMake.objects.create(name="Subaru", slug="subaru")
        self.model = VehicleModel.objects.create(make=self.make, name="Forester", slug="forester")
        self.payload = {"session_id": str(uuid.uuid4()), "analytics_consent": True,
                        "make": "subaru", "model": "forester", "year": 2019, "variant": "sport", "result_count": 4}
        self.collect = reverse("catalog-vehicle-interest")
        self.report = reverse("business:vehicle-demand")

    def post(self, **changes):
        return self.client.post(self.collect, {**self.payload, **changes}, format="json")

    def test_no_consent_invalid_fields_and_unknown_vehicle_never_store_data(self):
        self.assertEqual(self.post(analytics_consent=False).status_code, 204)
        for change in ({"vin": "private-input"}, {"make": "missing"}, {"model": "missing"}, {"lookup_token": "forged"}, {"year": 9999}):
            self.assertEqual(self.post(**change).status_code, 400)
        self.assertEqual(VehicleInterest.objects.count(), 0)

    def test_repeated_pages_and_vin_plus_catalog_are_deduplicated_and_flags_monotonic(self):
        self.assertEqual(self.post().status_code, 204)
        self.assertEqual(self.post(result_count=0).status_code, 204)
        token = lookup_interest_token({"status": "matched", "vehicle": {"make": "Subaru", "model": "Forester", "year": 2019, "trim": "Sport"}})
        self.assertEqual(self.post(lookup_token=token).status_code, 204)
        self.assertEqual(self.post(result_count=5).status_code, 204)
        self.assertEqual(VehicleInterest.objects.count(), 1)
        row = VehicleInterest.objects.get()
        self.assertTrue(row.via_vin)
        self.assertTrue(row.had_no_results)
        self.assertNotEqual(row.session_digest, self.payload["session_id"])
        self.assertNotIn("vin", {field.name for field in row._meta.fields})
        report = build_vehicle_demand(ReportPeriod(row.day, row.day))
        self.assertEqual(report["summary"]["visits"], 1)
        self.assertEqual(report["rows"][0]["visits"], 1)
        self.assertIn("Subaru Forester", report["insights"][0])

    def test_signed_unmatched_vehicle_is_counted_without_guessing_catalog_data(self):
        vehicle = {"make": "TOYOTA", "model": "Camry", "year": 2012, "trim": "Hybrid"}
        token = lookup_interest_token({"status": "not_in_catalog", "vehicle": vehicle})
        payload = signing.loads(token, salt=TOKEN_SALT)
        self.assertEqual(set(payload), {"make", "model", "year", "variant", "outcome"})
        self.assertEqual(self.post(lookup_token=token).status_code, 204)
        row = VehicleInterest.objects.get()
        self.assertTrue(row.missing_catalog)
        self.assertEqual(row.variant, "hybrid")
        self.assertEqual(row.make, "TOYOTA")

    def test_staff_collection_is_ignored_and_report_requires_separate_business_access(self):
        self.assertEqual(self.client.get(self.report).status_code, 401)
        user = get_user_model().objects.create_superuser("demand-owner", "owner@example.test", "safe-test-password")
        self.client.force_authenticate(user)
        self.assertEqual(self.post().status_code, 204)
        self.assertFalse(VehicleInterest.objects.exists())
        self.client.force_authenticate(user=None)
        session = session_store()
        session.update({"kind": SESSION_KIND, "user_id": user.pk, "auth_hash": user.get_session_auth_hash()})
        session.save()
        self.client.cookies[BUSINESS_COOKIE] = session.session_key
        response = self.client.get(self.report)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["visits"], 0)
        self.assertIn("ჯერ არ დაგროვებულა", response.data["insights"][0])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(self.client.get(self.report, {"start": "bad", "end": "bad"}).status_code, 400)

    def test_rows_are_ranked_by_distinct_sessions_and_versions_do_not_inflate_model_year(self):
        self.post()
        self.post(variant="limited")
        self.post(session_id=str(uuid.uuid4()))
        self.post(session_id=str(uuid.uuid4()), year=2018)
        row = VehicleInterest.objects.first()
        result = build_vehicle_demand(ReportPeriod(row.day, row.day))
        self.assertEqual(result["rows"][0]["year"], 2019)
        self.assertEqual(result["rows"][0]["visits"], 2)
        self.assertEqual(result["summary"]["visits"], 3)
        self.assertEqual(result["row_count"], 2)
        empty = build_vehicle_demand(ReportPeriod(date(2000, 1, 1), date(2000, 1, 2)))
        self.assertEqual(empty["rows"], [])

    def test_storage_failure_is_explicit_and_does_not_change_the_vin_lookup(self):
        with patch("catalog.interest_views.record_interest", side_effect=DatabaseError):
            result = self.post()
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result["Cache-Control"], "private, no-store")
        lookup = {"status": "not_in_catalog", "vehicle": {"make": "Toyota", "model": "Camry", "year": 2012}}
        with patch("catalog.vin_views.decode_vehicle", return_value={"status": "decoded", "vehicle": lookup["vehicle"]}), patch("catalog.vin_views.resolve_vehicle", return_value=lookup):
            result = self.client.post(reverse("catalog-vehicle-vin"), {"vin": "1HGCM82633A004352"}, format="json")
            self.assertEqual(result.status_code, 200)
            self.assertIn("interest_token", result.data)
