"""Read-only bank lifecycle and explicit local statement confirmation."""
from decimal import Decimal

from django.contrib import admin
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse, path
from django.utils.html import format_html

from .credo_status import describe_credo_status
from .models import CredoApplication, CredoStatementSettlement
from .credo_finance import expected_credo_amounts, confirm_credo_statement


class CredoStatementForm(forms.Form):
    received_on = forms.DateField(label="ამონაწერის ჩარიცხვის თარიღი", widget=forms.DateInput(attrs={"type": "date"}))
    fee_amount = forms.DecimalField(label="ამონაწერით დადასტურებული ბანკის საკომისიო (₾)", max_digits=12, decimal_places=2, min_value=0)
    net_amount = forms.DecimalField(label="ამონაწერით დადასტურებული ჩარიცხვა (₾)", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    statement_reference = forms.CharField(label="ამონაწერის ჩანაწერის მითითება", max_length=120,
        help_text="შიდა მითითება თანხის მოსაძებნად; პირადი ნომერი ან სხვა მომხმარებლის მონაცემები არ ჩაწეროთ.")
    confirmed = forms.BooleanField(label="თანხები და თარიღი ამონაწერში გადავამოწმე და ამ შეკვეთას ეკუთვნის")


def credo_bank_state(application):
    if application.bank_status is None:
        return application.get_submission_state_display()
    return f"{application.bank_status} — {describe_credo_status(application.bank_status).label}"


def credo_next_action(application):
    if application.needs_review:
        return "საჭიროა გადამოწმება. არ გაგზავნოთ და არ შექმნათ ახალი განაცხადი."
    if application.bank_status in (6, 7) or application.submission_state == "failed":
        return "ამ განაცხადით შეძენა არ დასრულდა."
    if application.bank_status == 5:
        return "ბანკმა დაფინანსების დასრულება დაადასტურა. ჩარიცხვა შეადარეთ საბანკო ამონაწერს."
    if application.bank_status == 12 and application.order_id:
        status = application.order.status
        if status == "delivered":
            return "ჩაბარებულია. დაელოდეთ კრედოს დასრულებას; დაუდასტურებელი მიღება გადაამოწმეთ ბანკთან."
        if status == "shipped":
            return "გაგზავნილია. კრედოს კაბინეტშიც მონიშნეთ გაგზავნა და დაელოდეთ ჩაბარებას."
        return "ხელმოწერილია. მოამზადეთ ნივთი; რეალური გაგზავნა ცალკე შეასრულეთ."
    return "დაელოდეთ ბანკის შემოწმებას ან მომხმარებლის ხელმოწერას. გაგზავნა ჯერ დაუშვებელია."


class CredoReadOnlyAdmin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="ბანკის მდგომარეობა")
    def bank_state(self, obj):
        return credo_bank_state(obj)

    @admin.display(description="შემდეგი მოქმედება")
    def next_action(self, obj):
        return credo_next_action(obj)


