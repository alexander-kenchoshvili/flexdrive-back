from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from .models import RedcapReferenceData, RedcapSyncReport
from .redcap import RedcapError
from .redcap_references import SERVICE_LABELS, refresh_redcap_references


@admin.register(RedcapReferenceData)
class RedcapReferenceDataAdmin(admin.ModelAdmin):
    change_list_template = "admin/commerce/redcap_references/change_list.html"
    list_display = ("category", "synced_at", "band_count")
    readonly_fields = ("category", "synced_at", "tariff_table", "location_table", "revision")
    fields = readonly_fields
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [path("refresh/", self.admin_site.admin_view(self.refresh_view),
                     name="commerce_redcapreferencedata_refresh")] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        extra_context["can_refresh"] = self.has_change_permission(request)
        extra_context["refresh_url"] = reverse("admin:commerce_redcapreferencedata_refresh")
        return super().changelist_view(request, extra_context=extra_context)

    def refresh_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        cancel_url = reverse("admin:commerce_redcapreferencedata_changelist")
        if request.method == "POST":
            try:
                snapshot = refresh_redcap_references()
            except RedcapError as exc:
                self.message_user(request, str(exc), level=messages.ERROR)
            else:
                self.message_user(request, f"RedCap-ის ტარიფები განახლდა: {len(snapshot.weights)} წონის დიაპაზონი.")
            return HttpResponseRedirect(cancel_url)
        return TemplateResponse(request, "admin/commerce/redcap_references/refresh.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": "RedCap-ის ტარიფების განახლება", "cancel_url": cancel_url,
        })

    @admin.display(description="წონის დიაპაზონები")
    def band_count(self, obj):
        return len(obj.weights)

    @admin.display(description="ტარიფები, დღგ-ს ჩათვლით")
    def tariff_table(self, obj):
        services = tuple(SERVICE_LABELS)
        headers = format_html_join("", "<th>{}</th>", ((SERVICE_LABELS[key],) for key in services))
        rows = format_html_join("", "<tr><th>{}–{} კგ</th>{}</tr>", (
            (row["from"], row["to"], format_html_join("", "<td>{} ₾</td>",
                ((row["prices"][key],) for key in services))) for row in obj.weights
        ))
        return format_html('<div style="overflow-x:auto"><table><thead><tr><th>წონა</th>{}</tr>'
                           '</thead><tbody>{}</tbody></table></div>'
                           '<p>ზუსტი ზედა ზღვარი ამავე დიაპაზონში შედის. მომსახურების სახელი '
                           'ჩაბარების თარიღის დაპირება არ არის.</p>', headers, rows)

    @admin.display(description="საკურიერო ზონები")
    def location_table(self, obj):
        return format_html("<ul>{}</ul>", format_html_join("", "<li>{} — {}</li>",
                           ((row["name"], row["zone_slug"]) for row in obj.locations)))


@admin.register(RedcapSyncReport)
class RedcapSyncReportAdmin(admin.ModelAdmin):
    list_display = ("started_at", "source", "status", "summary", "finished_at")
    list_filter = ("source", "status", "started_at")
    readonly_fields = ("started_at", "finished_at", "source", "status", "summary", "details")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
