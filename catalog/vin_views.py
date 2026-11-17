from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .vin import decode_vehicle, normalize_vin, resolve_vehicle


class VehicleVinAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "vin_lookup"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def post(self, request):
        vin = normalize_vin(request.data.get("vin") if isinstance(request.data, dict) else None)
        if not vin:
            return Response({"status": "invalid_vin"}, status=400)
        result = decode_vehicle(vin)
        if result["status"] == "decoded":
            result = resolve_vehicle(result["vehicle"])
        return Response(result, status=503 if result["status"] == "unavailable" else 200)
