from django.test import SimpleTestCase

from .credo_status import (
    CredoStage,
    CredoStatus,
    describe_credo_status,
    evaluate_credo_observation,
    parse_credo_status,
)


class CredoStatusTests(SimpleTestCase):
    def test_only_signed_or_completed_observations_authorize_fulfillment(self):
        for code in CredoStatus:
            with self.subTest(code=code):
                state = describe_credo_status(code)
                self.assertEqual(state.fulfillment_authorized, code in {12, 5})
                self.assertEqual(state.funding_completed, code == 5)
                self.assertEqual(state.terminal, code in {5, 6, 7})

    def test_approval_and_signature_do_not_mean_cash_received(self):
        self.assertEqual(describe_credo_status(3).stage, CredoStage.APPROVED)
        self.assertFalse(describe_credo_status(4).fulfillment_authorized)
        self.assertFalse(describe_credo_status(12).funding_completed)

    def test_envelope_code_and_untyped_values_are_not_application_statuses(self):
        for value in (200, 0, 1, 8, -1, 999, "12", 12.0, True, None, {}, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_credo_status(value)

    def test_processing_branches_remain_pending_in_any_order(self):
        for previous, observed in ((2, 9), (9, 13), (13, 14), (3, 2), (4, 14)):
            with self.subTest(previous=previous, observed=observed):
                decision = evaluate_credo_observation(previous, observed)
                self.assertEqual(decision.effective_status, observed)
                self.assertFalse(decision.requires_review)
                self.assertFalse(describe_credo_status(decision.effective_status).fulfillment_authorized)

    def test_signed_application_can_finish_once_and_repeat_safely(self):
        decision = evaluate_credo_observation(12, 5)
        self.assertEqual(decision.effective_status, CredoStatus.COMPLETED)
        self.assertFalse(decision.requires_review)
        self.assertFalse(evaluate_credo_observation(5, 5).requires_review)
        self.assertFalse(evaluate_credo_observation(12, 12).requires_review)

    def test_signed_application_never_automatically_regresses_or_releases_stock(self):
        for observed in (2, 3, 4, 6, 7, 9, 10, 11, 13, 14):
            with self.subTest(observed=observed):
                decision = evaluate_credo_observation(12, observed)
                self.assertEqual(decision.effective_status, CredoStatus.SIGNED)
                self.assertEqual(decision.observed_status, observed)
                self.assertTrue(decision.requires_review)
                self.assertFalse(decision.fulfillment_allowed)

    def test_terminal_states_keep_late_evidence_for_review_without_mutation(self):
        for previous in (5, 6, 7):
            for observed in CredoStatus:
                with self.subTest(previous=previous, observed=observed):
                    decision = evaluate_credo_observation(previous, observed)
                    self.assertEqual(decision.effective_status, previous)
                    self.assertEqual(decision.observed_status, observed)
                    self.assertEqual(decision.requires_review, previous != observed)
                    if decision.requires_review:
                        self.assertFalse(decision.fulfillment_allowed)

    def test_first_observation_can_skip_intermediate_statuses(self):
        for observed in (5, 6, 7, 12):
            with self.subTest(observed=observed):
                decision = evaluate_credo_observation(None, observed)
                self.assertEqual(decision.effective_status, observed)
                self.assertFalse(decision.requires_review)

    def test_repeated_good_status_cannot_clear_an_existing_review_incident(self):
        for previous, observed in ((12, 12), (12, 5), (6, 5), (None, 12)):
            with self.subTest(previous=previous, observed=observed):
                decision = evaluate_credo_observation(previous, observed, review_required=True)
                self.assertTrue(decision.requires_review)
                self.assertFalse(decision.fulfillment_allowed)
                self.assertEqual(decision.observed_status, observed)
                self.assertEqual(decision.effective_status, previous if previous is not None else observed)
