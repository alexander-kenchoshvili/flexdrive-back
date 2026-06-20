import logging
import smtplib
import time

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


logger = logging.getLogger(__name__)

BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    def __init__(self, message="We could not send the email right now. Please try again later."):
        super().__init__(message)


def _retry_settings():
    attempts = max(1, int(getattr(settings, "EMAIL_DELIVERY_MAX_ATTEMPTS", 3)))
    delay = max(
        0.0,
        float(getattr(settings, "EMAIL_DELIVERY_RETRY_DELAY_SECONDS", 0.25)),
    )
    return attempts, delay


def _send_with_retry(send_once):
    max_attempts, base_delay = _retry_settings()
    for attempt in range(1, max_attempts + 1):
        try:
            send_once()
            return
        except EmailDeliveryError as exc:
            if not getattr(exc, "retryable", False) or attempt == max_attempts:
                raise
            logger.warning(
                "Temporary email delivery failure; retrying (%s/%s).",
                attempt,
                max_attempts,
            )
            if base_delay:
                time.sleep(base_delay * (2 ** (attempt - 1)))


def _is_retryable_smtp_error(error):
    if isinstance(error, smtplib.SMTPResponseException):
        return 400 <= error.smtp_code < 500
    return isinstance(
        error,
        (
            smtplib.SMTPServerDisconnected,
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    )


def _normalize_recipients(recipients):
    normalized = [str(email).strip() for email in recipients if str(email).strip()]
    if not normalized:
        raise EmailDeliveryError("No email recipient was provided.")
    return normalized


def _send_via_brevo_api(
    *,
    subject,
    text_content,
    html_content,
    recipients,
    reply_to=None,
):
    sender_email = str(settings.DEFAULT_FROM_EMAIL).strip()
    if not sender_email:
        raise EmailDeliveryError("The sender email is not configured.")

    payload = {
        "sender": {"email": sender_email},
        "to": [{"email": email} for email in recipients],
        "subject": subject,
        "textContent": text_content,
    }
    if html_content:
        payload["htmlContent"] = html_content
    if reply_to:
        payload["replyTo"] = {"email": reply_to}

    def send_once():
        try:
            response = requests.post(
                BREVO_TRANSACTIONAL_EMAIL_URL,
                headers={
                    "accept": "application/json",
                    "api-key": settings.BREVO_API_KEY,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=settings.BREVO_API_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("Brevo API request failed while sending email.", exc_info=True)
            error = EmailDeliveryError()
            error.retryable = True
            raise error from exc

        if response.status_code >= 400:
            logger.error(
                "Brevo API rejected email with status %s: %s",
                response.status_code,
                response.text,
            )
            error = EmailDeliveryError()
            error.retryable = response.status_code in {408, 429} or response.status_code >= 500
            raise error

    _send_with_retry(send_once)


def _send_via_django_mail(
    *,
    subject,
    text_content,
    html_content,
    recipients,
    reply_to=None,
):
    def send_once():
        try:
            message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
                reply_to=[reply_to] if reply_to else None,
            )
            if html_content:
                message.attach_alternative(html_content, "text/html")
            message.send(fail_silently=False)
        except Exception as exc:
            logger.warning("SMTP failed while sending email.", exc_info=True)
            error = EmailDeliveryError()
            error.retryable = _is_retryable_smtp_error(exc)
            raise error from exc

    _send_with_retry(send_once)


def send_transactional_email(
    *,
    subject,
    text_content,
    recipients,
    html_content=None,
    reply_to=None,
):
    normalized_recipients = _normalize_recipients(recipients)
    normalized_reply_to = str(reply_to or "").strip() or None

    if getattr(settings, "BREVO_API_KEY", ""):
        _send_via_brevo_api(
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            recipients=normalized_recipients,
            reply_to=normalized_reply_to,
        )
        return

    _send_via_django_mail(
        subject=subject,
        text_content=text_content,
        html_content=html_content,
        recipients=normalized_recipients,
        reply_to=normalized_reply_to,
    )


def send_auth_email(*, subject, text_content, recipients, html_content=None):
    send_transactional_email(
        subject=subject,
        text_content=text_content,
        html_content=html_content,
        recipients=recipients,
    )
