import copy
import json
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import SUCCESS
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.text import capfirst

from .courier_state import has_unsettled_courier_shipment
from .models import Order, OrderItem, OrderReturn, WingoShipment
from .test_wingo import reference_client
from .test_wingo_checkout import item
from .wingo import MAX_LABEL_BYTES, WingoClient, WingoError, WingoResponseError, WingoTransportError
from .wingo_locations import WingoLocality, resolve_delivery_location
from .wingo_quotes import build_delivery_quote, delivery_order_fields
from .wingo_references import refresh_wingo_references
from .wingo_shipments import (
    CREATION_UNCONFIRMED_MESSAGE, WingoShipmentError, build_order_payload, can_submit,
    get_shipment_label, recover_submission, submit_shipment,
)


PDF = b"%PDF-1.4\n test document\n%%EOF\n"


class WingoBookingTransportTests(SimpleTestCase):
    def transport(self, *, body=None, status=201, content_type="application/json", chunks=None):
        response = Mock(status_code=status, headers={"Content-Type": content_type})
        response.iter_content.return_value = chunks if chunks is not None else [json.dumps(body or {}).encode()]
        http = Mock()
        http.request.return_value = response
        return WingoClient(api_key="private-key", api_base_url="https://wingo.example/api/v1", http_client=http), http, response

    def test_booking_posts_json_once_with_no_redirects(self):
        carrier, http, response = self.transport(body={"id": "id-1"})
        self.assertEqual(carrier.create_order({"deliveryTypeId": 1, "recipientPaymentDue": 0}), {"id": "id-1"})
        http.request.assert_called_once_with("POST", "https://wingo.example/api/v1/orders",
            headers={"X-API-Key": "private-key", "Accept": "application/json"}, params=None,
            timeout=(5.0, 20.0), allow_redirects=False, stream=True,
            json={"deliveryTypeId": 1, "recipientPaymentDue": 0})
        response.close.assert_called_once()

    def test_only_documented_refusals_are_retryable(self):
        for status in (400, 401, 403, 422, 301, 404, 408, 409, 429, 500, 502):
            carrier, http, response = self.transport(status=status)
            with self.subTest(status=status), self.assertRaises(WingoResponseError) as caught:
                carrier.create_order({})
            self.assertEqual(caught.exception.outcome_unknown, status not in {400, 401, 403, 422})
            http.request.assert_called_once()
            response.close.assert_called_once()

    def test_timeout_or_invalid_success_is_unknown_without_sensitive_error(self):
        carrier, http, _ = self.transport()
        http.request.side_effect = requests.Timeout("private-key private-phone")
        with self.assertRaises(WingoTransportError) as caught:
            carrier.create_order({})
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertNotIn("private", str(caught.exception))
        http.request.assert_called_once()
        for chunks in ([b"null"], [b"not json"]):
            carrier, _, _ = self.transport(chunks=chunks)
            with self.assertRaises(WingoResponseError) as caught:
                carrier.create_order({})
            self.assertTrue(caught.exception.outcome_unknown)

    def test_private_label_url_formats_and_language(self):
        for size in ("a4", "small"):
            carrier, http, response = self.transport(status=200, content_type="application/pdf", chunks=[PDF])
            self.assertEqual(carrier.get_label("internal-id-1", size=size), PDF)
            self.assertEqual(http.request.call_args.args, ("GET", "https://wingo.example/api/v1/orders/internal-id-1/label"))
            self.assertEqual(http.request.call_args.kwargs["params"], {"format": size, "lang": "ka"})
            response.close.assert_called_once()

    def test_bad_reference_format_and_page_never_send_key(self):
        carrier, http, _ = self.transport()
        for value in ("../orders", "https://evil.example", "id?x=1", "", None, True):
            with self.subTest(value=value), self.assertRaises(WingoError):
                carrier.get_order(value)
        for page, limit in ((True, 1), (101, 1), (1, 1000), (1, False)):
            with self.assertRaises(WingoError):
                carrier.get_orders(page=page, limit=limit)
        with self.assertRaises(WingoError):
            carrier.get_label("id", size="zebra")
        http.request.assert_not_called()

    def test_labels_reject_html_truncation_wrong_type_and_oversize(self):
        for content_type, data in (("text/html", PDF), ("application/pdf", b"html"),
                                    ("application/pdf", b"%PDF-truncated"),
                                    ("application/pdf", b"%PDF-" + b" " * MAX_LABEL_BYTES)):
            carrier, http, response = self.transport(content_type=content_type, chunks=[data])
            with self.assertRaises(WingoResponseError):
                carrier.get_label("id")
            response.close.assert_called_once()
            http.request.assert_called_once()


