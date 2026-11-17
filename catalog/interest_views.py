import logging

from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authenticate import CustomAuthentication
from business.vehicle_demand import record_interest


class VehicleInterestInput(serializers.Serializer):
    session_id = serializers.UUIDField()
    analytics_consent = serializers.BooleanField()
    lookup_token = serializers.CharField(max_length=4096, required=False)
    make = serializers.CharField(max_length=140, required=False)
    model = serializers.CharField(max_length=140, required=False)
    year = serializers.IntegerField(min_value=1900, max_value=2100, required=False, allow_null=True)
    variant = serializers.CharField(max_length=100, required=False, allow_blank=True)
    result_count = serializers.IntegerField(min_value=0, max_value=1000000, required=False)


class VehicleInterestView(APIView):
    authentication_classes = (CustomAuthentication, SessionAuthentication)
    permission_classes = (AllowAny,)
    throttle_scope = "vehicle_interest"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def post(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return Response(status=204)
        fields = VehicleInterestInput()
        if not isinstance(request.data, dict) or set(request.data) - set(fields.fields):
            return Response({"detail": "Invalid interest fields."}, status=400)
        payload = VehicleInterestInput(data=request.data)
        if not payload.is_valid():
            return Response({"detail": "Invalid interest data."}, status=400)
        values = payload.validated_data
        if not values["analytics_consent"]:
            return Response(status=204)
        try:
            record_interest(values)
        except (signing.BadSignature, ObjectDoesNotExist, ValueError, KeyError, TypeError):
            return Response({"detail": "Unknown vehicle interest."}, status=400)
        except DatabaseError:
            logging.getLogger(__name__).warning("vehicle_interest_storage_unavailable")
            return Response({"detail": "Collection unavailable."}, status=503)
        return Response(status=204)
