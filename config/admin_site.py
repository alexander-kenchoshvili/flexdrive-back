"""Admin navigation labels/order only; Django still owns URLs and permissions."""
from django.contrib.admin import AdminSite


# Keep app/model identities unchanged, including proxy models and custom admin URLs.
NAVIGATION = {
    "commerce": ("შეკვეთები და ოპერაციები", {
        "Order": "შეკვეთები",
        "OrderReturn": "დაბრუნებები",
        "PaymentTransaction": "გადახდები და თანხის დაბრუნებები",
        "OwnedStockLot": "FlexDrive-ის მარაგი",
        "WingoReferenceData": "Wingo-ს ტარიფები",
        "Cart": "კალათები",
        "CheckoutAttempt": "შეკვეთის გაფორმების მცდელობები",
        "StockReservation": "მარაგის ჯავშნები",
        "SupplierStockHold": "Cross Motors-ის დროებითი ჩამოკლებები",
    }),
    "catalog": ("პროდუქტები და კატალოგი", {
        "Product": "პროდუქტები",
        "DraftProduct": "მონახაზები",
        "ArchivedProduct": "არქივი",
        "SupplierPriceReview": "გადასახედი ფასები",
        "Category": "კატეგორიები",
        "Brand": "ნაწილების ბრენდები",
        "VehicleMake": "მანქანის მარკები",
        "VehicleModel": "მანქანის მოდელები",
        "VehicleEngine": "ძრავები",
        "SupplierSyncReport": "სინქრონიზაციის ანგარიშები",
        "SupplierProductBlock": "მომწოდებლის პროდუქტების ბლოკირება",
    }),
    "pages": ("საიტის შინაარსი და პარამეტრები", {
        "Page": "გვერდები",
        "BlogPost": "ბლოგის სტატიები",
        "ContactInquiry": "შემოსული შეტყობინებები",
        "SiteSettings": "საიტის პარამეტრები",
        "FooterSettings": "ფუტერის პარამეტრები",
        "LaunchControl": "საიტის საჯარო გახსნა",
        "Component": "გვერდის კომპონენტები",
        "Content": "შიგთავსის ბლოკები",
        "ContentItem": "შიგთავსის ელემენტები",
        "ComponentType": "კომპონენტების ტიპები",
    }),
    "accounts": ("მომხმარებლები", {
        "CustomUser": "მომხმარებლები",
        "GoogleAccount": "Google-ით დაკავშირებული ანგარიშები",
        "FacebookAccount": "Facebook-ით დაკავშირებული ანგარიშები",
    }),
    "auth": ("წვდომის უფლებები", {
        "Group": "უფლებების ჯგუფები",
    }),
    "token_blacklist": ("ტექნიკური ავტორიზაცია", {
        "OutstandingToken": "გაცემული ავტორიზაციის ტოკენები",
        "BlacklistedToken": "გაუქმებული ავტორიზაციის ტოკენები",
    }),
}


class FlexDriveAdminSite(AdminSite):
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
