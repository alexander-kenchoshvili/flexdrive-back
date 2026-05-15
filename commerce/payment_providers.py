from dataclasses import dataclass

from .models import (
    PaymentProvider,
    PaymentTransactionAction,
    PaymentTransactionStatus,
)


@dataclass(frozen=True)
class PaymentProviderResponse:
    status: str
    provider_transaction_id: str
    provider_reference: dict
    error_code: str = ""
    error_message: str = ""


class BasePaymentProvider:
    provider = None

    def authorize(self, *, transaction):
        raise NotImplementedError

    def capture(self, *, transaction):
        raise NotImplementedError

    def cancel(self, *, transaction):
        raise NotImplementedError

    def refund(self, *, transaction):
        raise NotImplementedError


class MockPaymentProvider(BasePaymentProvider):
    def __init__(self, provider=PaymentProvider.MOCK):
        self.provider = provider

    def authorize(self, *, transaction):
        return self._response(transaction, PaymentTransactionStatus.AUTHORIZED)

    def capture(self, *, transaction):
        return self._response(transaction, PaymentTransactionStatus.PAID)

    def cancel(self, *, transaction):
        return self._response(transaction, PaymentTransactionStatus.CANCELLED)

    def refund(self, *, transaction):
        return self._response(transaction, PaymentTransactionStatus.REFUNDED)

    def _response(self, transaction, status):
        return PaymentProviderResponse(
            status=status,
            provider_transaction_id=(
                f"{self.provider}-{transaction.action}-{transaction.pk}"
            ),
            provider_reference={
                "provider": self.provider,
                "action": transaction.action,
                "mode": "mock" if self.provider == PaymentProvider.MOCK else "manual",
            },
        )


def get_payment_provider(provider):
    if provider in {PaymentProvider.MOCK, PaymentProvider.MANUAL}:
        return MockPaymentProvider(provider=provider)
    raise ValueError(f"Unsupported payment provider: {provider}")


def get_provider_method_for_action(provider, action):
    provider_instance = get_payment_provider(provider)
    method_by_action = {
        PaymentTransactionAction.AUTHORIZE: provider_instance.authorize,
        PaymentTransactionAction.CAPTURE: provider_instance.capture,
        PaymentTransactionAction.SALE: provider_instance.capture,
        PaymentTransactionAction.CANCEL: provider_instance.cancel,
        PaymentTransactionAction.REFUND: provider_instance.refund,
    }
    return method_by_action[action]
