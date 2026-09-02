import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache, partial
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from svglib.svglib import svg2rlg

from .models import (
    OrderPaymentMethod,
    OrderPaymentStatus,
    OrderReceipt,
    PaymentTransactionStatus,
)


RECEIPT_TOKEN_SALT = "commerce.order-receipt.v1"
RECEIPT_TOKEN_HEADER = "X-Receipt-Token"
RECEIPT_TOKEN_MAX_LENGTH = 4096
RECEIPT_SCHEMA_VERSION = 1

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "receipt"
FONT_DIR = ASSET_DIR / "fonts"
LOGO_PATH = ASSET_DIR / "flexdrive-logo-horizontal.svg"

FONT_REGULAR = "FlexDriveReceipt-Regular"
FONT_SEMIBOLD = "FlexDriveReceipt-Semibold"
FONT_BOLD = "FlexDriveReceipt-Bold"
FONT_EXTRABOLD = "FlexDriveReceipt-Extrabold"

INK = colors.HexColor("#111827")
SECONDARY = colors.HexColor("#3F4A3A")
MUTED = colors.HexColor("#66705F")
RULE = colors.HexColor("#D7E0CD")
SOFT = colors.HexColor("#F3F6EE")
ACCENT = colors.HexColor("#4F6F1F")
ACCENT_DARK = colors.HexColor("#2F4312")
SUCCESS = colors.HexColor("#167A3A")
WHITE = colors.white
PREVIEW = colors.HexColor("#8B3B2F")


