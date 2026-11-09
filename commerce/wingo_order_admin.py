from io import BytesIO

from django import forms
from django.contrib import admin, messages
from django.http import FileResponse, Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import WingoShipment
from .wingo import WingoError
from .wingo_shipments import can_submit, get_shipment_label, recover_submission, submit_shipment


class WingoPrepareForm(forms.Form):
    parcel_count = forms.IntegerField(label="შეფუთვების რაოდენობა", min_value=1, max_value=1000, initial=1,
        help_text="მიუთითეთ ყუთების ან ცალკე შეფუთული ამანათების რაოდენობა, და არა პროდუქტების რაოდენობა.",
        error_messages={"required": "მიუთითეთ შეფუთვების რაოდენობა.", "invalid": "მიუთითეთ მთელი რიცხვი.",
                        "min_value": "მინიმუმ ერთი შეფუთვაა საჭირო.", "max_value": "მაქსიმუმ 1000 შეფუთვაა დასაშვები."})
    prepared = forms.BooleanField(label="ნივთები შემოწმებულია, შეფუთულია და მზადაა კურიერისთვის",
        error_messages={"required": "დაადასტურეთ ნივთების შემოწმება და მომზადება."})


class OrderWingoAdminMixin:
    def get_urls(self):
        routes = [("submit", self.wingo_submit_view), ("recover", self.wingo_recover_view),
                  ("label", self.wingo_label_view)]
        return [path(f"<path:object_id>/wingo-{action}/", self.admin_site.admin_view(view),
                     name=f"commerce_order_wingo_{action}") for action, view in routes] + super().get_urls()

    def get_fieldsets(self, request, obj=None):
        fields = super().get_fieldsets(request, obj)
        return fields if obj and obj.delivery_provider == "wingo" else [row for row in fields if row[0] != "Wingo მიწოდება"]

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        context = dict(extra_context or {})
        order = self.get_object(request, object_id) if object_id else None
        if order and order.delivery_provider == "wingo" and self.has_change_permission(request, order):
            shipment = WingoShipment.objects.filter(order=order).first()
            context["show_wingo_submit"] = can_submit(order)
            context["show_wingo_recover"] = bool(shipment and shipment.state in {"unknown", "submitting"})
            context["show_wingo_label"] = bool(shipment and shipment.state == "created" and shipment.provider_order_id)
            for action in ("submit", "recover", "label"):
                context[f"wingo_{action}_url"] = reverse(f"admin:commerce_order_wingo_{action}", args=[order.pk])
        return super().changeform_view(request, object_id, form_url, context)

    @admin.display(description="გზავნილი")
    def wingo_overview(self, obj):
        shipment = WingoShipment.objects.filter(order=obj).first()
        if shipment is None:
            return "გზავნილი ჯერ არ შექმნილა. ნივთების მომზადების შემდეგ გამოიყენეთ „Wingo-ში გაგზავნა“."
        price = f"{shipment.booked_price:.2f} ₾" if shipment.booked_price is not None else "ჯერ არ დადასტურებულა"
        difference = (f"{shipment.booked_price - obj.carrier_delivery_cost:+.2f} ₾"
                      if shipment.booked_price is not None else "ჯერ არ დადასტურებულა")
        return format_html(
            "<p><strong>{}</strong></p><p>გზავნილის ნომერი: {}<br>შეფუთვები: {}<br>"
            "მომხმარებლის მიერ გადახდილი მიტანა: {} ₾<br>შენახული საკურიერო ტარიფი: {} ₾<br>"
            "Wingo-ში დაფიქსირებული ფასი: {}<br>სხვაობა ტარიფთან: {}<br>"
            "გზავნილის დადასტურების დრო: {}</p><p>{}</p>",
            shipment.get_state_display(), shipment.tracking_number or "—", shipment.parcel_count,
            obj.delivery_price, obj.carrier_delivery_cost, price, difference,
            shipment.submitted_at or "—", shipment.last_error)

    def _wingo_order(self, request, object_id):
        order = self._get_action_order(request, object_id)
        if order.delivery_provider != "wingo":
            raise Http404
        return order

    def _wingo_action(self, request, order, *, title, action, form=None, recovery=False):
        return TemplateResponse(request, "admin/commerce/order/wingo_action.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "original": order,
            "title": title, "action": action, "form": form, "recovery": recovery,
            "cancel_url": reverse("admin:commerce_order_change", args=[order.pk]),
        })

    def wingo_submit_view(self, request, object_id):
        order = self._wingo_order(request, object_id)
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        if not can_submit(order):
            self.message_user(request, "გაგზავნა შეუძლებელია. გადაამოწმეთ გადახდა და არსებული გზავნილის შედეგი.", messages.WARNING)
            return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        form = WingoPrepareForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                shipment = submit_shipment(order.pk, **form.cleaned_data)
            except WingoError as exc:
                if not can_submit(order):
                    self.message_user(request, str(exc), messages.WARNING)
                    return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
                form.add_error(None, str(exc))
            else:
                self.log_change(request, order, "Wingo-ს გზავნილი შექმნილია.")
                self.message_user(request, f"გზავნილი შექმნილია. ნომერი: {shipment.tracking_number}")
                return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        return self._wingo_action(request, order, title="Wingo-ში გაგზავნა", action="Wingo-ში გაგზავნის დადასტურება", form=form)

    def wingo_recover_view(self, request, object_id):
        order = self._wingo_order(request, object_id)
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        if request.method == "POST":
            try:
                shipment = recover_submission(order.pk)
            except WingoError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            else:
                self.log_change(request, order, "არსებული Wingo გზავნილი დაუკავშირდა შეკვეთას.")
                self.message_user(request, f"არსებული გზავნილი დადასტურდა: {shipment.tracking_number}. ახალი არ შექმნილა.")
            return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        return self._wingo_action(request, order, title="Wingo-ში გაგზავნის შედეგის გადამოწმება",
                                  action="არსებული გზავნილის მოძებნა", recovery=True)

    def wingo_label_view(self, request, object_id):
        order = self._wingo_order(request, object_id)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        size = request.GET.get("size", "a4")
        if size not in {"a4", "small"}:
            raise Http404
        try:
            pdf = get_shipment_label(order.pk, size=size)
        except WingoError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        response = FileResponse(BytesIO(pdf), content_type="application/pdf",
            as_attachment=request.GET.get("download") == "1", filename=f"wingo-order-{order.pk}-{size}.pdf")
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response
