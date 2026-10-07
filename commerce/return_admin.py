"""Georgian controls for the return workflow, not a translation of the admin."""
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from .bog_payments import BogPaymentError
from .bog_refunds import can_request_bog_full_refund, request_bog_full_refund
from .models import OrderReturn, ReturnDisposition, ReturnReceiptStatus
from .returns import has_external_items, prepare_order_return, receive_order_return


class PredispatchRefundForm(forms.Form):
    disposition = forms.ChoiceField(
        label="მომწოდებლისგან ეს შეკვეთა უკვე შეძენილია?", widget=forms.RadioSelect,
        choices=[(ReturnDisposition.NOT_PURCHASED, "არა, მომწოდებლისგან ჯერ არ შემიძენია"),
                 (ReturnDisposition.ON_HAND, "უკვე შეძენილია და ჩემთანაა — გასაყიდად ვარგისია")],
        error_messages={"required": "აირჩიეთ ნივთების მდგომარეობა.", "invalid_choice": "აირჩიეთ მითითებული ვარიანტი."},
    )
    not_dispatched = forms.BooleanField(
        label="ვადასტურებ, რომ შეკვეთა მომხმარებელთან არ გაგზავნილა.",
        error_messages={"required": "გაგზავნამდე დაბრუნებისთვის საჭიროა ამ პირობის დადასტურება."},
    )

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)
        case = OrderReturn.objects.filter(order=order).first()
        if case:
            self.fields["disposition"].initial = case.disposition
            self.fields["disposition"].disabled = True
            self.fields["disposition"].help_text = "ეს არჩევანი უკვე დაფიქსირებულია. განმეორებით ცდა მარაგს მეორედ არ დაამატებს."
        elif not has_external_items(order):
            self.fields["disposition"].choices = self.fields["disposition"].choices[1:]
            self.fields["disposition"].label = "შეკვეთა ჩვენი მარაგიდანაა. დაადასტურეთ ნივთების მდგომარეობა."


def predispatched_refund_view(model_admin, request, order):
    cancel_url = reverse("admin:commerce_order_change", args=[order.pk])
    customer_return = OrderReturn.objects.filter(order=order, disposition=ReturnDisposition.FROM_CUSTOMER).exists()
    data = request.POST if request.method == "POST" else None
    form = ConfirmReturnForm(data) if customer_return else PredispatchRefundForm(data, order=order)
    allowed = can_request_bog_full_refund(order)
    if request.method == "POST" and form.is_valid():
        try:
            refund = request_bog_full_refund(
                order=order, requested_by=request.user,
                disposition=ReturnDisposition.FROM_CUSTOMER if customer_return else form.cleaned_data["disposition"],
                not_dispatched=False if customer_return else form.cleaned_data["not_dispatched"],
            )
        except ValidationError as error:
            form.add_error(None, error.messages[0])
        except BogPaymentError as error:
            model_admin.message_user(request,
                ("ბანკის პასუხი ჯერ გაურკვეველია. შეამოწმეთ დაბრუნების მდგომარეობა; განმეორებით ცდა იმავე მოთხოვნას გამოიყენებს."
                 if error.retryable or error.outcome_unknown else
                 "ბანკმა თანხის დაბრუნების მოთხოვნა უარყო. ნივთების აღრიცხვა შენახულია; მიზეზის მოგვარების შემდეგ შეგიძლიათ ხელახლა სცადოთ."),
                level=messages.WARNING,
            )
            return HttpResponseRedirect(cancel_url)
        else:
            model_admin.message_user(request,
                "თანხა დაბრუნებულია." if refund.status == "refunded" else
                "თანხის დაბრუნების მოთხოვნა მიღებულია. ველოდებით ბანკის საბოლოო დადასტურებას.",
                level=messages.SUCCESS,
            )
            return HttpResponseRedirect(cancel_url)
    return TemplateResponse(request, "admin/commerce/predispatch_refund.html", {
        **model_admin.admin_site.each_context(request), "opts": model_admin.model._meta,
        "original": order, "title": f"თანხის დაბრუნება — {order.order_number}",
        "order": order, "items": order.items.all(), "form": form, "cancel_url": cancel_url,
        "allowed": allowed, "customer_return": customer_return,
    })


class ConfirmReturnForm(forms.Form):
    confirm = forms.BooleanField(
        label="ვადასტურებ მოქმედებას.",
        error_messages={"required": "მოქმედებისთვის საჭიროა დადასტურება."},
    )


class ReceiveReturnForm(ConfirmReturnForm):
    def __init__(self, *args, lines, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["confirm"].label = "ვადასტურებ, რომ ყველა ნივთი მივიღე და შევამოწმე."
        self.rows = []
        for line in lines:
            for kind, label in [("saleable", "გასაყიდად ვარგისი"), ("unsaleable", "გასაყიდად უვარგისი")]:
                self.fields[f"{kind}_{line.pk}"] = forms.IntegerField(
                    label=label, min_value=0, max_value=line.expected_quantity,
                    error_messages={"required": "მიუთითეთ რაოდენობა (ან 0).", "invalid": "მიუთითეთ მთელი რიცხვი.",
                                    "min_value": "რაოდენობა ვერ იქნება უარყოფითი.", "max_value": "რაოდენობა აღემატება დასაბრუნებელს."},
                )
            self.rows.append((line, self[f"saleable_{line.pk}"], self[f"unsaleable_{line.pk}"]))


def customer_return_view(model_admin, request, order, *, receiving=False):
    cancel_url = reverse("admin:commerce_order_change", args=[order.pk])
    case = OrderReturn.objects.filter(order=order, disposition=ReturnDisposition.FROM_CUSTOMER).first()
    lines = list(case.lines.select_related("order_item").order_by("pk")) if case else []
    data = request.POST if request.method == "POST" else None
    form = ReceiveReturnForm(data, lines=lines) if receiving else ConfirmReturnForm(data)
    title = "მიღება და შემოწმება" if receiving else "დაბრუნების დაწყება"
    allowed = bool(case and case.receipt_status == ReturnReceiptStatus.AWAITING) if receiving else bool(
        order.status in {"shipped", "delivered"} and order.payment_status == "paid" and not case
    )
    if request.method == "POST" and form.is_valid():
        try:
            if receiving:
                if not case:
                    raise ValidationError("ჯერ დაიწყეთ ნივთების დაბრუნება.")
                receive_order_return(return_case=case, actor=request.user, inspection={
                    line.pk: {kind: form.cleaned_data[f"{kind}_{line.pk}"] for kind in ("saleable", "unsaleable")}
                    for line in lines
                })
                note = "მიღება დაფიქსირებულია. მხოლოდ ვარგისი ნივთები დაემატა FlexDrive-ის მარაგს. თანხის დაბრუნება ცალკე მოქმედებით შეასრულეთ."
            else:
                prepare_order_return(order=order, disposition=ReturnDisposition.FROM_CUSTOMER, actor=request.user)
                note = "დაბრუნება დაწყებულია — ველოდებით ნივთებს. თანხა ჯერ არ დაბრუნებულა."
        except ValidationError as error:
            form.add_error(None, error.messages[0])
        else:
            model_admin.message_user(request, note, level=messages.SUCCESS)
            return HttpResponseRedirect(cancel_url)
    return TemplateResponse(request, "admin/commerce/customer_return.html", {
        **model_admin.admin_site.each_context(request), "opts": model_admin.model._meta,
        "original": order, "order": order, "title": title, "form": form,
        "receiving": receiving, "allowed": allowed, "cancel_url": cancel_url, "items": order.items.all(),
    })
