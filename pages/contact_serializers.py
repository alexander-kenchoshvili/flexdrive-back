from rest_framework import serializers

from .models import ContactInquiry, ContentItem


CONTACT_CONTENT_NAME = "contact_page_content"
CONTACT_TOPIC_CONTENT_TYPE = "contact_topic"


class ContactInquiryCreateSerializer(serializers.ModelSerializer):
    recaptcha_token = serializers.CharField(write_only=True)

    class Meta:
        model = ContactInquiry
        fields = [
            "full_name",
            "phone",
            "email",
            "topic_slug",
            "order_number",
            "message",
            "recaptcha_token",
        ]

    def _get_topic_item(self, topic_slug):
        return (
            ContentItem.objects
            .filter(
                content__name=CONTACT_CONTENT_NAME,
                content_type=CONTACT_TOPIC_CONTENT_TYPE,
                slug=topic_slug,
            )
            .order_by("position", "id")
            .first()
        )

    def validate_topic_slug(self, value):
        topic_item = self._get_topic_item(value)
        if not topic_item or not (topic_item.title or "").strip():
            raise serializers.ValidationError("აირჩიეთ სწორი საკითხის თემა.")

        self.context["topic_item"] = topic_item
        return value

    def validate(self, attrs):
        topic_item = self.context.get("topic_item")
        if topic_item is None and attrs.get("topic_slug"):
            topic_item = self._get_topic_item(attrs["topic_slug"])

        if topic_item is None:
            raise serializers.ValidationError(
                {"topic_slug": "აირჩიეთ სწორი საკითხის თემა."}
            )

        attrs["topic_label"] = (topic_item.title or "").strip()
        attrs["order_number"] = (attrs.get("order_number") or "").strip()
        attrs["message"] = (attrs.get("message") or "").strip()
        attrs["full_name"] = (attrs.get("full_name") or "").strip()
        attrs["phone"] = (attrs.get("phone") or "").strip()
        attrs["email"] = (attrs.get("email") or "").strip()
        return attrs

    def create(self, validated_data):
        validated_data.pop("recaptcha_token", None)
        return super().create(validated_data)
