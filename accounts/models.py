from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class CustomUser(AbstractUser):
    email = models.EmailField("email address", unique=True)
    activation_token = models.UUIDField(default=uuid.uuid4, null=True, blank=True)
    activation_token_created_at = models.DateTimeField(null=True, blank=True)
    reset_password_token = models.UUIDField(null=True, blank=True)
    reset_password_token_created_at = models.DateTimeField(null=True, blank=True)
    auth_token_version = models.PositiveIntegerField(default=0)

    """
    Custom User model.
    Keep auth data here; profile-specific delivery fields live in UserProfile.
    """


class GoogleAccount(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="google_account",
    )
    google_sub = models.CharField(max_length=255, unique=True)
    email = models.EmailField()
    email_verified = models.BooleanField(default=False)
    full_name = models.CharField(max_length=255, blank=True, default="")
    picture_url = models.URLField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["email"], name="accounts_google_email_idx"),
        ]

    def __str__(self):
        return f"Google account for {self.email}"


class UserProfile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone = models.CharField(max_length=50, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    address_line = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return f"Profile for {self.user.email}"