class ReceiptUnavailableError(Exception):
    def __init__(self, code, detail, *, status_code=409):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class ReceiptAccessError(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReceiptEligibility:
    is_preview: bool
    payment: object | None


def _money(value):
    return f"{Decimal(str(value or 0)).quantize(Decimal('0.01')):.2f}"


def _safe_text(value):
    return str(value or "").strip()


def _snapshot_datetime(value):
    if not value:
        return ""
    return value.isoformat()


def _display_datetime(value):
    if not value:
        return "-"
    parsed = value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    return parsed.strftime("%d.%m.%Y · %H:%M")


def _payment_method_label(method):
    if method == OrderPaymentMethod.CARD:
        return "საბანკო ბარათი"
    return "ნაღდი ანგარიშსწორება"


def _payment_status_label(status, *, is_preview=False):
    if is_preview:
        return "სატესტო რეჟიმი · გადახდა ჩაბარებისას"
    labels = {
        OrderPaymentStatus.PAID: "გადახდილია",
        OrderPaymentStatus.AUTHORIZED: "ავტორიზებულია",
        OrderPaymentStatus.PENDING: "მოლოდინშია",
        OrderPaymentStatus.FAILED: "ვერ შესრულდა",
        OrderPaymentStatus.CANCELLED: "გაუქმებულია",
        OrderPaymentStatus.REFUND_PENDING: "დაბრუნების პროცესშია",
        OrderPaymentStatus.REFUNDED: "დაბრუნებულია",
    }
    return labels.get(status, _safe_text(status))


def get_receipt_eligibility(order):
    if not settings.ORDER_RECEIPTS_ENABLED:
        raise ReceiptUnavailableError(
            "receipt_disabled",
            "ელექტრონული ჩეკი ამ მომენტში მიუწვდომელია.",
        )

    if (
        order.payment_method == OrderPaymentMethod.CARD
        and order.payment_status == OrderPaymentStatus.PAID
    ):
        payment = (
            order.payment_transactions.filter(
                payment_method=OrderPaymentMethod.CARD,
                status=PaymentTransactionStatus.PAID,
            )
            .order_by("-captured_at", "-created_at", "-id")
            .first()
        )
        if payment is None:
            raise ReceiptUnavailableError(
                "receipt_paid_transaction_missing",
                "გადახდის დამადასტურებელი ტრანზაქცია ვერ მოიძებნა.",
            )
        return ReceiptEligibility(is_preview=False, payment=payment)

    if (
        settings.ORDER_RECEIPT_ALLOW_COD_PREVIEW
        and order.payment_method == OrderPaymentMethod.CASH_ON_DELIVERY
    ):
        return ReceiptEligibility(is_preview=True, payment=None)

    raise ReceiptUnavailableError(
        "receipt_not_eligible",
        "ელექტრონული ჩეკი ხელმისაწვდომია მხოლოდ წარმატებით გადახდილ საბარათე შეკვეთაზე.",
    )


def _seller_snapshot():
    return {
        "name": _safe_text(settings.ORDER_RECEIPT_SELLER_NAME),
        "tax_id": _safe_text(settings.ORDER_RECEIPT_SELLER_TAX_ID),
        "address": _safe_text(settings.ORDER_RECEIPT_SELLER_ADDRESS),
        "phone": _safe_text(settings.ORDER_RECEIPT_SELLER_PHONE),
        "email": _safe_text(settings.ORDER_RECEIPT_SELLER_EMAIL),
        "website": _safe_text(settings.ORDER_RECEIPT_SELLER_WEBSITE),
    }


def _payment_snapshot(order, eligibility):
    payment = eligibility.payment
    if payment is None:
        return {
            "method": order.payment_method,
            "status": order.payment_status,
            "status_label": _payment_status_label(
                order.payment_status,
                is_preview=True,
            ),
            "amount": _money(order.total),
            "currency": "GEL",
            "reference": "",
            "paid_at": "",
        }

    reference = (
        _safe_text(payment.provider_transaction_id)
        or _safe_text(payment.provider_order_id)
        or str(payment.public_token)
    )
    return {
        "method": order.payment_method,
        "status": order.payment_status,
        "status_label": _payment_status_label(order.payment_status),
        "amount": _money(payment.amount),
        "currency": _safe_text(payment.currency) or "GEL",
        "reference": reference,
        "paid_at": _snapshot_datetime(payment.captured_at or payment.updated_at),
    }


def build_receipt_snapshot(order, eligibility):
    items = [
        {
            "name": _safe_text(item.product_name),
            "sku": _safe_text(item.sku),
            "unit_price": _money(item.unit_price),
            "quantity": int(item.quantity),
            "line_total": _money(item.line_total),
        }
        for item in order.items.all().order_by("id")
    ]
    buyer_name = " ".join(
        value
        for value in (_safe_text(order.first_name), _safe_text(order.last_name))
        if value
    )

    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "template_version": settings.ORDER_RECEIPT_TEMPLATE_VERSION,
        "is_preview": eligibility.is_preview,
        "issued_at": _snapshot_datetime(timezone.now()),
        "seller": _seller_snapshot(),
        "buyer": {
            "type": order.buyer_type,
            "name": buyer_name,
            "company_name": _safe_text(order.company_name),
            "company_tax_id": _safe_text(order.company_identification_code),
            "phone": _safe_text(order.phone),
            "email": _safe_text(order.email),
            "address": _safe_text(order.address_line),
            "city": _safe_text(order.delivery_city_name or order.city),
            "region": _safe_text(order.delivery_region_name),
        },
        "order": {
            "public_token": str(order.public_token),
            "number": _safe_text(order.order_number),
            "created_at": _snapshot_datetime(order.created_at),
            "subtotal": _money(order.subtotal),
            "delivery_price": _money(order.delivery_price),
            "total": _money(order.total),
            "currency": "GEL",
            "total_quantity": sum(item["quantity"] for item in items),
        },
        "payment": _payment_snapshot(order, eligibility),
        "items": items,
    }


def _snapshot_hash(snapshot):
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@transaction.atomic
def get_or_create_order_receipt(order):
    existing = OrderReceipt.objects.select_for_update().filter(order=order).first()
    if existing is not None:
        return existing

    eligibility = get_receipt_eligibility(order)
    snapshot = build_receipt_snapshot(order, eligibility)
    receipt, _ = OrderReceipt.objects.get_or_create(
        order=order,
        defaults={
            "template_version": settings.ORDER_RECEIPT_TEMPLATE_VERSION,
            "document_snapshot": snapshot,
            "content_hash": _snapshot_hash(snapshot),
            "issued_at": timezone.now(),
        },
    )
    return receipt


