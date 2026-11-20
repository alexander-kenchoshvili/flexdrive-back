"""Admin navigation labels/order only; Django still owns URLs and permissions."""
from django.contrib.admin import AdminSite


# Keep app/model identities unchanged, including proxy models and custom admin URLs.
NAVIGATION = {
    "commerce": ("Commerce — შეკვეთები და ოპერაციები", {
        "Order": "Orders — შეკვეთები",
        "OrderReturn": "Returns — დაბრუნებები",
        "PaymentTransaction": "Payment Transactions — გადახდები და თანხის დაბრუნებები",
        "OwnedStockLot": "Owned Stock Lots — FlexDrive-ის მარაგი",
        "WingoReferenceData": "Wingo Tariffs — Wingo-ს ტარიფები",
        "Cart": "Carts — კალათები",
        "CheckoutAttempt": "Checkout Attempts — შეკვეთის დუბლირებისგან დაცვა",
        "StockReservation": "Stock Reservations — მარაგის ჯავშნები",
        "SupplierStockHold": "Supplier Stock Holds — Cross Motors-ის დროებითი ჩამოკლებები",
    }),
    "catalog": ("Catalog — პროდუქტები და კატალოგი", {
        "Product": "Products — პროდუქტები",
        "DraftProduct": "Drafts — მონახაზები",
        "ArchivedProduct": "Archived — არქივი",
        "SupplierPriceReview": "Supplier Price Reviews — გადასახედი ფასები",
        "Category": "Categories — კატეგორიები",
        "Brand": "Brands — ნაწილების ბრენდები",
        "VehicleMake": "Vehicle Makes — მანქანის მარკები",
        "VehicleModel": "Vehicle Models — მანქანის მოდელები",
        "VehicleEngine": "Vehicle Engines — ძრავები",
        "SupplierSyncReport": "Supplier Sync Reports — სინქრონიზაციის ანგარიშები",
        "SupplierProductBlock": "Supplier Product Blocks — მომწოდებლის პროდუქტების ბლოკირება",
    }),
    "pages": ("Pages — საიტის შინაარსი და პარამეტრები", {
        "Page": "Pages — გვერდები",
        "BlogPost": "Blog Posts — ბლოგის სტატიები",
        "ContactInquiry": "Contact Inquiries — შემოსული შეტყობინებები",
        "SiteSettings": "Site Settings — საიტის პარამეტრები",
        "FooterSettings": "Footer Settings — ფუტერის პარამეტრები",
        "LaunchControl": "Launch Control — საიტის საჯარო გახსნა",
        "Component": "Components — გვერდის კომპონენტები",
        "Content": "Contents — შიგთავსის ბლოკები",
        "ContentItem": "Content Items — შიგთავსის ელემენტები",
        "ComponentType": "Component Types — კომპონენტების ტიპები",
    }),
    "accounts": ("Accounts — მომხმარებლები", {
        "CustomUser": "Users — მომხმარებლები",
        "GoogleAccount": "Google Accounts — Google-ით დაკავშირებული ანგარიშები",
        "FacebookAccount": "Facebook Accounts — Facebook-ით დაკავშირებული ანგარიშები",
    }),
    "auth": ("Authentication and Authorization — წვდომის უფლებები", {
        "Group": "Groups — უფლებების ჯგუფები",
    }),
    "token_blacklist": ("Token Blacklist — ტექნიკური ავტორიზაცია", {
        "OutstandingToken": "Outstanding Tokens — გაცემული ავტორიზაციის ტოკენები",
        "BlacklistedToken": "Blacklisted Tokens — გაუქმებული ავტორიზაციის ტოკენები",
    }),
}


class FlexDriveAdminSite(AdminSite):
    site_header = "FlexDrive Admin — თბილისის დრო (UTC+04:00)"

    def get_app_list(self, request, app_label=None):
        # Filter through Django's existing permission checks before presentation.
        app_list = super().get_app_list(request, app_label)
        app_order = {label: index for index, label in enumerate(NAVIGATION)}
        for app in app_list:
            definition = NAVIGATION.get(app["app_label"])
            if definition is None:
                continue
            app["name"], labels = definition
            model_order = {name: index for index, name in enumerate(labels)}
            for model in app["models"]:
                model["name"] = labels.get(model["object_name"], model["name"])
            app["models"].sort(key=lambda model: (
                model_order.get(model["object_name"], len(model_order)),
                str(model["name"]).casefold(),
            ))
        app_list.sort(key=lambda app: (
            app_order.get(app["app_label"], len(app_order)),
            str(app["name"]).casefold(),
        ))
        return app_list