@override_settings(WINGO_MERCHANT_USER_ID="merchant-test-id", WINGO_PICKUP_TITLE="სატესტო მაღაზია",
                   WINGO_PICKUP_ADDRESS="სატესტო საწყობი", WINGO_PICKUP_PHONE="+995322123456")
class WingoShipmentFixture(TestCase):
    def setUp(self):
        refresh_wingo_references(client=reference_client())
        mapping = WingoLocality.objects.get(external_id="oayK3wTbTlSTuvTHkTHc")
        self.location = resolve_delivery_location(mapping.region_id, mapping.pk)
        quote = build_delivery_quote(source="cart", items=[item()], region=self.location, city=self.location)
        self.order = Order.objects.create(order_number="ORDER-WINGO-1", first_name="სატესტო", last_name="მიმღები",
            phone="+995 555 000 002", city="თბილისი", address_line="სატესტო მისამართი",
            payment_status="paid", payment_method="card", status="confirmed", subtotal=100, total=146,
            **delivery_order_fields(quote))
        OrderItem.objects.create(order=self.order, product_name="სატესტო ნაწილი", sku="private-supplier-code",
            internal_sku="FD-03-0001", unit_price=50, quantity=2, line_total=100)
        self.carrier = Mock(spec=WingoClient)
        self.carrier.api_base_url = "https://wingo.example/api/v1"
        self.carrier.account_mode = "test"
        self.carrier.create_order.side_effect = lambda payload: self.result(payload)

    def payload(self, parcels=2):
        self.order.refresh_from_db()
        return build_order_payload(self.order, parcel_count=parcels, client=self.carrier)

    def result(self, payload=None, **changes):
        return {**copy.deepcopy(payload or self.payload()), "id": "internal-wingo-id", "orderNumber": "999-1000001",
                "serviceFee": 46, "orderStatusId": 1, "weightRangeId": "6", **changes}

    def submit(self, **kwargs):
        return submit_shipment(self.order.pk, parcel_count=2, prepared=True, client=self.carrier, **kwargs)

    def unknown(self):
        self.carrier.create_order.side_effect = WingoTransportError()
        with self.assertRaises(WingoShipmentError):
            self.submit()
        return WingoShipment.objects.get(order=self.order)

    def pages(self, rows, *, next_page=False, page=1):
        return {"orders": rows, "pagination": {"page": page, "hasNext": next_page}}

    def change_order(self, **values):
        for key, value in values.items():
            setattr(self.order, key, value)
        self.order.save(update_fields=list(values))


