from collections import Counter

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from .models import WingoReferenceData
from .wingo import WingoError
from .wingo_references import TARIFF_LABELS, refresh_wingo_references


@admin.register(WingoReferenceData)
class WingoReferenceDataAdmin(admin.ModelAdmin):
    change_list_template = "admin/commerce/wingo_references/change_list.html"
    change_form_template = "admin/commerce/wingo_references/change_form.html"
    list_display = ("snapshot_name", "synced_at", "band_count", "region_count", "locality_count")
    readonly_fields = ("account_mode", "api_base_url", "synced_at", "tariff_table", "reference_summary", "revision")
    fields = readonly_fields
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _url(self, suffix):
        return reverse(f"{self.admin_site.name}:commerce_wingoreferencedata_{suffix}")

    def get_urls(self):
        return [path("refresh/", self.admin_site.admin_view(self.refresh_view),
                     name="commerce_wingoreferencedata_refresh")] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        context = dict(extra_context or {})
        context.update(can_refresh=self.has_change_permission(request), refresh_url=self._url("refresh"))
        return super().changelist_view(request, extra_context=context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method == "POST":
            raise PermissionDenied
        context = dict(extra_context or {})
        context.update(show_save=False, show_save_and_continue=False, show_save_and_add_another=False,
                       show_save_as_new=False, can_refresh=self.has_change_permission(request),
                       refresh_url=self._url("refresh"), back_url=self._url("changelist"),
                       title="Wingo-ს ტარიფები")
        return super().changeform_view(request, object_id, form_url, context)

    def refresh_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        cancel_url = self._url("changelist")
        if request.method == "POST":
            try:
                snapshot = refresh_wingo_references()
            except WingoError as exc:
                self.message_user(request, str(exc), level=messages.ERROR)
            else:
                self.message_user(request,
                    f"Wingo-ს მონაცემები განახლდა ({snapshot.get_account_mode_display()}): "
                    f"{len(snapshot.tariffs)} წონის დიაპაზონი, {len(snapshot.localities)} დასახლება.")
            return HttpResponseRedirect(cancel_url)
        return TemplateResponse(request, "admin/commerce/wingo_references/refresh.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": "Wingo-ს მონაცემების განახლება", "cancel_url": cancel_url,
        })

    @admin.display(description="ანგარიში")
    def snapshot_name(self, obj):
        return str(obj)

    @admin.display(description="წონის დიაპაზონები")
    def band_count(self, obj):
        return len(obj.weight_ranges)

    @admin.display(description="რეგიონები")
    def region_count(self, obj):
        return len(obj.regions)

    @admin.display(description="დასახლებები")
    def locality_count(self, obj):
        return len(obj.localities)

    @admin.display(description="Wingo-ს ტარიფები")
    def tariff_table(self, obj):
        headers = format_html_join("", "<th>{}</th>", ((label,) for label in TARIFF_LABELS.values()))
        weights = {row["id"]: row for row in obj.weight_ranges}
        rows = format_html_join("", "<tr><th>{}–{} კგ</th>{}<td>{}</td><td>{}</td></tr>", (
            (weights[row["weight_range_id"]]["min_weight"], weights[row["weight_range_id"]]["max_weight"],
             format_html_join("", "<td>{} ₾</td>", ((row["prices"][key],) for key in TARIFF_LABELS)),
             "პირადი" if row["is_custom"] else "საერთო", "დამალულია" if row["hidden"] else "ჩანს")
            for row in obj.tariffs
        ))
        return format_html(
            '<div style="overflow-x:auto"><table><thead><tr><th>წონა</th>{}'
            '<th>ტარიფის წყარო</th><th>Wingo-ში ჩვენება</th></tr></thead><tbody>{}</tbody></table></div>'
            '<p>ფასები მიღებულია Wingo-ს ანგარიშიდან. მომსახურების სახელები ჩაბარების '
            'კონკრეტულ თარიღს არ ნიშნავს. ჩექაუთის ფასი ამ შენახული ტარიფებით ითვლება.</p>', headers, rows)

    @admin.display(description="შენახული ცნობარები")
    def reference_summary(self, obj):
        counts = Counter(row["region_id"] for row in obj.localities)
        operational = Counter(row["region_id"] for row in obj.localities if row["operational"])
        rows = format_html_join("", "<tr><th>{}</th><td>{}</td><td>{}</td></tr>", (
            (region["name"], counts[region["id"]], operational[region["id"]]) for region in obj.regions
        ))
        types = format_html_join(", ", "{}", ((row["name"],) for row in obj.delivery_types))
        return format_html(
            '<p>მომსახურებები: {}.</p><table><thead><tr><th>რეგიონი</th><th>დასახლებები</th>'
            '<th>Wingo-ში ოპერაციულად მონიშნული</th></tr></thead><tbody>{}</tbody></table>'
            '<p>დასახლებების მიტანის დღეები და ხელმისაწვდომობის მონიშვნები შენახულია ცნობარში. '
            'მომსახურების კონკრეტული დღის არქონა შეკვეთის მიღების აკრძალვას არ ნიშნავს.</p>', types, rows)
