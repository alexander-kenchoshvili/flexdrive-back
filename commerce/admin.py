from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .bog_callbacks import BogCallbackError, reconcile_bog_payment
from .bog_payments import BogPaymentError
from .bog_refunds import (
    can_request_bog_full_refund,
    get_bog_sale_payment_for_order,
    request_bog_full_refund,
)
from .easyway_shipments import (
    EasywayShipmentError,
    can_cancel_easyway_shipment,
    can_submit_easyway_shipment,
    cancel_easyway_shipment,
    submit_easyway_shipment,
)
from .models import (
    Cart,
    CartItem,
    CheckoutAttempt,
    EasywayCity,
    EasywayRegion,
    Order,
    OrderItem,
    OrderStatus,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
    StockReservation,
    StockReservationItem,
)
from .services import (
    can_cancel_order,
    can_transition_order_status,
    cancel_order_and_restore_stock,
    transition_order_status,
)


def _bog_reconciliation_message_level(result):
    if result in {
        "refund_rejected",
        "rejected",
        "paid_fulfillment_blocked",
    }:
        return messages.ERROR
    if (
        "pending" in result
        or "required" in result
        or "review" in result
    ):
        return messages.WARNING
    return messages.SUCCESS


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "quantity", "created_at")
    readonly_fields = ("created_at",)


@admin.register(EasywayRegion)
class EasywayRegionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "external_id",
        "is_internal_delivery",
        "is_active",
        "last_synced_at",
    )
    list_filter = ("is_internal_delivery", "is_active")
    search_fields = ("name", "external_id")
    readonly_fields = (
        "external_id",
        "name",
        "is_active",
        "last_synced_at",
        "created_at",
        "updated_at",
    )
    fields = (
        "external_id",
        "name",
        "is_internal_delivery",
        "is_active",
        "last_synced_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EasywayCity)
class EasywayCityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "region",
        "external_id",
        "is_active",
        "last_synced_at",
    )
    list_filter = ("is_active", "region")
    search_fields = ("name", "external_id", "region__name")
    list_select_related = ("region",)
    readonly_fields = (
        "region",
        "external_id",
        "name",
        "is_active",
        "last_synced_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "guest_token", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("user__email", "user__username", "guest_token")
    readonly_fields = ("created_at", "updated_at")
    inlines = (CartItemInline,)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "sku", "unit_price", "quantity", "line_total")
    readonly_fields = fields
    can_delete = False


