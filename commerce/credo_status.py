"""Credo application observations, independent of money and order mutations.

The bank's envelope ``status`` is not an application status. Only ``data``
contains the status below. A signed application permits fulfillment; it is
not a cash receipt. Conflicting observations require reconciliation.
"""

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class CredoStatus(IntEnum):
    PROCESSING = 2
    APPROVED = 3
    AWAITING_SIGNATURE = 4
    COMPLETED = 5
    REJECTED = 6
    CANCELLED = 7
    BRANCH_REVIEW = 9
    NEEDS_IDENTIFICATION = 10
    DRAFT = 11
    SIGNED = 12
    VIDEO_REVIEW = 13
    BACK_OFFICE_REVIEW = 14


class CredoStage(StrEnum):
    IDENTIFICATION = "identification"
    PROCESSING = "processing"
    APPROVED = "approved"
    AWAITING_SIGNATURE = "awaiting_signature"
    READY_TO_SHIP = "ready_to_ship"
    FUNDING_COMPLETED = "funding_completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CredoStatusDescription:
    stage: CredoStage
    label: str
    fulfillment_authorized: bool = False
    funding_completed: bool = False
    terminal: bool = False


_DESCRIPTIONS = {
    CredoStatus.DRAFT: CredoStatusDescription(CredoStage.IDENTIFICATION, "განაცხადი შექმნილია"),
    CredoStatus.NEEDS_IDENTIFICATION: CredoStatusDescription(CredoStage.IDENTIFICATION, "საჭიროა იდენტიფიკაცია"),
    CredoStatus.PROCESSING: CredoStatusDescription(CredoStage.PROCESSING, "განაცხადი განხილვაშია"),
    CredoStatus.BRANCH_REVIEW: CredoStatusDescription(CredoStage.PROCESSING, "საჭიროა ფილიალში გადამოწმება"),
    CredoStatus.VIDEO_REVIEW: CredoStatusDescription(CredoStage.PROCESSING, "მიმდინარეობს ვიდეოშემოწმება"),
    CredoStatus.BACK_OFFICE_REVIEW: CredoStatusDescription(CredoStage.PROCESSING, "მიმდინარეობს დამატებითი განხილვა"),
    CredoStatus.APPROVED: CredoStatusDescription(CredoStage.APPROVED, "დამტკიცებულია — შესაძლოა დამატებითი შემოწმება"),
    CredoStatus.AWAITING_SIGNATURE: CredoStatusDescription(CredoStage.AWAITING_SIGNATURE, "დამტკიცებულია — ხელმოსაწერია"),
    CredoStatus.SIGNED: CredoStatusDescription(CredoStage.READY_TO_SHIP, "ხელმოწერილია — გასაგზავნია", True),
    CredoStatus.COMPLETED: CredoStatusDescription(CredoStage.FUNDING_COMPLETED, "დაფინანსება დასრულებულია", True, True, True),
    CredoStatus.REJECTED: CredoStatusDescription(CredoStage.REJECTED, "განაცხადი უარყოფილია", terminal=True),
    CredoStatus.CANCELLED: CredoStatusDescription(CredoStage.CANCELLED, "განაცხადი გაუქმებულია", terminal=True),
}


def parse_credo_status(value):
    """Require the documented integer; bool, strings and unknowns fail closed."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Invalid Credo application status.")
    try:
        return CredoStatus(value)
    except ValueError:
        raise ValueError("Unknown Credo application status.") from None


def describe_credo_status(value):
    return _DESCRIPTIONS[parse_credo_status(value)]


@dataclass(frozen=True)
class CredoObservationDecision:
    effective_status: CredoStatus
    observed_status: CredoStatus
    requires_review: bool = False
    issue: str = ""

    @property
    def fulfillment_allowed(self):
        return not self.requires_review and describe_credo_status(self.effective_status).fulfillment_authorized


def evaluate_credo_observation(previous_status, observed_status, *, review_required=False):
    """Choose the effective bank state, without authorizing local side effects.

    Processing branches have no documented total ordering. They can change
    freely until signature. After signature, a regression/cancellation cannot
    restore stock, undo delivery, or assert that a loan was refunded. Late
    success after a terminal failure is also an incident, not a fresh checkout.
    Callers retain the observed status even when the effective state is held.
    """
    if type(review_required) is not bool:
        raise ValueError("Invalid Credo review flag.")
    observed = parse_credo_status(observed_status)
    previous = parse_credo_status(previous_status) if previous_status is not None else None
    if review_required:
        return CredoObservationDecision(
            previous if previous is not None else observed, observed, True, "credo_prior_review_required",
        )
    if previous_status is None:
        return CredoObservationDecision(observed, observed)
    if previous == observed:
        return CredoObservationDecision(previous, observed)
    if describe_credo_status(previous).terminal:
        return CredoObservationDecision(previous, observed, True, "credo_terminal_status_conflict")
    if previous == CredoStatus.SIGNED and observed != CredoStatus.COMPLETED:
        return CredoObservationDecision(previous, observed, True, "credo_signed_status_conflict")
    return CredoObservationDecision(observed, observed)
