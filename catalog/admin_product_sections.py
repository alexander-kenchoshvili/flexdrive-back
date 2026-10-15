"""Status-specific admin lists sharing the existing Product editor and permissions."""

from django.contrib.admin.views.main import ChangeList

from .models import ProductStatus


PRODUCT_SECTIONS = {
    ProductStatus.PUBLISHED: ("product", "Products"),
    ProductStatus.DRAFT: ("draftproduct", "Drafts"),
    ProductStatus.ARCHIVED: ("archivedproduct", "Archived"),
}


class ProductSectionChangeList(ChangeList):
    def get_queryset(self, request, exclude_parameters=None):
        # Scope counts, filter choices and select-all actions as well as rows.
        # The editor and related-product autocomplete retain the full queryset.
        self.root_queryset = self.root_queryset.filter(status=self.model_admin.section_status)
        return super().get_queryset(request, exclude_parameters)