class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    fields = (
        "provider",
        "payment_method",
        "action",
        "status",
        "amount",
        "currency",
        "provider_order_id",
        "provider_transaction_id",
        "provider_action_id",
        "created_at",
    )
    readonly_fields = fields
    can_delete = False


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        if not self.instance.pk:
            return cleaned_data

        next_status = cleaned_data.get("status")
        current_order = Order.objects.only("status").get(
            pk=self.instance.pk
        )

        if next_status and current_order.status != next_status:
            if next_status == OrderStatus.CANCELLED:
                self.add_error(
                    "status",
                    "Use the 'Cancel and restore stock' button to cancel this order.",
                )
            elif not can_transition_order_status(current_order, next_status):
                self.add_error(
                    "status",
                    (
                        f"Cannot change status from "
                        f"'{current_order.get_status_display()}' "
                        f"to '{OrderStatus(next_status).label}'."
                    ),
                )

        return cleaned_data


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    change_form_template = "admin/commerce/order/change_form.html"
    list_display = (
        "order_number",
        "customer_name",
        "buyer_type",
        "company_name",
        "phone",
        "email",
        "payment_method",
        "payment_status",
        "total",
        "status",
        "created_at",
    )
    list_filter = (
        "buyer_type",
        "status",
        "payment_status",
        "payment_method",
        "created_at",
    )
    search_fields = (
        "order_number",
        "first_name",
        "last_name",
        "email",
        "phone",
        "company_name",
        "company_identification_code",
    )
    readonly_fields = (
        "order_number",
        "public_token",
        "subtotal",
        "delivery_provider",
        "delivery_region_id",
        "delivery_region_name",
        "delivery_city_id",
        "delivery_city_name",
        "carrier_delivery_cost",
        "delivery_margin",
        "delivery_price",
        "shipping_weight_kg",
        "shipping_length_cm",
        "shipping_width_cm",
        "shipping_height_cm",
        "delivery_package_id",
        "easyway_shipment_state",
        "easyway_order_id",
        "easyway_last_error",
        "easyway_last_attempt_at",
        "easyway_submitted_at",
        "total",
        "payment_method",
        "payment_status",
        "terms_accepted_at",
        "terms_version",
        "terms_content_hash",
        "terms_content_snapshot",
        "terms_url",
        "terms_ip_address",
        "terms_user_agent",
        "stock_restored_at",
        "created_at",
        "updated_at",
    )
    inlines = (OrderItemInline, PaymentTransactionInline)

    fieldsets = (
        (
            "Order",
            {
                "fields": (
                    "order_number",
                    "public_token",
                    "buyer_type",
                    "payment_method",
                    "payment_status",
                    "status",
                )
            },
        ),
        (
            "Company",
            {
                "fields": (
                    "company_name",
                    "company_identification_code",
                )
            },
        ),
        ("Customer", {"fields": ("first_name", "last_name", "email", "phone")}),
        (
            "Delivery",
            {
                "fields": (
                    "delivery_provider",
                    "delivery_region_id",
                    "delivery_region_name",
                    "delivery_city_id",
                    "delivery_city_name",
                    "city",
                    "address_line",
                    "note",
                    "carrier_delivery_cost",
                    "delivery_margin",
                    "shipping_weight_kg",
                    "shipping_length_cm",
                    "shipping_width_cm",
                    "shipping_height_cm",
                    "delivery_package_id",
                )
            },
        ),
        ("Totals", {"fields": ("subtotal", "delivery_price", "total")}),
        (
            "EasyWay shipment",
            {
                "fields": (
                    "easyway_shipment_state",
                    "easyway_order_id",
                    "easyway_last_error",
                    "easyway_last_attempt_at",
                    "easyway_submitted_at",
                )
            },
        ),
        (
            "Legal acceptance",
            {
                "fields": (
                    "terms_accepted_at",
                    "terms_version",
                    "terms_content_hash",
                    "terms_url",
                    "terms_ip_address",
                    "terms_user_agent",
                    "terms_content_snapshot",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("stock_restored_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Customer")
    def customer_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/bog-refund/",
                self.admin_site.admin_view(self.bog_refund_view),
                name="commerce_order_bog_refund",
            ),
            path(
                "<path:object_id>/bog-reconcile/",
                self.admin_site.admin_view(self.bog_reconcile_view),
                name="commerce_order_bog_reconcile",
            ),
            path(
                "<path:object_id>/easyway-submit/",
                self.admin_site.admin_view(self.easyway_submit_view),
                name="commerce_order_easyway_submit",
            ),
            path(
                "<path:object_id>/easyway-cancel/",
                self.admin_site.admin_view(self.easyway_cancel_view),
                name="commerce_order_easyway_cancel",
            ),
        ]
        return custom_urls + super().get_urls()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}

        if object_id:
            order = self.get_object(request, object_id)
            extra_context["show_cancel_and_restore_stock"] = bool(
                order and can_cancel_order(order)
            )
            sale_payment = self._bog_sale_payment_or_none(order)
            extra_context["show_bog_full_refund"] = bool(
                order and can_request_bog_full_refund(order)
            )
            extra_context["show_bog_reconciliation"] = bool(
                sale_payment and sale_payment.provider_order_id
            )
            extra_context["show_easyway_submit"] = bool(
                order and can_submit_easyway_shipment(order)
            )
            extra_context["show_easyway_cancel"] = bool(
                order and can_cancel_easyway_shipment(order)
            )
            if order:
                extra_context["bog_refund_url"] = reverse(
                    "admin:commerce_order_bog_refund",
                    args=[order.pk],
                )
                extra_context["bog_reconcile_url"] = reverse(
                    "admin:commerce_order_bog_reconcile",
                    args=[order.pk],
                )
                extra_context["easyway_submit_url"] = reverse(
                    "admin:commerce_order_easyway_submit",
                    args=[order.pk],
                )
                extra_context["easyway_cancel_url"] = reverse(
                    "admin:commerce_order_easyway_cancel",
                    args=[order.pk],
                )
        else:
            extra_context["show_cancel_and_restore_stock"] = False
            extra_context["show_bog_full_refund"] = False
            extra_context["show_bog_reconciliation"] = False
            extra_context["show_easyway_submit"] = False
            extra_context["show_easyway_cancel"] = False

        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if not change:
            super().save_model(request, obj, form, change)
            return

        current_order = Order.objects.get(pk=obj.pk)
        requested_status = obj.status

        obj.status = current_order.status
        super().save_model(request, obj, form, change)
        if requested_status != current_order.status:
            transition_order_status(obj, requested_status)

    def response_change(self, request, obj):
        if "_cancel_and_restore_stock" not in request.POST:
            return super().response_change(request, obj)

        try:
            cancel_order_and_restore_stock(obj)
        except DjangoValidationError as error:
            self.message_user(request, error.messages[0], level=messages.ERROR)
        else:
            self.message_user(
                request,
                "Order was cancelled and stock was restored successfully.",
                level=messages.SUCCESS,
            )

        return HttpResponseRedirect(".")

    def bog_refund_view(self, request, object_id):
        order = self._get_action_order(request, object_id)
        if request.method == "POST":
            try:
                refund = request_bog_full_refund(
                    order=order,
                    requested_by=request.user,
                )
            except DjangoValidationError as error:
                self.message_user(
                    request,
                    error.messages[0],
                    level=messages.ERROR,
                )
            except BogPaymentError as error:
                level = (
                    messages.WARNING
                    if error.retryable or error.outcome_unknown
                    else messages.ERROR
                )
                self.message_user(
                    request,
                    (
                        f"BOG refund was not confirmed ({error.code}). "
                        "Check the refund transaction and reconcile its status."
                    ),
                    level=level,
                )
            else:
                self.message_user(
                    request,
                    (
                        "BOG accepted the full refund request. The refund is "
                        "pending until BOG confirms the final status."
                        if refund.status == PaymentTransactionStatus.REFUND_PENDING
                        else "The existing refund record was reused."
                    ),
                    level=messages.SUCCESS,
                )
            return HttpResponseRedirect(
                reverse("admin:commerce_order_change", args=[order.pk])
            )

        return self._confirmation_response(
            request,
            original=order,
            title=f"Confirm full BOG refund for {order.order_number}",
            action_label="Request full refund",
            warning=(
                f"BOG will receive a full GEL {order.total} refund request. "
                "The request cannot be cancelled. Stock will be restored only "
                "after BOG confirms the refund."
            ),
            cancel_url=reverse(
                "admin:commerce_order_change",
                args=[order.pk],
            ),
        )

    def easyway_submit_view(self, request, object_id):
        order = self._get_action_order(request, object_id)
        if request.method == "POST":
            try:
                submitted_order = submit_easyway_shipment(order)
            except DjangoValidationError as error:
                self.message_user(
                    request,
                    error.messages[0],
                    level=messages.ERROR,
                )
            except EasywayShipmentError as error:
                self.message_user(
                    request,
                    error.detail,
                    level=(
                        messages.WARNING
                        if error.outcome_unknown
                        else messages.ERROR
                    ),
                )
            else:
                self.message_user(
                    request,
                    (
                        "EasyWay shipment created successfully. "
                        f"EasyWay order ID: {submitted_order.easyway_order_id}."
                    ),
                    level=messages.SUCCESS,
                )
            return HttpResponseRedirect(
                reverse("admin:commerce_order_change", args=[order.pk])
            )

        return self._confirmation_response(
            request,
            original=order,
            title=f"Send {order.order_number} to EasyWay",
            action_label="Create EasyWay shipment",
            warning=(
                "This sends a real shipment request to EasyWay. Submit only a paid "
                "regional order that is ready for courier pickup. The same request "
                "must not be sent twice."
            ),
            cancel_url=reverse(
                "admin:commerce_order_change",
                args=[order.pk],
            ),
        )

    def easyway_cancel_view(self, request, object_id):
        order = self._get_action_order(request, object_id)
        if request.method == "POST":
            try:
                cancel_easyway_shipment(order)
            except DjangoValidationError as error:
                self.message_user(
                    request,
                    error.messages[0],
                    level=messages.ERROR,
                )
            except EasywayShipmentError as error:
                self.message_user(
                    request,
                    error.detail,
                    level=(
                        messages.WARNING
                        if error.outcome_unknown
                        else messages.ERROR
                    ),
                )
            else:
                self.message_user(
                    request,
                    "EasyWay shipment cancelled successfully.",
                    level=messages.SUCCESS,
                )
            return HttpResponseRedirect(
                reverse("admin:commerce_order_change", args=[order.pk])
            )

        return self._confirmation_response(
            request,
            original=order,
            title=f"Cancel EasyWay shipment for {order.order_number}",
            action_label="Cancel EasyWay shipment",
            warning=(
                f"EasyWay shipment {order.easyway_order_id} will be cancelled. "
                "This does not refund the card payment or cancel the FlexDrive order."
            ),
            cancel_url=reverse(
                "admin:commerce_order_change",
                args=[order.pk],
            ),
        )

    def bog_reconcile_view(self, request, object_id):
        order = self._get_action_order(request, object_id)
        try:
            sale_payment = get_bog_sale_payment_for_order(order)
        except DjangoValidationError as error:
            raise Http404 from error
        if request.method == "POST":
            try:
                result = reconcile_bog_payment(sale_payment)
            except (BogPaymentError, BogCallbackError) as error:
                self.message_user(
                    request,
                    (
                        f"BOG status could not be reconciled ({error.code}). "
                        "No payment state was guessed."
                    ),
                    level=messages.ERROR,
                )
            except DjangoValidationError as error:
                self.message_user(
                    request,
                    error.messages[0],
                    level=messages.ERROR,
                )
            else:
                self.message_user(
                    request,
                    f"BOG status reconciliation result: {result.result}.",
                    level=_bog_reconciliation_message_level(result.result),
                )
            return HttpResponseRedirect(
                reverse("admin:commerce_order_change", args=[order.pk])
            )

        return self._confirmation_response(
            request,
            original=order,
            title=f"Refresh BOG status for {order.order_number}",
            action_label="Refresh BOG status",
            warning=(
                "FlexDrive will read the latest payment/refund status from BOG "
                "and apply only a verified state transition."
            ),
            cancel_url=reverse(
                "admin:commerce_order_change",
                args=[order.pk],
            ),
        )

    def _get_action_order(self, request, object_id):
        order = self.get_object(request, object_id)
        if order is None:
            raise Http404
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        return order

    def _bog_sale_payment_or_none(self, order):
        if order is None:
            return None
        try:
            return get_bog_sale_payment_for_order(order)
        except DjangoValidationError:
            return None

    def _confirmation_response(
        self,
        request,
        *,
        original,
        title,
        action_label,
        warning,
        cancel_url,
    ):
        return TemplateResponse(
            request,
            "admin/commerce/bog_action_confirmation.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "original": original,
                "title": title,
                "action_label": action_label,
                "warning": warning,
                "cancel_url": cancel_url,
            },
        )


