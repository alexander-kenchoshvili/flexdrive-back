"""Saved order buyer details, restricted to the accountant report and export."""

BUYER_COLUMNS = (
    ("order_number", "შეკვეთა", 27),
    ("buyer_type", "მყიდველის ტიპი", 23),
    ("company_name", "კომპანიის დასახელება", 32),
    ("company_identification_code", "კომპანიის საიდენტიფიკაციო კოდი", 26),
    ("first_name", "სახელი / საკონტაქტო პირის სახელი", 27),
    ("last_name", "გვარი / საკონტაქტო პირის გვარი", 27),
    ("personal_number", "ფიზიკური პირის პირადი ნომერი", 25),
    ("address", "მიწოდების მისამართი", 58),
    ("phone", "საკონტაქტო ტელეფონი", 24),
)


def order_buyer(order):
    legal = order.buyer_type == "legal_entity"
    return {
        "order_number": order.order_number,
        "buyer_type": "იურიდიული პირი" if legal else "ფიზიკური პირი",
        "company_name": order.company_name if legal else "",
        "company_identification_code": order.company_identification_code if legal else "",
        "first_name": order.first_name,
        "last_name": order.last_name,
        "personal_number": order.personal_number if not legal else "",
        "address": ", ".join(value.strip() for value in (order.city, order.address_line) if value.strip()),
        "phone": order.phone,
    }


def buyer_fields(buyer):
    excluded = {"order_number", "buyer_type"}
    excluded.update({"personal_number"} if buyer["buyer_type"] == "იურიდიული პირი"
                    else {"company_name", "company_identification_code"})
    return [(label, buyer[key] or "—") for key, label, _ in BUYER_COLUMNS if key not in excluded]
