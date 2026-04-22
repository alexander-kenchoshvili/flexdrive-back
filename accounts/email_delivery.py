import logging

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


logger = logging.getLogger(__name__)

BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    def __init__(self, message="We could not send the email right now. Please try again later."):
        super().__init__(message)


def _normalize_recipients(recipients):
    normalized = [str(email).strip() for email in recipients if str(email).strip()]
    if not normalized:
        raise EmailDeliveryError("No email recipient was provided.")
    return normalized


def _send_via_brevo_api(*, subject, text_content, html_content, recipients):
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
        logger.exception("Brevo API request failed while sending auth email.")
        raise EmailDeliveryError() from exc

    if response.status_code >= 400:
        logger.error(
            "Brevo API rejected auth email with status %s: %s",
            response.status_code,
            response.text,
        )
        raise EmailDeliveryError()


def _send_via_django_mail(*, subject, text_content, html_content, recipients):
    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        if html_content:
            message.attach_alternative(html_content, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("SMTP fallback failed while sending auth email.")
        raise EmailDeliveryError() from exc


def send_auth_email(*, subject, text_content, recipients, html_content=None):
    normalized_recipients = _normalize_recipients(recipients)

    if getattr(settings, "BREVO_API_KEY", ""):
        _send_via_brevo_api(
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            recipients=normalized_recipients,
        )
        return

    _send_via_django_mail(
        subject=subject,
        text_content=text_content,
        html_content=html_content,
        recipients=normalized_recipients,
    )
