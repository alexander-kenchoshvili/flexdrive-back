from io import BytesIO

from django import forms
from django.contrib import admin, messages
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from .models import RedcapReferenceData, RedcapShipment
from .redcap import LABEL_SIZES, RedcapClient, RedcapError
from .redcap_shipments import can_submit, cancel_shipment, recover_submission, submit_shipment
from .redcap_tracking import sync_shipments


class RedcapPrepareForm(forms.Form):
    parcel_count = forms.IntegerField(label="შეფუთული ამანათების რაოდენობა", min_value=1, max_value=1000, initial=1)
    prepared = forms.BooleanField(label="ნივთები შემოწმებულია, შეფუთულია და მზადაა კურიერისთვის")


class RedcapCancelForm(forms.Form):
    reason = forms.CharField(label="გაუქმების მიზეზი", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class OrderRedcapAdminMixin:
    def get_urls(self):
        routes = [
            ("redcap-submit", self.redcap_submit_view),
            ("redcap-recover", self.redcap_recover_view),
            ("redcap-cancel", self.redcap_cancel_view),
            ("redcap-tracking", self.redcap_tracking_view),
            ("redcap-label", self.redcap_label_view),
        ]
        return [path(f"<path:object_id>/{route}/", self.admin_site.admin_view(view),
                     name=f"commerce_order_{route.replace('-', '_')}") for route, view in routes] + super().get_urls()

    def get_fieldsets(self, request, obj=None):
        fields = super().get_fieldsets(request, obj)
        if not obj or obj.delivery_provider != "redcap":
            return [row for row in fields if row[0] != "RedCap მიწოდება"]
        return fields

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        context = dict(extra_context or {})
        order = self.get_object(request, object_id) if object_id else None
        if order and order.delivery_provider == "redcap":
            shipment = RedcapShipment.objects.filter(order=order).first()
            context["show_redcap_submit"] = can_submit(order)
            context["show_redcap_recover"] = bool(shipment and shipment.state in {"unknown", "submitting"})
            context["show_redcap_tracking"] = bool(shipment and shipment.tracking_number and shipment.state in {"created", "cancel_unknown", "cancelling"})
            context["show_redcap_cancel"] = bool(shipment and shipment.state == "created")
            context["show_redcap_label"] = bool(shipment and shipment.state == "created" and shipment.tracking_number)
            for action in ("submit", "recover", "tracking", "cancel", "label"):
                context[f"redcap_{action}_url"] = reverse(f"admin:commerce_order_redcap_{action}", args=[order.pk])
        return super().changeform_view(request, object_id, form_url, context)

    @admin.display(description="გზავნილი")
    def redcap_overview(self, obj):
        shipment = RedcapShipment.objects.filter(order=obj).first()
        if shipment is None:
            return "გზავნილი ჯერ არ შექმნილა. ნივთების მომზადების შემდეგ გამოიყენეთ გაგზავნის ღილაკი."
        snapshot = RedcapReferenceData.objects.filter(pk=1).first()
        labels = {row["key"]: row["name"] for row in snapshot.statuses} if snapshot else {}
        history = format_html_join("", "<li>{}: {}</li>", (
            (row.get("observed_at", "—"), labels.get(row.get("status"), row.get("status") or "—"))
            for row in shipment.tracking_history[-20:]
        ))
        return format_html(
            "<p><strong>{}</strong></p><p>თრექინგი: {}<br>ამანათები: {}<br>"
            "RedCap-ის ფასი: {}<br>კურიერის სტატუსი: {}<br>ბოლო შემოწმება: {}</p><p>{}</p><p>{}</p>"
            "<p>ბოლო 20 დაკვირვება (შემოწმების დრო):</p><ul>{}</ul>",
            shipment.get_state_display(), shipment.tracking_number or "—", shipment.parcel_count,
            shipment.booked_price if shipment.booked_price is not None else "შესამოწმებელია",
            labels.get(shipment.carrier_status, shipment.carrier_status or "—"), shipment.tracking_checked_at or "—",
            shipment.last_error, shipment.tracking_error, history,
        )

    def _redcap_order(self, request, object_id):
        order = self._get_action_order(request, object_id)
        if order.delivery_provider != "redcap":
            raise Http404
        return order

    def _redcap_action(self, request, order, *, title, action, form=None):
        return TemplateResponse(request, "admin/commerce/order/redcap_action.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "original": order, "title": title, "action": action, "form": form,
            "cancel_url": reverse("admin:commerce_order_change", args=[order.pk]),
        })

    def redcap_submit_view(self, request, object_id):
        order = self._redcap_order(request, object_id)
        form = RedcapPrepareForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                shipment = submit_shipment(order.pk, **form.cleaned_data)
            except RedcapError as exc:
                form.add_error(None, str(exc))
            else:
                self.log_change(request, order, "RedCap-ის გზავნილი შექმნილია.")
                self.message_user(request, f"გზავნილი შექმნილია. თრექინგი: {shipment.tracking_number}")
                return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        return self._redcap_action(request, order, title="RedCap-ში გზავნილის შექმნა", action="შექმნა", form=form)

    def redcap_recover_view(self, request, object_id):
        order = self._redcap_order(request, object_id)
        if request.method == "POST":
            try:
                recover_submission(order.pk)
            except RedcapError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            else:
                self.message_user(request, "არსებული RedCap გზავნილი დაუკავშირდა შეკვეთას; ახალი არ შექმნილა.")
            return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        return self._redcap_action(request, order, title="გაგზავნის შედეგის გადამოწმება", action="არსებული გზავნილის მოძებნა")

    def redcap_cancel_view(self, request, object_id):
        order = self._redcap_order(request, object_id)
        form = RedcapCancelForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                cancel_shipment(order.pk, **form.cleaned_data)
            except RedcapError as exc:
                form.add_error(None, str(exc))
            else:
                self.log_change(request, order, "RedCap-ის გზავნილი გაუქმებულია; გადახდა და მარაგი არ შეცვლილა.")
                self.message_user(request, "RedCap-ის გზავნილი გაუქმდა. თანხა და მარაგი არ შეცვლილა.")
                return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        return self._redcap_action(request, order, title="RedCap გზავნილის გაუქმება", action="გზავნილის გაუქმება", form=form)

    def redcap_tracking_view(self, request, object_id):
        order = self._redcap_order(request, object_id)
        if request.method == "POST":
            counts = sync_shipments([order.pk])
            problematic = counts["failed"] or counts["review"]
            self.message_user(request, "თრექინგი შენახულია; გადაამოწმეთ შენიშვნა." if problematic else "თრექინგი განახლდა.",
                              messages.WARNING if problematic else messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        return self._redcap_action(request, order, title="RedCap სტატუსის განახლება", action="სტატუსის განახლება")

    def redcap_label_view(self, request, object_id):
        order = self._redcap_order(request, object_id)
        shipment = RedcapShipment.objects.filter(order=order, state="created", tracking_number__isnull=False).first()
        size = request.GET.get("size", "a4")
        if shipment is None or size not in LABEL_SIZES:
            raise Http404
        try:
            pdf = RedcapClient.from_settings().get_label(shipment.tracking_number, size=size)
        except RedcapError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return HttpResponseRedirect(reverse("admin:commerce_order_change", args=[order.pk]))
        response = FileResponse(BytesIO(pdf), content_type="application/pdf",
            as_attachment=request.GET.get("download") == "1", filename=f"redcap-order-{order.pk}.pdf")
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response