class StockReservationItemInline(admin.TabularInline):
    model = StockReservationItem
    extra = 0
    fields = ("product", "quantity", "unit_price_snapshot", "created_at")
    readonly_fields = fields
    can_delete = False


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = (
        "token",
        "owner_display",
        "source",
        "status",
        "expires_at",
        "completed_order",
        "created_at",
    )
    list_filter = ("status", "source", "created_at", "expires_at")
    search_fields = ("token", "guest_token", "user__email", "user__username", "completed_order__order_number")
    readonly_fields = (
        "token",
        "created_at",
        "updated_at",
        "completed_at",
        "released_at",
    )
    inlines = (StockReservationItemInline,)

    @admin.display(description="Owner")
    def owner_display(self, obj):
        return obj.user or obj.guest_token


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    change_form_template = (
        "admin/commerce/paymenttransaction/change_form.html"
    )
    list_display = (
        "id",
        "order",
        "reservation",
        "provider",
        "payment_method",
        "action",
        "status",
        "amount",
        "currency",
        "provider_order_id",
        "provider_action_id",
        "error_code",
        "created_at",
        "updated_at",
    )
    list_filter = ("provider", "payment_method", "action", "status", "created_at")
    search_fields = (
        "order__order_number",
        "reservation__token",
        "public_token",
        "idempotency_key",
        "provider_order_id",
        "provider_transaction_id",
        "provider_action_id",
    )
    readonly_fields = tuple(
        field.name for field in PaymentTransaction._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/bog-refund/",
                self.admin_site.admin_view(self.bog_refund_view),
                name="commerce_paymenttransaction_bog_refund",
            ),
            path(
                "<path:object_id>/bog-reconcile/",
                self.admin_site.admin_view(self.bog_reconcile_view),
                name="commerce_paymenttransaction_bog_reconcile",
            ),
        ]
        return custom_urls + super().get_urls()

    def changeform_view(
        self,
        request,
        object_id=None,
        form_url="",
        extra_context=None,
    ):
        extra_context = extra_context or {}
        payment = self.get_object(request, object_id) if object_id else None
        is_bog_sale = bool(
            payment
            and payment.provider == PaymentProvider.BOG
            and payment.action == PaymentTransactionAction.SALE
            and payment.provider_order_id
        )
        extra_context["show_bog_reconciliation"] = is_bog_sale
        extra_context["show_bog_full_refund"] = bool(
            is_bog_sale
            and payment.status == PaymentTransactionStatus.PAID
            and payment.order_id is None
        )
        if payment:
            extra_context["bog_refund_url"] = reverse(
                "admin:commerce_paymenttransaction_bog_refund",
                args=[payment.pk],
            )
            extra_context["bog_reconcile_url"] = reverse(
                "admin:commerce_paymenttransaction_bog_reconcile",
                args=[payment.pk],
            )
        return super().changeform_view(
            request,
            object_id,
            form_url,
            extra_context,
        )

    def bog_refund_view(self, request, object_id):
        payment = self._get_action_payment(request, object_id)
        if request.method == "POST":
            try:
                refund = request_bog_full_refund(
                    sale_payment=payment,
                    requested_by=request.user,
                )
            except DjangoValidationError as error:
                self.message_user(
                    request,
                    error.messages[0],
                    level=messages.ERROR,
                )
            except BogPaymentError as error:
                self.message_user(
                    request,
                    (
                        f"BOG refund was not confirmed ({error.code}). "
                        "Reconcile before creating any new request."
                    ),
                    level=(
                        messages.WARNING
                        if error.retryable or error.outcome_unknown
                        else messages.ERROR
                    ),
                )
            else:
                self.message_user(
                    request,
                    (
                        f"Full refund transaction {refund.pk} is pending BOG "
                        "confirmation."
                    ),
                    level=messages.SUCCESS,
                )
            return HttpResponseRedirect(
                reverse(
                    "admin:commerce_paymenttransaction_change",
                    args=[payment.pk],
                )
            )

        return self._confirmation_response(
            request,
            original=payment,
            title=f"Confirm full BOG refund for payment {payment.pk}",
            action_label="Request full refund",
            warning=(
                f"BOG will receive a full GEL {payment.amount} refund request. "
                "This paid transaction has no order and requires incident "
                "recovery."
            ),
        )

    def bog_reconcile_view(self, request, object_id):
        payment = self._get_action_payment(request, object_id)
        if request.method == "POST":
            try:
                result = reconcile_bog_payment(payment)
            except (BogPaymentError, BogCallbackError) as error:
                self.message_user(
                    request,
                    f"BOG reconciliation failed safely ({error.code}).",
                    level=messages.ERROR,
                )
            except DjangoValidationError as error:
                self.message_user(
                    request,
                    error.messages[0],
                    level=messages.ERROR,
                )
            else:
                self.message_user(
                    request,
                    f"BOG status reconciliation result: {result.result}.",
                    level=_bog_reconciliation_message_level(result.result),
                )
            return HttpResponseRedirect(
                reverse(
                    "admin:commerce_paymenttransaction_change",
                    args=[payment.pk],
                )
            )

        return self._confirmation_response(
            request,
            original=payment,
            title=f"Refresh BOG status for payment {payment.pk}",
            action_label="Refresh BOG status",
            warning=(
                "FlexDrive will fetch the latest BOG details and apply the "
                "same verified reconciliation used by callbacks."
            ),
        )

    def _get_action_payment(self, request, object_id):
        payment = self.get_object(request, object_id)
        if payment is None:
            raise Http404
        if not self.has_change_permission(request, payment):
            raise PermissionDenied
        if (
            payment.provider != PaymentProvider.BOG
            or payment.action != PaymentTransactionAction.SALE
            or not payment.provider_order_id
        ):
            raise Http404
        return payment

    def _confirmation_response(
        self,
        request,
        *,
        original,
        title,
        action_label,
        warning,
    ):
        return TemplateResponse(
            request,
            "admin/commerce/bog_action_confirmation.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "original": original,
                "title": title,
                "action_label": action_label,
                "warning": warning,
                "cancel_url": reverse(
                    "admin:commerce_paymenttransaction_change",
                    args=[original.pk],
                ),
            },
        )


@admin.register(CheckoutAttempt)
class CheckoutAttemptAdmin(admin.ModelAdmin):
    list_display = ("key", "source", "order", "created_at", "updated_at")
    list_filter = ("source", "created_at")
    search_fields = ("key", "order__order_number")
    readonly_fields = (
        "key",
        "source",
        "owner_fingerprint",
        "request_fingerprint",
        "order",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
