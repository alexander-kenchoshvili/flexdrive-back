from django.db import transaction
from django.utils import timezone

from commerce.models import StockReservation, StockReservationStatus


@transaction.atomic
def delete_user_account(user):
    user_model = type(user)
    locked_user = user_model.objects.select_for_update().get(pk=user.pk)

    active_reservation_ids = list(
        StockReservation.objects.select_for_update()
        .filter(
            user=locked_user,
            status=StockReservationStatus.ACTIVE,
        )
        .values_list("pk", flat=True)
    )

    if active_reservation_ids:
        now = timezone.now()
        StockReservation.objects.filter(
            pk__in=active_reservation_ids,
            status=StockReservationStatus.ACTIVE,
        ).update(
            status=StockReservationStatus.RELEASED,
            released_at=now,
            updated_at=now,
        )

    return locked_user.delete()
