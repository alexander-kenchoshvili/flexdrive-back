from django.contrib.admin.apps import AdminConfig


class FlexDriveAdminConfig(AdminConfig):
    default_site = "config.admin_site.FlexDriveAdminSite"