def issue_receipt_access_token(receipt):
    return signing.dumps(
        {
            "v": RECEIPT_SCHEMA_VERSION,
            "receipt": str(receipt.public_token),
            "order": str(receipt.order.public_token),
        },
        salt=RECEIPT_TOKEN_SALT,
        compress=True,
    )


def verify_receipt_access_token(token, receipt):
    token = _safe_text(token)
    if not token or len(token) > RECEIPT_TOKEN_MAX_LENGTH:
        raise ReceiptAccessError(
            "receipt_access_denied",
            "ელექტრონულ ჩეკზე წვდომა ვერ დადასტურდა.",
        )
    try:
        payload = signing.loads(
            token,
            salt=RECEIPT_TOKEN_SALT,
            max_age=settings.ORDER_RECEIPT_GUEST_TOKEN_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as error:
        raise ReceiptAccessError(
            "receipt_token_expired",
            "ელექტრონული ჩეკის ჩამოტვირთვის ბმულს ვადა გაუვიდა.",
        ) from error
    except signing.BadSignature as error:
        raise ReceiptAccessError(
            "receipt_token_invalid",
            "ელექტრონული ჩეკის ჩამოტვირთვის მონაცემები არასწორია.",
        ) from error

    if not isinstance(payload, dict) or (
        payload.get("receipt") != str(receipt.public_token)
        or payload.get("order") != str(receipt.order.public_token)
    ):
        raise ReceiptAccessError(
            "receipt_token_invalid",
            "ელექტრონული ჩეკის ჩამოტვირთვის მონაცემები არასწორია.",
        )


def authorize_receipt_request(request, receipt):
    if (
        request.user.is_authenticated
        and receipt.order.user_id == request.user.id
    ):
        return
    verify_receipt_access_token(
        request.headers.get(RECEIPT_TOKEN_HEADER, ""),
        receipt,
    )


def build_receipt_access_payload(order, request):
    try:
        receipt = get_or_create_order_receipt(order)
    except ReceiptUnavailableError:
        return None
    return {
        "receipt_url": request.build_absolute_uri(
            reverse(
                "commerce-order-receipt",
                kwargs={"public_token": order.public_token},
            )
        ),
        "receipt_access_token": issue_receipt_access_token(receipt),
    }


@lru_cache(maxsize=1)
def register_receipt_fonts():
    font_files = {
        FONT_REGULAR: FONT_DIR / "NotoSansGeorgian-Regular.ttf",
        FONT_SEMIBOLD: FONT_DIR / "NotoSansGeorgian-SemiBold.ttf",
        FONT_BOLD: FONT_DIR / "NotoSansGeorgian-Bold.ttf",
        FONT_EXTRABOLD: FONT_DIR / "NotoSansGeorgian-ExtraBold.ttf",
    }
    for name, path in font_files.items():
        if not path.exists():
            raise RuntimeError(f"Receipt font is missing: {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "FlexDriveReceipt",
        normal=FONT_REGULAR,
        bold=FONT_BOLD,
        italic=FONT_REGULAR,
        boldItalic=FONT_BOLD,
    )


@lru_cache(maxsize=1)
def _load_logo_drawing():
    if not LOGO_PATH.exists():
        raise RuntimeError(f"Receipt logo is missing: {LOGO_PATH}")
    drawing = svg2rlg(str(LOGO_PATH))
    if drawing is None:
        raise RuntimeError("Receipt logo could not be parsed.")
    return drawing


def _logo_flowable(width=142):
    import copy

    drawing = copy.deepcopy(_load_logo_drawing())
    scale = width / drawing.width
    drawing.scale(scale, scale)
    drawing.width *= scale
    drawing.height *= scale
    return drawing


def _paragraph(text, style):
    return Paragraph(escape(_safe_text(text)), style)


def _formatted_money(value, currency="₾"):
    return f"{_money(value)} {currency}"


def _styles():
    return {
        "label": ParagraphStyle(
            "ReceiptLabel",
            fontName=FONT_BOLD,
            fontSize=6.8,
            leading=9,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "value": ParagraphStyle(
            "ReceiptValue",
            fontName=FONT_SEMIBOLD,
            fontSize=9,
            leading=12.5,
            textColor=INK,
        ),
        "title": ParagraphStyle(
            "ReceiptTitle",
            fontName=FONT_EXTRABOLD,
            fontSize=17,
            leading=22,
            textColor=INK,
        ),
        "body": ParagraphStyle(
            "ReceiptBody",
            fontName=FONT_REGULAR,
            fontSize=8.5,
            leading=12.5,
            textColor=SECONDARY,
        ),
        "status": ParagraphStyle(
            "ReceiptStatus",
            fontName=FONT_BOLD,
            fontSize=8,
            leading=11,
            textColor=SUCCESS,
        ),
        "section": ParagraphStyle(
            "ReceiptSection",
            fontName=FONT_BOLD,
            fontSize=8.5,
            leading=12,
            textColor=INK,
        ),
        "product": ParagraphStyle(
            "ReceiptProduct",
            fontName=FONT_SEMIBOLD,
            fontSize=9.2,
            leading=13,
            textColor=INK,
        ),
        "product_meta": ParagraphStyle(
            "ReceiptProductMeta",
            fontName=FONT_REGULAR,
            fontSize=7.2,
            leading=10.5,
            textColor=MUTED,
        ),
        "price": ParagraphStyle(
            "ReceiptPrice",
            fontName=FONT_BOLD,
            fontSize=9.5,
            leading=13,
            textColor=INK,
            alignment=TA_RIGHT,
        ),
        "footer": ParagraphStyle(
            "ReceiptFooter",
            fontName=FONT_REGULAR,
            fontSize=6.7,
            leading=9,
            textColor=MUTED,
        ),
    }


def _xml_lines(values):
    return "<br/>".join(escape(_safe_text(value)) for value in values if _safe_text(value))


class ReceiptCanvas(canvas.Canvas):
    def __init__(self, *args, order_number="", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._receipt_order_number = order_number
        self.setTitle(f"FlexDrive receipt {order_number}")
        self.setAuthor("FlexDrive")
        self.setSubject("Electronic payment receipt")

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_receipt_footer(page_count)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_receipt_footer(self, page_count):
        self.saveState()
        width, height = A4
        if self._pageNumber > 1:
            drawing = _logo_flowable(width=104)
            renderPDF.draw(drawing, self, 14 * mm, height - 17 * mm)
            self.setFont(FONT_BOLD, 7.5)
            self.setFillColor(ACCENT)
            self.drawRightString(
                width - 14 * mm,
                height - 11 * mm,
                f"შეკვეთა № {self._receipt_order_number}",
            )
            self.setStrokeColor(RULE)
            self.setLineWidth(0.5)
            self.line(
                14 * mm,
                height - 20 * mm,
                width - 14 * mm,
                height - 20 * mm,
            )
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(14 * mm, 12 * mm, width - 14 * mm, 12 * mm)
        self.setFont(FONT_REGULAR, 6.7)
        self.setFillColor(MUTED)
        self.drawString(14 * mm, 7.8 * mm, "FlexDrive · ავტომატურად გენერირებული დოკუმენტი")
        self.drawRightString(
            width - 14 * mm,
            7.8 * mm,
            f"გვერდი {self._pageNumber} / {page_count}",
        )
        self.restoreState()


def _build_header(snapshot, styles, content_width):
    order = snapshot["order"]
    header = Table(
        [
            [
                _logo_flowable(),
                Paragraph(
                    "<font color='#66705F' size='7'>შეკვეთის ნომერი</font><br/>"
                    f"<font color='#4F6F1F' size='13'><b>{escape(order['number'])}</b></font>",
                    ParagraphStyle(
                        "ReceiptOrderNumber",
                        fontName=FONT_REGULAR,
                        alignment=TA_RIGHT,
                        leading=15,
                    ),
                ),
            ]
        ],
        colWidths=[content_width * 0.58, content_width * 0.42],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LINEBELOW", (0, 0), (-1, -1), 0.7, RULE),
            ]
        )
    )
    return header


def _build_intro(snapshot, styles, content_width):
    payment = snapshot["payment"]
    is_preview = snapshot["is_preview"]
    status_color = "#8B3B2F" if is_preview else "#167A3A"
    status_text = (
        "სატესტო PDF · თანხა არ არის გადახდილი"
        if is_preview
        else "გადახდა წარმატებით დასრულდა"
    )
    title = "შეკვეთის ელექტრონული ჩეკი"
    left = [
        Paragraph(
            f"<font color='{status_color}'><b>{escape(status_text)}</b></font>",
            styles["status"],
        ),
        Spacer(1, 8),
        _paragraph(title, styles["title"]),
        Spacer(1, 5),
        _paragraph(
            "შეინახე ეს დოკუმენტი შეკვეთისა და გადახდის დეტალების დასადასტურებლად.",
            styles["body"],
        ),
    ]
    right = Table(
        [
            [_paragraph("საბოლოო თანხა", styles["label"])],
            [
                Paragraph(
                    f"<font color='#4F6F1F' size='16'><b>{escape(_formatted_money(snapshot['order']['total']))}</b></font>",
                    styles["value"],
                )
            ],
            [_paragraph(_payment_method_label(payment["method"]), styles["body"])],
            [
                _paragraph(
                    payment["reference"] or payment["status_label"],
                    styles["product_meta"],
                )
            ],
        ],
        colWidths=[content_width * 0.31],
    )
    right.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
            ]
        )
    )
    intro = Table(
        [[left, right]],
        colWidths=[content_width * 0.65, content_width * 0.35],
    )
    intro.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 14),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return intro


