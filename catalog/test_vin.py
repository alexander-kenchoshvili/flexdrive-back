import hashlib
import json
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache, caches
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from common.throttling import CachedScopedRateThrottle
from .models import Category, Product, ProductFitment, ProductStatus, VehicleEngine, VehicleMake, VehicleModel
from .vin import _read_provider, decode_vehicle, normalize_vin, resolve_vehicle


# Public, widely documented example; never a customer's VIN.
VIN = "1HGCM82633A004352"
VEHICLE = {"make": "HONDA", "model": "Accord", "year": 2003}


def provider_response(**overrides):
    row = {"VIN": VIN, "Make": "HONDA", "Model": "Accord", "ModelYear": "2003", "ErrorCode": "0", **overrides}
    response = MagicMock()
    response.status_code = 200
    response.iter_content.return_value = [json.dumps({"Results": [row]}).encode()]
    response.__enter__.return_value = response
    return response


@override_settings(CACHES={
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "vin-tests"},
    "throttling": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "vin-throttle-tests"},
})
class VinTests(APITestCase):
    def setUp(self):
        cache.clear()
        caches["throttling"].clear()
        CachedScopedRateThrottle.cache.clear()
        self.url = reverse("catalog-vehicle-vin")
        self.make = VehicleMake.objects.create(name="Honda", slug="honda")
        self.model = VehicleModel.objects.create(make=self.make, name="Accord", slug="accord")
        self.category = Category.objects.create(name="Hoods", slug="hoods")
        self.product = Product.objects.create(
            name="კაპოტი", slug="vin-test-hood", sku="VIN-HOOD", internal_sku="FD-01-0001",
            category=self.category, price="100", stock_qty=20, status=ProductStatus.PUBLISHED,
        )
        self.fitment = ProductFitment.objects.create(product=self.product, vehicle_model=self.model, year_from=2003, year_to=2007)

    def post(self, value=VIN):
        return self.client.post(self.url, {"vin": value}, format="json", REMOTE_ADDR="10.67.0.1")

    def test_invalid_input_never_reaches_provider_and_is_not_echoed(self):
        with patch("catalog.vin.requests.get") as get:
            for value in (None, [], 12, "1" * 16, "I" * 17, "Q" * 17, "O" * 17, "АHGCM82633A004352", "http://localhost/x", VIN + "?x=1"):
                with self.subTest(value=value):
                    result = self.post(value)
                    self.assertEqual(result.status_code, 400)
                    self.assertEqual(result.data, {"status": "invalid_vin"})
            get.assert_not_called()
        self.assertEqual(normalize_vin("  " + VIN.lower() + "  "), VIN)
        self.assertIsNone(normalize_vin("ßHGCM82633A004352"))

    @patch("catalog.vin.requests.get")
    def test_anonymous_match_and_followup_part_search(self, get):
        get.return_value = provider_response()
        response = self.post(VIN.lower())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["filters"], {"make": "honda", "model": "accord", "year": "2003", "variant": "unspecified"})
        self.assertNotIn(VIN, json.dumps(response.data))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(self.client.get(self.url).status_code, 405)
        result = self.client.get(reverse("catalog-product-list"), {**response.data["filters"], "q": "კაპოტი"})
        self.assertEqual(result.status_code, 200)
        self.assertIn(self.product.pk, {p["id"] for p in result.data["results"]})
        args, options = get.call_args
        self.assertTrue(args[0].startswith("https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"))
        self.assertEqual(options["params"], {"format": "json"})
        self.assertFalse(options["allow_redirects"])
        self.assertEqual(options["timeout"], (3.05, 6))

    @patch("catalog.vin.requests.get")
    def test_cached_identity_is_reused_but_taxonomy_and_coverage_are_live(self, get):
        get.return_value = provider_response()
        self.assertEqual(self.post().data["status"], "matched")
        self.assertEqual(self.post().data["status"], "matched")
        get.assert_called_once()
        key = "catalog:vin:v2:" + hashlib.sha256(VIN.encode()).hexdigest()
        self.assertNotIn(VIN, key)
        self.assertNotIn(VIN, json.dumps(cache.get(key)))
        self.product.status = ProductStatus.DRAFT
        self.product.save(update_fields=["status"])
        self.assertEqual(self.post().data["status"], "no_coverage")
        self.model.is_active = False
        self.model.save(update_fields=["is_active"])
        self.assertEqual(self.post().data["status"], "not_in_catalog")
        get.assert_called_once()

    def test_exact_punctuation_matching_and_no_fuzzy_guess(self):
        self.model.name, self.model.slug = "CRV", "crv"
        self.model.save()
        self.assertEqual(resolve_vehicle({**VEHICLE, "model": "CR-V"})["status"], "matched")
        self.assertEqual(resolve_vehicle({**VEHICLE, "model": "CR-V Hybrid"})["status"], "not_in_catalog")
        VehicleModel.objects.create(make=self.make, name="CR-V", slug="cr-v")
        self.assertEqual(resolve_vehicle({**VEHICLE, "model": "CR-V"})["status"], "not_in_catalog")

    def test_manufacturer_alias_is_scoped_and_no_cross_market_model_alias(self):
        self.make.name, self.make.slug = "Mercedes", "mercedes"
        self.make.save()
        self.assertEqual(resolve_vehicle({**VEHICLE, "make": "MERCEDES-BENZ"})["status"], "matched")
        self.assertEqual(resolve_vehicle({**VEHICLE, "make": "SUBARU", "model": "XV"})["status"], "not_in_catalog")

    def test_year_publication_category_and_active_engine_required_but_stock_not_required(self):
        self.assertEqual(resolve_vehicle({**VEHICLE, "year": 2002})["status"], "no_coverage")
        self.product.stock_qty = 0
        self.product.save(update_fields=["stock_qty"])
        self.assertEqual(resolve_vehicle(VEHICLE)["status"], "matched")
        engine = VehicleEngine.objects.create(model=self.model, name="2.4", slug="24", is_active=False)
        self.fitment.engine = engine
        self.fitment.save()
        self.assertEqual(resolve_vehicle(VEHICLE)["status"], "no_coverage")
        self.fitment.engine = None
        self.fitment.save()
        self.category.is_active = False
        self.category.save()
        self.assertEqual(resolve_vehicle(VEHICLE)["status"], "no_coverage")

    @patch("catalog.vin.requests.get")
    def test_provider_warning_data_never_autofilters(self, get):
        for code in ("1", "0,1", "6", "11", "", None):
            with self.subTest(code=code):
                cache.clear()
                get.return_value = provider_response(ErrorCode=code)
                self.assertEqual(self.post().data, {"status": "unrecognized"})

    @patch("catalog.vin.requests.get")
    def test_unavailable_is_bounded_cached_and_never_leaks_provider_errors(self, get):
        get.side_effect = requests.Timeout("private URL " + VIN)
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {"status": "unavailable"})
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(self.post().status_code, 503)
        get.assert_called_once()

    @patch("catalog.vin.requests.get")
    def test_bad_shape_missing_identity_year_and_wrong_vin_fail_closed(self, get):
        for overrides in ({"Make": ""}, {"Model": None}, {"ModelYear": "unknown"}, {"ModelYear": "1900"}, {"VIN": "OTHER"}):
            with self.subTest(overrides=overrides):
                cache.clear()
                get.return_value = provider_response(**overrides)
                self.assertEqual(decode_vehicle(VIN), {"status": "unavailable"})
        for body in (b"not json", b"[]", b'{"Results":[]}', b'{"Results":[{},{}]}', b'{"Results":"bad"}'):
            cache.clear()
            response = provider_response()
            response.iter_content.return_value = [body]
            get.return_value = response
            self.assertEqual(decode_vehicle(VIN), {"status": "unavailable"})

    @patch("catalog.vin.requests.get")
    def test_redirects_http_failures_and_large_bodies_rejected(self, get):
        for status in (301, 429, 500):
            response = provider_response()
            response.status_code = status
            get.return_value = response
            with self.assertRaises(ValueError):
                _read_provider(VIN)
        response = provider_response()
        response.iter_content.return_value = [b"x" * 262145]
        get.return_value = response
        with self.assertRaises(ValueError):
            _read_provider(VIN)

    @patch("catalog.vin.requests.get")
    def test_lookup_rate_limit_applies_even_to_cached_results(self, get):
        get.return_value = provider_response()
        with patch.dict(CachedScopedRateThrottle.THROTTLE_RATES, {"vin_lookup": "2/min"}):
            self.assertEqual(self.post().status_code, 200)
            self.assertEqual(self.post().status_code, 200)
            result = self.post()
            self.assertEqual(result.status_code, 429)
            self.assertEqual(result["Cache-Control"], "private, no-store")
            get.assert_called_once()