@admin.register(CredoApplication)
class CredoApplicationAdmin(CredoReadOnlyAdmin, admin.ModelAdmin):
    change_form_template = "admin/commerce/credoapplication/change_form.html"
    actions = None
    list_display = ("order_code", "requested_offer", "order_link", "requested_amount", "bank_state",
                    "needs_review", "next_action", "bank_checked_at", "is_test")
    list_filter = ("needs_review", "bank_status", "requested_offer", "is_test", "submission_state", "created_at")
    search_fields = ("order_code", "order__order_number", "public_token")
    fields = ("order_code", "public_token", "requested_offer", "order_link", "requested_amount", "currency",
              "submission_state", "bank_state", "next_action", "needs_review", "last_issue", "is_test",
              "start_attempted_at", "submitted_at", "signed_at", "funding_completed_at", "bank_checked_at",
              "merchant_fee_rate", "fee_overview", "created_at", "updated_at", "workflow_guide")
    readonly_fields = fields
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order", "statement_settlement")

    def get_urls(self):
        return [path("<path:object_id>/statement/", self.admin_site.admin_view(self.statement_view),
                     name="commerce_credoapplication_statement")] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        can_confirm = bool(obj and obj.bank_status == 5 and not obj.is_test and not obj.needs_review
            and obj.order_id and not hasattr(obj, "statement_settlement")
            and request.user.has_perm("commerce.add_credostatementsettlement"))
        return super().change_view(request, object_id, form_url, {**(extra_context or {}),
            "can_confirm_statement": can_confirm,
            "statement_url": reverse("admin:commerce_credoapplication_statement", args=[object_id])})

    def statement_view(self, request, object_id):
        obj = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_view_permission(request, obj) or not request.user.has_perm("commerce.add_credostatementsettlement"):
            raise PermissionDenied
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        form = CredoStatementForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                confirm_credo_statement(application_id=obj.pk, actor=request.user, **form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                self.log_change(request, obj, "Statement receipt confirmed; merchant pays fee.")
                return HttpResponseRedirect(reverse("admin:commerce_credoapplication_change", args=[obj.pk]))
        return TemplateResponse(request, "admin/commerce/credoapplication/statement.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "original": obj,
            "title": "კრედოს ჩარიცხვის დადასტურება ამონაწერით", "form": form,
            "expected": expected_credo_amounts(obj),
            "cancel_url": reverse("admin:commerce_credoapplication_change", args=[obj.pk]),
        })

    @admin.display(description="ბანკის საკომისიო და ჩარიცხვა")
    def fee_overview(self, obj):
        expected = expected_credo_amounts(obj)
        actual = getattr(obj, "statement_settlement", None)
        text = f"მოსალოდნელი საკომისიო: {expected['fee']:.2f} ₾; მოსალოდნელი ჩარიცხვა: {expected['net']:.2f} ₾. მომხმარებლის დამატება: 0.00 ₾."
        if actual:
            return text + f" ამონაწერით: საკომისიო {actual.fee_amount:.2f} ₾, ჩარიცხვა {actual.net_amount:.2f} ₾, თარიღი {actual.received_on:%d.%m.%Y}."
        return text + " ამონაწერით ჩარიცხვა ჯერ არ დადასტურებულა."

    @admin.display(description="შეკვეთა")
    def order_link(self, obj):
        if not obj.order_id:
            return "შეკვეთა ჯერ არ შექმნილა"
        return format_html('<a href="{}">{}</a>', reverse("admin:commerce_order_change", args=[obj.order_id]), obj.order.order_number)

    @admin.display(description="მუშაობის წესი")
    def workflow_guide(self, obj):
        return format_html(
            '{} <a href="{}" target="_blank" rel="noopener noreferrer">{}</a> {}',
            "Wingo-ს გზავნილი და კრედოს კაბინეტში გაგზავნის მონიშვნა ორი ცალკე მოქმედებაა.",
            "https://merchants.credo.ge/landing/authorization", "კრედოს მერჩანტის კაბინეტი",
            "ჩაბარების მტკიცებულება შეინახეთ. მიღების დაუდასტურებლობაზე დაუკავშირდით ბანკს შეთანხმებული არხით. "
            "გაუქმება/დაბრუნება ჯერ ბანკთან უნდა შეთანხმდეს; ამ გვერდიდან სტატუსის შეცვლა ან თანხის დაბრუნება შეუძლებელია.",
        )


class CredoApplicationInline(CredoReadOnlyAdmin, admin.TabularInline):
    model = CredoApplication
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("order_code", "requested_offer", "bank_state", "next_action", "needs_review", "bank_checked_at")
    readonly_fields = fields


@admin.register(CredoStatementSettlement)
class CredoStatementSettlementAdmin(CredoReadOnlyAdmin, admin.ModelAdmin):
    actions = None
    list_display = ("application", "gross_amount", "fee_amount", "net_amount", "received_on", "created_at")
    fields = ("application", "payment", "gross_amount", "fee_amount", "net_amount", "received_on",
              "statement_reference", "confirmed_by", "created_at")
    readonly_fields = fields
    list_select_related = ("application", "payment")
