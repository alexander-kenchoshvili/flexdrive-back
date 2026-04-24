from django.conf import settings
from django.core.mail import EmailMessage
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.utils import validate_recaptcha

from .contact_serializers import ContactInquiryCreateSerializer
from .models import FooterSettings


class ContactInquiryCreateAPIView(APIView):
    serializer_class = ContactInquiryCreateSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        remote_ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )
        recaptcha_token = serializer.validated_data.get("recaptcha_token")

        if not validate_recaptcha(
            recaptcha_token,
            expected_action="contact_inquiry",
            remote_ip=remote_ip,
        ):
            return Response(
                {
                    "detail": "უსაფრთხოების შემოწმება ვერ შესრულდა. სცადეთ თავიდან."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        inquiry = serializer.save()
        self._send_notification_email(inquiry)

        return Response(
            {
                "message": (
                    "შეტყობინება მიღებულია. სამუშაო საათებში მაქსიმალურად სწრაფად "
                    "დაგიბრუნდებით პასუხს, არასამუშაო დროს კი მომდევნო სამუშაო დღეს."
                )
            },
            status=status.HTTP_201_CREATED,
        )

    def _send_notification_email(self, inquiry):
        footer_settings = FooterSettings.objects.first()
        recipient = (
            getattr(footer_settings, "email", None)
            or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        )
        if not recipient:
            return

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", recipient) or recipient
        subject = f"ახალი საკონტაქტო მოთხოვნა: {inquiry.topic_label}"
        body = "\n".join(
            [
                "მივიღეთ ახალი საკონტაქტო მოთხოვნა FlexDrive-იდან.",
                "",
                f"თემა: {inquiry.topic_label}",
                f"სახელი: {inquiry.full_name}",
                f"ტელეფონი: {inquiry.phone}",
                f"ელფოსტა: {inquiry.email}",
                f"შეკვეთის ნომერი: {inquiry.order_number or '-'}",
                "",
                "შეტყობინება:",
                inquiry.message,
            ]
        )

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient],
            reply_to=[inquiry.email] if inquiry.email else None,
        )

        try:
            email.send(fail_silently=False)
        except Exception:
            return
