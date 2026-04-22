from django.conf import settings
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.html import format_html
from datetime import timedelta
import uuid
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login

from .models import UserProfile
from .email_delivery import EmailDeliveryError, send_auth_email
from .token_utils import (
    build_refresh_token_for_user,
    get_auth_token_version,
    revoke_user_refresh_tokens,
)

User = get_user_model()
TOKEN_TTL = timedelta(hours=1)


def _build_link_email_html(*, intro_text, action_label, url):
    return format_html(
        (
            "<p>{}</p>"
            "<p><a href=\"{}\">{}</a></p>"
            "<p>If the link above does not work, copy and paste this URL into your browser:</p>"
            "<p>{}</p>"
        ),
        intro_text,
        url,
        action_label,
        url,
    )


class UserMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class UserProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    phone = serializers.CharField(max_length=50, allow_blank=True, required=False)
    city = serializers.CharField(max_length=120, allow_blank=True, required=False)
    address_line = serializers.CharField(max_length=255, allow_blank=True, required=False)

    def to_representation(self, instance):
        profile, _ = UserProfile.objects.get_or_create(user=instance)
        return {
            "id": instance.id,
            "email": instance.email,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "phone": profile.phone,
            "city": profile.city,
            "address_line": profile.address_line,
        }

    def validate_email(self, value):
        normalized = value.strip().lower()
        qs = User.objects.filter(email__iexact=normalized)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def update(self, instance, validated_data):
        profile, _ = UserProfile.objects.get_or_create(user=instance)

        user_fields = {
            "email": validated_data.get("email", instance.email),
            "first_name": validated_data.get("first_name", instance.first_name),
            "last_name": validated_data.get("last_name", instance.last_name),
        }
        profile_fields = {
            "phone": validated_data.get("phone", profile.phone),
            "city": validated_data.get("city", profile.city),
            "address_line": validated_data.get("address_line", profile.address_line),
        }

        user_updates = []
        for field, value in user_fields.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                user_updates.append(field)

        profile_updates = []
        for field, value in profile_fields.items():
            if getattr(profile, field) != value:
                setattr(profile, field, value)
                profile_updates.append(field)

        if user_updates:
            instance.save(update_fields=user_updates)
        if profile_updates:
            profile.save(update_fields=profile_updates)

        return instance


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    terms_accepted = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "password", "confirm_password", "terms_accepted"]

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("confirm_password"):
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        if not attrs.get("terms_accepted"):
            raise serializers.ValidationError(
                {"terms_accepted": "You must accept terms to continue."}
            )

        try:
            validate_password(attrs.get("password"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        return attrs

    def _build_unique_username(self, email):
        base = email.strip().lower()
        if not base:
            base = "user"

        if len(base) > 140:
            local_part, _, domain_part = base.partition("@")
            trimmed_local = local_part[: max(1, 140 - len(domain_part) - 1)]
            base = f"{trimmed_local}@{domain_part}" if domain_part else trimmed_local

        candidate = base
        suffix = 1

        while User.objects.filter(username=candidate).exists():
            candidate = f"{base}_{suffix}"[:150]
            suffix += 1

        return candidate

    def create(self, validated_data):
        email = validated_data["email"]
        username = self._build_unique_username(email)

        user = User(
            username=username,
            email=email,
            is_active=False,
            activation_token=uuid.uuid4(),
            activation_token_created_at=timezone.now(),
        )
        user.set_password(validated_data["password"])
        try:
            user.save()
        except IntegrityError:
            raise serializers.ValidationError(
                {"email": "A user with this email already exists."}
            )

        activation_link = f"{settings.FRONTEND_BASE_URL}/activate/{user.activation_token}/"
        activation_text = f"Click the link to activate your account: {activation_link}"
        activation_html = _build_link_email_html(
            intro_text="Click the button below to activate your account.",
            action_label="Activate your account",
            url=activation_link,
        )
        try:
            send_auth_email(
                subject="Activate your account",
                text_content=activation_text,
                html_content=activation_html,
                recipients=[user.email],
            )
        except EmailDeliveryError:
            User.objects.filter(pk=user.pk).delete()
            raise

        return user


class ActivationSerializer(serializers.Serializer):
    token = serializers.UUIDField()

    def validate(self, attrs):
        token = attrs.get("token")
        try:
            user = User.objects.get(activation_token=token)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired token.")

        if (
            not user.activation_token_created_at
            or timezone.now() - user.activation_token_created_at > TOKEN_TTL
        ):
            raise serializers.ValidationError("Invalid or expired token.")

        attrs["user"] = user
        return attrs


class ResendActivationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, attrs):
        attrs["email"] = attrs.get("email").strip().lower()
        return attrs

    def save(self):
        email = self.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()

        # Keep response generic and do nothing for unknown/active accounts.
        if not user or user.is_active:
            return

        user.activation_token = uuid.uuid4()
        user.activation_token_created_at = timezone.now()
        user.save(update_fields=["activation_token", "activation_token_created_at"])

        activation_link = f"{settings.FRONTEND_BASE_URL}/activate/{user.activation_token}/"
        activation_text = f"Click the link to activate your account: {activation_link}"
        activation_html = _build_link_email_html(
            intro_text="Click the button below to activate your account.",
            action_label="Activate your account",
            url=activation_link,
        )
        try:
            send_auth_email(
                subject="Activate your account",
                text_content=activation_text,
                html_content=activation_html,
                recipients=[user.email],
            )
        except EmailDeliveryError:
            return


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        try:
            db_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials.")
        except User.MultipleObjectsReturned:
            raise serializers.ValidationError("Invalid credentials.")

        user = authenticate(username=db_user.username, password=password)

        if not user:
            raise serializers.ValidationError("Invalid credentials.")

        if not user.is_active:
            raise serializers.ValidationError("Account is not activated.")

        update_last_login(None, user)

        refresh = build_refresh_token_for_user(user)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()
        user = User.objects.filter(email__iexact=email).first()

        # Intentionally do not reveal whether the email exists.
        attrs["email"] = email
        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        if not user:
            return

        user.reset_password_token = uuid.uuid4()
        user.reset_password_token_created_at = timezone.now()
        user.save(update_fields=["reset_password_token", "reset_password_token_created_at"])

        reset_link = f"{settings.FRONTEND_BASE_URL}/reset-password/{user.reset_password_token}/"

        reset_text = f"Click the link to reset your password: {reset_link}"
        reset_html = _build_link_email_html(
            intro_text="Click the button below to reset your password.",
            action_label="Reset your password",
            url=reset_link,
        )
        try:
            send_auth_email(
                subject="Reset Your Password",
                text_content=reset_text,
                html_content=reset_html,
                recipients=[user.email],
            )
        except EmailDeliveryError:
            return


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        token = attrs.get("token")
        try:
            user = User.objects.get(reset_password_token=token)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired token.")

        if (
            not user.reset_password_token_created_at
            or timezone.now() - user.reset_password_token_created_at > TOKEN_TTL
        ):
            raise serializers.ValidationError("Invalid or expired token.")

        try:
            validate_password(attrs.get("password"), user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        password = self.validated_data["password"]

        with transaction.atomic():
            user.set_password(password)
            user.reset_password_token = None
            user.reset_password_token_created_at = None
            user.auth_token_version = get_auth_token_version(user) + 1
            user.save(
                update_fields=[
                    "password",
                    "reset_password_token",
                    "reset_password_token_created_at",
                    "auth_token_version",
                ]
            )
            revoke_user_refresh_tokens(user)