def _build_metadata(snapshot, styles, content_width):
    order = snapshot["order"]
    payment = snapshot["payment"]
    cells = [
        ("თარიღი", _display_datetime(order["created_at"])),
        ("ერთეულები", f"{order['total_quantity']} ცალი"),
        ("გადახდის მეთოდი", _payment_method_label(payment["method"])),
        ("სტატუსი", payment["status_label"]),
    ]
    data = [
        [
            [
                _paragraph(label, styles["label"]),
                _paragraph(value, styles["value"]),
            ]
            for label, value in cells
        ]
    ]
    table = Table(data, colWidths=[content_width / 4] * 4)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def _build_products(snapshot, styles, content_width):
    data = [
        [
            _paragraph("პროდუქტის დეტალები", styles["label"]),
            Paragraph("თანხა", styles["label"]),
        ]
    ]
    for item in snapshot["items"]:
        details = Paragraph(
            f"<b>{escape(item['name'])}</b><br/>"
            f"<font color='#66705F' size='7.2'>"
            f"SKU: {escape(item['sku'] or '-')} · "
            f"რაოდენობა: {item['quantity']} · "
            f"ერთეული: {escape(_formatted_money(item['unit_price']))}"
            "</font>",
            styles["product"],
        )
        data.append(
            [
                details,
                Paragraph(
                    escape(_formatted_money(item["line_total"])),
                    styles["price"],
                ),
            ]
        )
    table = Table(
        data,
        colWidths=[content_width - 33 * mm, 33 * mm],
        repeatRows=1,
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
            ]
        )
    )
    return table