class WingoShipmentTests(WingoShipmentFixture):
    @override_settings(WINGO_DELIVERY_BUFFER_GEL=Decimal("2.50"))
    def test_buffer_stays_on_order_and_does_not_inflate_carrier_price_or_payload(self):
        quote = build_delivery_quote(source="cart", items=[item()], region=self.location, city=self.location)
        self.change_order(total=Decimal("148.50"), **delivery_order_fields(quote))
        shipment = self.submit()
        self.assertEqual((self.order.delivery_price, self.order.delivery_margin, self.order.carrier_delivery_cost),
                         (Decimal("48.50"), Decimal("2.50"), Decimal("46.00")))
        self.assertEqual(shipment.booked_price, Decimal("46.00"))
        self.assertEqual(shipment.last_error, "")
        self.assertNotIn("delivery_margin", shipment.request_payload)
        self.assertNotIn("serviceFee", shipment.request_payload)
        self.assertEqual(shipment.request_payload["recipientPaymentDue"], 0)

    def test_frozen_order_payload_standard_prepaid_products_and_packages(self):
        payload = self.payload()
        self.assertEqual((payload["deliveryTypeId"], payload["recipientPaymentDue"], payload["packageCount"]), (1, 0, 2))
        self.assertEqual(payload["weightRangeId"], 6)
        self.assertEqual(payload["products"], [{"productName": "სატესტო ნაწილი", "quantity": 2}])
        self.assertEqual(payload["recipientPhone"], "+995555000002")
        self.assertNotIn("serviceFee", payload)
        self.assertNotIn("deliveryDate", payload)
        self.assertNotIn("private-supplier-code", str(payload))
        self.assertNotIn("FD-03-0001", str(payload))

    def test_confirmation_and_integer_parcel_count_required_before_io_or_db_attempt(self):
        with self.assertRaises(WingoShipmentError):
            submit_shipment(self.order.pk, parcel_count=1, prepared=False, client=self.carrier)
        for parcels in (0, True, -1, 1.5, "2", 1001):
            with self.subTest(parcels=parcels), self.assertRaises(WingoShipmentError):
                submit_shipment(self.order.pk, parcel_count=parcels, prepared=True, client=self.carrier)
        self.assertFalse(WingoShipment.objects.exists())
        self.carrier.create_order.assert_not_called()

    def test_created_shipment_preserves_payment_stock_status_and_quoted_price(self):
        before = Order.objects.values().get(pk=self.order.pk)
        shipment = self.submit()
        self.assertEqual(shipment.state, "created")
        self.assertEqual((shipment.provider_order_id, shipment.tracking_number), ("internal-wingo-id", "999-1000001"))
        self.assertEqual(shipment.booked_price, Decimal(46))
        self.assertEqual(shipment.parcel_count, 2)
        self.assertIsNotNone(shipment.submitted_at)
        self.assertEqual(before, Order.objects.values().get(pk=self.order.pk))
        self.assertFalse(can_submit(self.order))
        with self.assertRaises(WingoShipmentError):
            self.submit()
        self.carrier.create_order.assert_called_once()

    def test_returned_price_discrepancy_is_separate_and_does_not_recharge_customer(self):
        self.carrier.create_order.side_effect = lambda payload: self.result(payload, serviceFee=49)
        shipment = self.submit()
        self.order.refresh_from_db()
        self.assertEqual((self.order.total, self.order.delivery_price, self.order.carrier_delivery_cost), (146, 46, 46))
        self.assertEqual(shipment.booked_price, Decimal(49))
        self.assertIn("განსხვავდება", shipment.last_error)

    def test_missing_provider_price_stays_unknown_not_zero(self):
        self.carrier.create_order.side_effect = lambda payload: self.result(payload, serviceFee=None)
        shipment = self.submit()
        self.assertEqual(shipment.state, "created")
        self.assertIsNone(shipment.booked_price)
        self.assertTrue(shipment.last_error)

    def test_only_paid_ready_wingo_orders_are_sent(self):
        for change in ({"payment_status": "pending"}, {"payment_status": "refund_pending"},
                       {"status": "shipped"}, {"status": "delivered"}, {"status": "cancelled"},
                       {"delivery_provider": "redcap"}, {"stock_restored_at": timezone.now()}):
            self.order.refresh_from_db()
            old = {key: getattr(self.order, key) for key in change}
            self.change_order(**change)
            with self.subTest(change=change), self.assertRaises(WingoShipmentError):
                self.submit()
            self.change_order(**old)
        self.carrier.create_order.assert_not_called()
        self.assertFalse(WingoShipment.objects.exists())

    def test_existing_physical_return_blocks_submission(self):
        OrderReturn.objects.create(order=self.order, disposition="not_purchased", receipt_status="not_required")
        with self.assertRaises(WingoShipmentError):
            self.submit()
        self.carrier.create_order.assert_not_called()

    def test_missing_sender_config_fails_before_attempt(self):
        for field in ("WINGO_MERCHANT_USER_ID", "WINGO_PICKUP_TITLE", "WINGO_PICKUP_ADDRESS", "WINGO_PICKUP_PHONE"):
            with self.subTest(field=field), override_settings(**{field: ""}), self.assertRaises(WingoError):
                self.submit()
        self.assertFalse(WingoShipment.objects.exists())
        self.carrier.create_order.assert_not_called()

    def test_mismatched_snapshot_account_or_location_blocks_sending(self):
        for field, value in (("account_mode", "production"), ("api_base_url", "https://another.example/api/v1")):
            original = getattr(self.carrier, field)
            setattr(self.carrier, field, value)
            with self.assertRaises(WingoError):
                self.submit()
            setattr(self.carrier, field, original)
        self.change_order(delivery_provider_data={**self.order.delivery_provider_data, "locality_id": "different"})
        with self.assertRaises(WingoError):
            self.submit()
        self.carrier.create_order.assert_not_called()

    def test_invalid_frozen_weight_band_or_fast_type_blocks_sending(self):
        original = self.order.delivery_provider_data.copy()
        for data in ({**original, "weight_range_id": 1}, {**original, "delivery_type_id": 2},
                     {**original, "delivery_type_id": True}, {}):
            self.change_order(delivery_provider_data=data)
            with self.subTest(data=data), self.assertRaises(WingoError):
                self.submit()
        self.carrier.create_order.assert_not_called()

    def test_timeout_freezes_request_and_blocks_all_retries(self):
        shipment = self.unknown()
        self.assertEqual(shipment.state, "unknown")
        frozen = shipment.request_payload
        self.change_order(address_line="შეცვლილი მისამართი")
        with self.assertRaises(WingoShipmentError):
            self.submit()
        shipment.refresh_from_db()
        self.assertEqual(shipment.request_payload, frozen)
        self.carrier.create_order.assert_called_once()
        self.assertTrue(has_unsettled_courier_shipment(self.order))

    def test_definite_rejection_allows_corrected_retry(self):
        self.carrier.create_order.side_effect = WingoResponseError(status_code=400, outcome_unknown=False)
        with self.assertRaises(WingoShipmentError):
            self.submit()
        self.assertEqual(WingoShipment.objects.get().state, "failed")
        self.assertFalse(has_unsettled_courier_shipment(self.order))
        self.carrier.create_order.side_effect = lambda payload: self.result(payload)
        self.assertEqual(self.submit().state, "created")
        self.assertEqual(self.carrier.create_order.call_count, 2)

    def test_malformed_or_foreign_success_never_becomes_retryable(self):
        for changes in ({"id": "../bad"}, {"orderNumber": ""}, {"userId": "another"},
                        {"supplierOrderId": "another"}, {"recipientPhone": "+995555000099"},
                        {"weightRangeId": "5"}, {"packageCount": 1}, {"recipientPaymentDue": 50}):
            self.carrier.create_order.side_effect = lambda payload: self.result(payload, **changes)
            with self.subTest(changes=changes), self.assertRaises(WingoShipmentError):
                self.submit()
            self.assertEqual(WingoShipment.objects.get().state, "unknown")
            self.assertFalse(can_submit(self.order))
            WingoShipment.objects.all().delete()  # disposable fixture only

    def test_unexpected_error_is_sanitized_and_unknown(self):
        self.carrier.create_order.side_effect = RuntimeError("private-key private-phone")
        with self.assertRaises(WingoShipmentError) as caught:
            self.submit()
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("private", WingoShipment.objects.get().last_error)
        self.assertEqual(WingoShipment.objects.get().state, "unknown")

    def test_provider_id_already_attached_elsewhere_keeps_new_attempt_unknown(self):
        other = Order.objects.create(order_number="WINGO-OTHER", subtotal=1, total=1)
        WingoShipment.objects.create(order=other, state="created", provider_order_id="internal-wingo-id",
            tracking_number="999-2000001", submitted_at=timezone.now())
        with self.assertRaises(WingoShipmentError):
            self.submit()
        self.assertEqual(WingoShipment.objects.get(order=self.order).state, "unknown")
        self.assertEqual(WingoShipment.objects.get(order=other).tracking_number, "999-2000001")
        self.assertFalse(can_submit(self.order))
        self.carrier.create_order.assert_called_once()

    def test_private_attempt_and_pickup_details_are_absent_from_customer_serializers(self):
        from .serializers import OrderLookupSummarySerializer, OrderSummarySerializer, PublicOrderSummarySerializer
        self.submit()
        for serializer in (OrderLookupSummarySerializer, OrderSummarySerializer, PublicOrderSummarySerializer):
            body = str(serializer(self.order).data)
            for private in ("request_payload", "wingo_shipment", "merchant-test-id", "სატესტო საწყობი",
                            "internal-wingo-id", "private-supplier-code"):
                self.assertNotIn(private, body)

    def test_recovery_ignores_nonmatching_first_row_and_reads_all_pages(self):
        shipment = self.unknown()
        result = self.result(shipment.request_payload)
        other = {**result, "id": "unrelated", "supplierOrderId": "OTHER", "orderNumber": "999-2000000"}
        self.carrier.get_orders.side_effect = [self.pages([other], next_page=True), self.pages([result], page=2)]
        self.carrier.get_order.return_value = result
        recovered = recover_submission(self.order.pk, client=self.carrier)
        self.assertEqual(recovered.state, "created")
        self.assertEqual(recovered.request_payload, shipment.request_payload)
        self.assertEqual(self.carrier.get_orders.call_args_list[1].kwargs, {"page": 2, "limit": 100})
        self.carrier.get_order.assert_called_once_with("internal-wingo-id")
        self.carrier.create_order.assert_called_once()

    def test_recovery_no_match_does_not_release_retry(self):
        self.unknown()
        self.carrier.get_orders.return_value = self.pages([])
        with self.assertRaises(WingoShipmentError):
            recover_submission(self.order.pk, client=self.carrier)
        self.assertEqual(WingoShipment.objects.get().state, "unknown")
        self.assertFalse(can_submit(self.order))
        self.carrier.get_order.assert_not_called()

    def test_duplicate_supplier_ids_require_review_instead_of_first_match(self):
        shipment = self.unknown()
        result = self.result(shipment.request_payload)
        second = {**result, "id": "second", "orderNumber": "999-1000002"}
        self.carrier.get_orders.side_effect = [self.pages([result], next_page=True), self.pages([second], page=2)]
        with self.assertRaises(WingoShipmentError):
            recover_submission(self.order.pk, client=self.carrier)
        self.assertEqual(WingoShipment.objects.get().state, "unknown")
        self.carrier.get_order.assert_not_called()

    def test_foreign_merchant_or_changed_details_do_not_link(self):
        shipment = self.unknown()
        result = self.result(shipment.request_payload)
        self.carrier.get_orders.return_value = self.pages([result])
        for changed in ({"userId": "foreign"}, {"deliveryAddress": "changed"}, {"id": "different"}):
            self.carrier.get_order.return_value = {**result, **changed}
            with self.subTest(changed=changed), self.assertRaises(WingoError):
                recover_submission(self.order.pk, client=self.carrier)
        self.assertEqual(WingoShipment.objects.get().state, "unknown")

    def test_account_switch_blocks_recovery_before_network(self):
        self.unknown()
        with override_settings(WINGO_MERCHANT_USER_ID="new-account"), self.assertRaises(WingoError):
            recover_submission(self.order.pk, client=self.carrier)
        self.carrier.get_orders.assert_not_called()

    def test_repeated_pagination_or_invalid_pagination_cannot_confirm(self):
        shipment = self.unknown()
        result = self.result(shipment.request_payload, supplierOrderId="OTHER")
        for pages in ([self.pages([result], next_page=True), self.pages([result], page=2)],
                      [{"orders": [result]}], [self.pages([], next_page=True)],
                      [{"orders": [], "pagination": {"page": True, "hasNext": False}}]):
            self.carrier.get_orders.side_effect = pages
            with self.subTest(pages=pages), self.assertRaises(WingoError):
                recover_submission(self.order.pk, client=self.carrier)
        self.assertEqual(WingoShipment.objects.get().state, "unknown")

    def test_bounded_recovery_does_not_link_match_before_search_completes(self):
        shipment = self.unknown()
        result = self.result(shipment.request_payload)
        self.carrier.get_orders.side_effect = [self.pages([
            result if page == 1 else {"id": f"other-{page}", "supplierOrderId": "OTHER"}], next_page=True, page=page)
            for page in range(1, 11)]
        with self.assertRaises(WingoError):
            recover_submission(self.order.pk, client=self.carrier)
        self.assertEqual(self.carrier.get_orders.call_count, 10)
        self.carrier.get_order.assert_not_called()
        self.assertEqual(WingoShipment.objects.get().state, "unknown")

    def test_recovery_page_limit_is_validated_before_network(self):
        self.unknown()
        for limit in (0, 11, True, 1.5, "2"):
            with self.subTest(limit=limit), self.assertRaises(WingoShipmentError):
                recover_submission(self.order.pk, client=self.carrier, max_pages=limit)
        self.carrier.get_orders.assert_not_called()

    def test_recovery_winning_race_cannot_be_overwritten_by_late_post_response(self):
        def delayed_create(payload):
            result = self.result(payload)
            self.carrier.get_orders.return_value = self.pages([result])
            self.carrier.get_order.return_value = result
            recover_submission(self.order.pk, client=self.carrier)
            return result
        self.carrier.create_order.side_effect = delayed_create
        with self.assertRaises(WingoError):
            self.submit()
        self.assertEqual(WingoShipment.objects.get().state, "created")
        self.assertEqual(WingoShipment.objects.get().tracking_number, "999-1000001")

    def test_label_requires_confirmed_identity_and_uses_internal_id(self):
        with self.assertRaises(WingoError):
            get_shipment_label(self.order.pk, client=self.carrier)
        shipment = self.submit()
        self.carrier.get_order.return_value = self.result(shipment.request_payload)
        self.carrier.get_label.return_value = PDF
        self.assertEqual(get_shipment_label(self.order.pk, size="small", client=self.carrier), PDF)
        self.carrier.get_label.assert_called_once_with("internal-wingo-id", size="small")
        self.carrier.create_order.assert_called_once()

    def test_private_label_is_not_returned_for_foreign_order(self):
        shipment = self.submit()
        self.carrier.get_order.return_value = self.result(shipment.request_payload, userId="foreign")
        with self.assertRaises(WingoError):
            get_shipment_label(self.order.pk, client=self.carrier)
        self.carrier.get_label.assert_not_called()

    def test_active_or_uncertain_booking_blocks_pre_dispatch_return_and_refund(self):
        from .bog_refunds import _return_ready_for_refund
        from .returns import prepare_order_return
        actor = get_user_model().objects.create_superuser(username="operator", email="operator@example.com", password="password")
        self.assertFalse(has_unsettled_courier_shipment(self.order))
        self.unknown()
        self.assertFalse(_return_ready_for_refund(self.order))
        with self.assertRaisesMessage(ValidationError, "Wingo"):
            prepare_order_return(order=self.order, disposition="not_purchased", actor=actor)
        self.assertFalse(OrderReturn.objects.exists())

    def test_database_rejects_incomplete_created_state_and_invalid_parcels(self):
        for changes in ({"state": "created"}, {"parcel_count": 0}, {"parcel_count": 1001}, {"booked_price": -1}):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), transaction.atomic():
                WingoShipment.objects.create(order=self.order, **changes)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class WingoOrderAdminTests(WingoShipmentFixture):
    def setUp(self):
        super().setUp()
        self.operator = get_user_model().objects.create_superuser(username="wingo-admin", email="wingo-admin@example.com", password="password")
        self.client.force_login(self.operator)

    def url(self, action):
        return reverse(f"admin:commerce_order_wingo_{action}", args=[self.order.pk])

    def test_paid_order_shows_georgian_button_and_confirmation_without_network(self):
        with patch("commerce.wingo_order_admin.submit_shipment") as submit:
            page = self.client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
            self.assertContains(page, "Wingo-ში გაგზავნა")
            self.assertNotContains(page, "RedCap-ში გზავნილის შექმნა")
            response = self.client.get(self.url("submit"))
        self.assertContains(response, "შეფუთვების რაოდენობა")
        self.assertContains(response, "ნივთები შემოწმებულია, შეფუთულია და მზადაა კურიერისთვის")
        self.assertContains(response, 'value="1"')
        self.assertNotContains(response, "13:00")
        self.assertFalse(WingoShipment.objects.exists())
        submit.assert_not_called()

    def test_checkbox_required_and_submit_posts_once_then_shows_labels(self):
        with patch("commerce.wingo_shipments.WingoClient.from_settings", return_value=self.carrier):
            invalid = self.client.post(self.url("submit"), {"parcel_count": 2})
            self.assertContains(invalid, "დაადასტურეთ ნივთების შემოწმება და მომზადება")
            self.carrier.create_order.assert_not_called()
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"})
            self.assertEqual(response.status_code, 302)
            self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"})
            page = self.client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
        self.assertContains(page, "სტიკერის გახსნა / ბეჭდვა — A4")
        self.assertContains(page, "პატარა სტიკერის გახსნა / ბეჭდვა")
        self.assertContains(page, "999-1000001")
        self.assertNotContains(page, ">Wingo-ში გაგზავნა</a>")
        self.carrier.create_order.assert_called_once()

    def test_unknown_result_shows_recovery_instead_of_resubmit_or_labels(self):
        self.unknown()
        page = self.client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
        self.assertContains(page, "Wingo-ში გაგზავნის შედეგის გადამოწმება")
        self.assertNotContains(page, ">Wingo-ში გაგზავნა</a>")
        self.assertNotContains(page, "სტიკერის გახსნა / ბეჭდვა — A4")
        self.assertContains(page, CREATION_UNCONFIRMED_MESSAGE)

    def test_uncertain_post_redirects_to_recovery_instead_of_another_submit_form(self):
        self.carrier.create_order.side_effect = WingoTransportError()
        with patch("commerce.wingo_shipments.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"}, follow=True)
        self.assertContains(response, "Wingo-ში გაგზავნის შედეგის გადამოწმება")
        self.assertNotContains(response, ">Wingo-ში გაგზავნა</a>")
        self.assertContains(response, CREATION_UNCONFIRMED_MESSAGE)
        self.carrier.create_order.assert_called_once()

    def test_timeout_automatically_confirms_existing_shipment_without_second_post(self):
        result = self.result()
        self.carrier.create_order.side_effect = WingoTransportError()
        self.carrier.get_orders.return_value = self.pages([result])
        self.carrier.get_order.return_value = result
        original = (self.order.total, self.order.delivery_price, self.order.payment_status, self.order.status)
        with patch("commerce.wingo_order_admin.WingoClient.from_settings", return_value=self.carrier) as factory:
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"}, follow=True)
        self.assertContains(response, capfirst("გზავნილი წარმატებით შეიქმნა. ნომერი: 999-1000001"))
        self.assertEqual([message.level for message in response.context["messages"]], [SUCCESS])
        self.assertContains(response, "სტიკერის გახსნა / ბეჭდვა — A4")
        self.assertNotContains(response, CREATION_UNCONFIRMED_MESSAGE)
        self.assertNotContains(response, ">Wingo-ში გაგზავნა</a>")
        shipment = WingoShipment.objects.get(order=self.order)
        self.assertEqual((shipment.state, shipment.tracking_number, shipment.last_error), ("created", "999-1000001", ""))
        self.order.refresh_from_db()
        self.assertEqual((self.order.total, self.order.delivery_price, self.order.payment_status, self.order.status), original)
        self.carrier.create_order.assert_called_once()
        self.carrier.get_orders.assert_called_once_with(page=1, limit=100)
        self.carrier.get_order.assert_called_once_with("internal-wingo-id")
        factory.assert_any_call(connect_timeout=2, read_timeout=4)

    def test_unverifiable_create_response_can_be_confirmed_by_canonical_get(self):
        result = self.result()
        self.carrier.create_order.side_effect = None
        self.carrier.create_order.return_value = {"id": "incomplete"}
        self.carrier.get_orders.return_value = self.pages([result])
        self.carrier.get_order.return_value = result
        with patch("commerce.wingo_order_admin.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"}, follow=True)
        self.assertContains(response, capfirst("გზავნილი წარმატებით შეიქმნა. ნომერი: 999-1000001"))
        self.assertEqual(WingoShipment.objects.get().state, "created")
        self.carrier.create_order.assert_called_once()

    def test_failed_automatic_read_remains_blocked_and_does_not_expose_errors(self):
        self.carrier.create_order.side_effect = WingoTransportError()
        self.carrier.get_orders.side_effect = WingoTransportError()
        with patch("commerce.wingo_order_admin.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"}, follow=True)
            # A second submit cannot create anything or repeat automatic reads.
            self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"})
        self.assertContains(response, CREATION_UNCONFIRMED_MESSAGE)
        self.assertNotContains(response, "სტიკერის გახსნა / ბეჭდვა — A4")
        self.assertNotContains(response, "წარმატებით შეიქმნა")
        self.assertEqual(WingoShipment.objects.get().state, "unknown")
        self.assertFalse(can_submit(self.order))
        self.carrier.create_order.assert_called_once()
        self.carrier.get_orders.assert_called_once()

    def test_automatic_search_never_accepts_missing_duplicate_or_foreign_match(self):
        result = self.result()
        for rows, detail in (([], result),
                             ([result, {**result, "id": "other-id"}], result),
                             ([result], {**result, "userId": "foreign-merchant"})):
            with self.subTest(rows=rows):
                self.carrier.reset_mock(side_effect=True)
                self.carrier.create_order.side_effect = WingoTransportError()
                self.carrier.get_orders.return_value = self.pages(rows)
                self.carrier.get_order.return_value = detail
                with patch("commerce.wingo_order_admin.WingoClient.from_settings", return_value=self.carrier):
                    response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"}, follow=True)
                self.assertContains(response, CREATION_UNCONFIRMED_MESSAGE)
                self.assertNotContains(response, "წარმატებით შეიქმნა")
                self.assertEqual(WingoShipment.objects.get().state, "unknown")
                self.assertFalse(can_submit(self.order))
                self.carrier.create_order.assert_called_once()
                WingoShipment.objects.all().delete()  # disposable fixture only

    def test_automatic_search_is_bounded_and_manual_check_can_finish_search(self):
        result = self.result()
        pages = [self.pages([result], next_page=True),
                 self.pages([{"id": "other", "supplierOrderId": "OTHER"}], next_page=True, page=2)]
        self.carrier.create_order.side_effect = WingoTransportError()
        self.carrier.get_orders.side_effect = pages
        with patch("commerce.wingo_order_admin.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"}, follow=True)
            self.assertContains(response, CREATION_UNCONFIRMED_MESSAGE)
            self.assertEqual(self.carrier.get_orders.call_count, 2)
            self.carrier.get_order.assert_not_called()
            self.assertEqual(WingoShipment.objects.get().state, "unknown")
            self.carrier.get_orders.side_effect = pages + [self.pages([], page=3)]
            self.carrier.get_order.return_value = result
            self.assertEqual(self.client.post(self.url("recover")).status_code, 302)
        self.assertEqual(WingoShipment.objects.get().state, "created")
        self.assertEqual(self.carrier.get_orders.call_count, 5)
        self.carrier.create_order.assert_called_once()

    def test_normal_success_and_definite_refusal_do_not_start_recovery(self):
        with patch("commerce.wingo_order_admin.WingoClient.from_settings", return_value=self.carrier):
            self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"})
            self.carrier.get_orders.assert_not_called()
            WingoShipment.objects.all().delete()  # disposable fixture only
            self.carrier.create_order.side_effect = WingoResponseError(status_code=401, outcome_unknown=False)
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"})
        self.assertContains(response, "Wingo-მ მოთხოვნა უარყო")
        self.assertNotContains(response, CREATION_UNCONFIRMED_MESSAGE)
        self.assertEqual(WingoShipment.objects.get().state, "failed")
        self.carrier.get_orders.assert_not_called()

    def test_concurrent_verified_recovery_is_not_reported_as_failed_submission(self):
        def delayed_create(payload):
            result = self.result(payload)
            self.carrier.get_orders.return_value = self.pages([result])
            self.carrier.get_order.return_value = result
            recover_submission(self.order.pk, client=self.carrier)
            raise WingoTransportError()

        self.carrier.create_order.side_effect = delayed_create
        with patch("commerce.wingo_order_admin.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.post(self.url("submit"), {"parcel_count": 2, "prepared": "on"}, follow=True)
        self.assertContains(response, capfirst("გზავნილი წარმატებით შეიქმნა. ნომერი: 999-1000001"))
        self.assertNotContains(response, CREATION_UNCONFIRMED_MESSAGE)
        self.assertEqual(WingoShipment.objects.get().state, "created")
        self.carrier.create_order.assert_called_once()
        self.carrier.get_orders.assert_called_once()

    def test_recovery_get_is_read_only_and_post_never_creates(self):
        shipment = self.unknown()
        result = self.result(shipment.request_payload)
        self.carrier.get_orders.return_value = self.pages([result])
        self.carrier.get_order.return_value = result
        with patch("commerce.wingo_shipments.WingoClient.from_settings", return_value=self.carrier):
            self.assertEqual(self.client.get(self.url("recover")).status_code, 200)
            self.carrier.get_orders.assert_not_called()
            self.assertEqual(self.client.post(self.url("recover")).status_code, 302)
        self.assertEqual(WingoShipment.objects.get().state, "created")
        self.carrier.create_order.assert_called_once()

    def test_pdf_proxy_is_private_and_formats_are_constrained(self):
        shipment = self.submit()
        self.carrier.get_order.return_value = self.result(shipment.request_payload)
        self.carrier.get_label.return_value = PDF
        with patch("commerce.wingo_shipments.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.get(self.url("label") + "?size=small")
            self.assertEqual(b"".join(response.streaming_content), PDF)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("inline", response["Content-Disposition"])
            download = self.client.get(self.url("label") + "?download=1")
            self.assertIn("attachment", download["Content-Disposition"])
            download.close()
            self.assertEqual(self.client.get(self.url("label") + "?size=evil").status_code, 404)

    def test_view_only_staff_cannot_book_recover_or_read_labels(self):
        viewer = get_user_model().objects.create_user(username="wingo-viewer", email="wingo-viewer@example.com", password="password", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename="view_order", content_type__app_label="commerce"))
        self.client.force_login(viewer)
        page = self.client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, ">Wingo-ში გაგზავნა</a>")
        for action in ("submit", "recover", "label"):
            self.assertEqual(self.client.get(self.url(action)).status_code, 403)
            self.assertEqual(self.client.post(self.url(action)).status_code, 403)

    def test_anonymous_wrong_courier_methods_and_csrf_are_blocked(self):
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.operator)
        self.assertEqual(protected.post(self.url("submit"), {"parcel_count": 1, "prepared": "on"}).status_code, 403)
        self.assertEqual(self.client.delete(self.url("submit")).status_code, 405)
        self.assertEqual(self.client.put(self.url("recover")).status_code, 405)
        self.assertEqual(self.client.post(self.url("label")).status_code, 405)
        self.change_order(delivery_provider="redcap")
        self.assertEqual(self.client.get(self.url("submit")).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url("label")).status_code, 302)
        self.carrier.create_order.assert_not_called()
