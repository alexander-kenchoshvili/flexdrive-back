"""Single, read-only accountant ledger; dedicated role remains deferred."""
from decimal import Decimal
from urllib.parse import urlencode
from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from .accounting_reports import ReportPeriod, TBILISI
from .accounting_ledger import build_ledger, visible_columns
from .accounting_access import can_view_accounting


class AccountingFilterForm(forms.Form):
    period_mode = forms.ChoiceField(label="პერიოდი", choices=(("days", "დღეების მიხედვით"), ("months", "თვეების მიხედვით")))
    start = forms.DateField(label="თარიღიდან", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="თარიღამდე", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    start_month = forms.CharField(label="თვიდან", required=False, max_length=7, widget=forms.TextInput(attrs={"type": "month"}))
    end_month = forms.CharField(label="თვემდე", required=False, max_length=7, widget=forms.TextInput(attrs={"type": "month"}))
    status = forms.ChoiceField(label="შეკვეთები", choices=(("paid", "წარმატებული"), ("refunded", "დაბრუნებული"), ("all", "ყველა")))
    sku = forms.CharField(label="პროდუქტის სახელი ან SKU", required=False, max_length=255)

    show_purchase = forms.BooleanField(label="შესაძენი ფასების ჩვენება", required=False)

    def clean(self):
        data = super().clean()
        try:
            if data.get("period_mode") == "months":
                self.period = ReportPeriod.months(data.get("start_month"), data.get("end_month"))
            else:
                self.period = ReportPeriod(data["start"], data["end"])
        except (ValueError, KeyError):
            raise forms.ValidationError("მიუთითეთ სწორი საწყისი და ბოლო პერიოდი.")
        return data


def display(value):
    if value is None:
        return "—"
    return f"{value:,.2f}" if isinstance(value, Decimal) else value


def order_block(group, columns):
    rows = group["rows"]
    first = rows[0]
    subtotal = ["პროდუქტების ჯამი", None, sum(r[4] for r in rows), None, None]
    for column in range(7, 11):
        values = [r[column] for r in rows]
        subtotal.append(None if any(v is None for v in values) else sum(values, Decimal(0)))
    return {"event_id": group["event_id"], "number": first[1], "date": first[0], "status": first[15],
            "line_count": len(rows), "unit_count": sum(abs(r[4]) for r in rows),
            "buyer_type": first[16], "buyer_vat": first[17],
            "is_company": first[16] == "იურიდიული პირი",
            "rows": [[display(row[i]) for i in columns] for row in rows],
            "subtotal": [display(subtotal[i - 2]) for i in columns],
            "delivery": [(label, display(first[index])) for index, label in (
                (11, "თბილისის მიტანა"), (12, "რეგიონის მიტანა"), (13, "ბუფერი"), (14, "შეკვეთის სრული თანხა"))]}


@require_GET
def accounting_view(request):
    if not can_view_accounting(request.user):
        raise PermissionDenied
    today = timezone.localdate(timezone=TBILISI)
    data = {"start": today.replace(day=1).isoformat(), "end": today.isoformat(), "status": "paid",
            "period_mode": "days", "start_month": today.strftime("%Y-%m"), "end_month": today.strftime("%Y-%m"), "sku": "", "show_purchase": ""}
    data.update({k: request.GET[k] for k in data if k in request.GET})
    form = AccountingFilterForm(data)
    context = {**admin.site.each_context(request), "title": "ბუღალტერია", "form": form}
    if form.is_valid():
        try:
            report = build_ledger(form.period, form.cleaned_data["status"], sku=form.cleaned_data["sku"])
        except ValueError:
            context["error"] = "შეამცირეთ არჩეული პერიოდი ან გადაამოწმეთ მონაცემები ადმინისტრატორთან."
        else:
            report["show_purchase"] = form.cleaned_data["show_purchase"]
            columns = visible_columns(report["show_purchase"])
            product_columns = [i for i in columns if 2 <= i <= 10]
            total_columns = [i for i in columns if i == 4 or 7 <= i <= 14]
            if request.GET.get("export") == "xlsx":
                from .accounting_export import export_response
                return export_response(report)
            page = Paginator(report["groups"], 20).get_page(request.GET.get("page"))
            context.update(period=form.period, status=report["status"], sku=report["sku"], order_count=report["order_count"],
                headers=report["headers"], rows=[[display(v) for v in row] for group in page for row in group["rows"]],
                groups=[order_block(group, product_columns) for group in page],
                product_headers=[report["headers"][i] for i in product_columns],
                total_headers=[report["headers"][i] for i in total_columns],
                total_values=[display(report["totals"][i]) for i in total_columns],
                totals=[display(v) for v in report["totals"]], page=page,
                export_url="?" + urlencode({**data, "export": "xlsx"}),
                previous_url="?" + urlencode({**data, "page": page.previous_page_number()}) if page.has_previous() else None,
                next_url="?" + urlencode({**data, "page": page.next_page_number()}) if page.has_next() else None)
    return TemplateResponse(request, "admin/commerce/accounting/report.html", context)