def _build_totals(snapshot, styles, content_width):
    order = snapshot["order"]
    cells = [
        ("პროდუქტები", _formatted_money(order["subtotal"]), SOFT, "#111827"),
        ("მიწოდება", _formatted_money(order["delivery_price"]), SOFT, "#111827"),
        ("სულ", _formatted_money(order["total"]), ACCENT, "#FFFFFF"),
    ]
    data = [
        [
            [
                Paragraph(
                    f"<font color='{text_color}' size='7'>{escape(label)}</font><br/>"
                    f"<font color='{text_color}' size='13'><b>{escape(value)}</b></font>",
                    ParagraphStyle(
                        f"ReceiptTotal{index}",
                        fontName=FONT_REGULAR,
                        leading=16,
                    ),
                )
            ]
            for index, (label, value, _, text_color) in enumerate(cells)
        ]
    ]
    table = Table(data, colWidths=[content_width * 0.3, content_width * 0.3, content_width * 0.4])
    commands = [
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]
    for index, (_, _, background, _) in enumerate(cells):
        commands.append(("BACKGROUND", (index, 0), (index, 0), background))
    table.setStyle(TableStyle(commands))
    return table


def _build_parties(snapshot, styles, content_width):
    buyer = snapshot["buyer"]
    seller = snapshot["seller"]
    buyer_name = buyer["company_name"] or buyer["name"]
    buyer_lines = [buyer_name]
    if buyer["company_tax_id"]:
        buyer_lines.append(f"ს/კ: {buyer['company_tax_id']}")
    buyer_lines.extend(
        [
            f"ტელეფონი: {buyer['phone']}" if buyer["phone"] else "",
            f"ელ.ფოსტა: {buyer['email']}" if buyer["email"] else "",
            f"მისამართი: {buyer['address']}" if buyer["address"] else "",
            " · ".join(value for value in (buyer["region"], buyer["city"]) if value),
        ]
    )
    seller_lines = [seller["name"]]
    seller_lines.extend(
        [
            f"ს/კ: {seller['tax_id']}" if seller["tax_id"] else "",
            seller["address"],
            f"ტელეფონი: {seller['phone']}" if seller["phone"] else "",
            f"ელ.ფოსტა: {seller['email']}" if seller["email"] else "",
            seller["website"],
        ]
    )
    buyer_cell = [
        _paragraph("მყიდველი და მიწოდება", styles["label"]),
        Paragraph(_xml_lines(buyer_lines), styles["body"]),
    ]
    seller_cell = [
        _paragraph("გამყიდველი", styles["label"]),
        Paragraph(_xml_lines(seller_lines), styles["body"]),
    ]
    table = Table(
        [[buyer_cell, seller_cell]],
        colWidths=[content_width * 0.56, content_width * 0.44],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
            ]
        )
    )
    return table


