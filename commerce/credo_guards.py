"""Queries for unresolved financing in the existing checkout-owner context."""

from django.db.models import Q

from .models import CredoApplication, StockReservationItem


def unresolved_credo_applications():
    # A created order consumes this checkout once; its funding wait must not
    # prohibit a genuinely new purchase. Replays are blocked by CheckoutAttempt.
    # Expired local stock holds do NOT imply that a bank application was cancelled.
    return CredoApplication.objects.filter(order__isnull=True).exclude(
        Q(bank_status__in=(6, 7), needs_review=False)
        | Q(submission_state=CredoApplication.SubmissionState.FAILED,
            bank_status__isnull=True, needs_review=False)
    )


def has_unresolved_credo_application(*, source, owner_filter, product_ids=None):
    if not owner_filter:
        return False
    applications = unresolved_credo_applications().filter(
        reservation__source=source, **owner_filter,
    )
    if product_ids is not None:
        product_ids = {int(value) for value in product_ids if value is not None}
        if not product_ids:
            return False
        applications = applications.filter(reservation_id__in=StockReservationItem.objects.filter(
            product_id__in=product_ids,
        ).values("reservation_id"))
    return applications.exists()