def render_order_receipt_pdf(receipt):
    register_receipt_fonts()
    snapshot = receipt.document_snapshot
    if (
        not isinstance(snapshot, dict)
        or not hmac.compare_digest(
            _safe_text(receipt.content_hash),
            _snapshot_hash(snapshot),
        )
        or snapshot.get("template_version") != receipt.template_version
    ):
        raise ReceiptUnavailableError(
            "receipt_integrity_failed",
            "ელექტრონული ჩეკის მონაცემების მთლიანობა ვერ დადასტურდა.",
        )
    styles = _styles()
    output = BytesIO()
    left_margin = right_margin = 14 * mm
    content_width = A4[0] - left_margin - right_margin
    order_number = snapshot["order"]["number"]
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=24 * mm,
        bottomMargin=19 * mm,
        title=f"FlexDrive receipt {order_number}",
        author="FlexDrive",
        subject="Electronic payment receipt",
    )
    story = [
        _build_header(snapshot, styles, content_width),
        _build_intro(snapshot, styles, content_width),
        _build_metadata(snapshot, styles, content_width),
        Spacer(1, 14),
        _paragraph("პროდუქტები", styles["section"]),
        Spacer(1, 7),
        _build_products(snapshot, styles, content_width),
        Spacer(1, 14),
        KeepTogether(
            [
                _build_totals(snapshot, styles, content_width),
                Spacer(1, 12),
                _build_parties(snapshot, styles, content_width),
            ]
        ),
    ]
    if snapshot.get("is_preview"):
        story.extend(
            [
                Spacer(1, 10),
                Table(
                    [[Paragraph(
                        "<font color='#8B3B2F'><b>სატესტო დოკუმენტი · გადახდას არ ადასტურებს</b></font>",
                        styles["section"],
                    )]],
                    colWidths=[content_width],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBEDEA")),
                            ("BOX", (0, 0), (-1, -1), 0.7, PREVIEW),
                            ("TEXTCOLOR", (0, 0), (-1, -1), PREVIEW),
                            ("LEFTPADDING", (0, 0), (-1, -1), 11),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                            ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ]
                    ),
                ),
            ]
        )

    document.build(
        story,
        onFirstPage=lambda pdf_canvas, doc: None,
        onLaterPages=lambda pdf_canvas, doc: None,
        canvasmaker=partial(ReceiptCanvas, order_number=order_number),
    )
    return output.getvalue()


def receipt_filename(order_number):
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "-", _safe_text(order_number)).strip("-")
    safe_number = safe_number or "order"
    filename = f"FlexDrive-{safe_number}.pdf"
    return filename, quote(filename)
