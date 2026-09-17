"""Measurement ingest (bulk-capable) + time-range query with granularity.

Ingest path:
1. validate payload(s)
2. resolve baby from the bracelet's current pairing
3. bulk-insert measurements, update bracelet last_seen/battery
4. run CRITICAL rules synchronously (SpO2/HR)
5. queue non-critical rules on Celery
"""
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from analysis.rules import run_rules
from analysis.tasks import evaluate_non_critical_rules
from babies.views import babies_for
from bracelets.views import bracelets_for
from common.pagination import DefaultPagination
from .models import Measurement
from .serializers import (
    MeasurementBucketSerializer,
    MeasurementIngestSerializer,
    MeasurementSerializer,
)

MAX_BULK = 500          # bound bulk ingest size
MAX_RANGE_DAYS = 92     # bound query windows (no unbounded queries)
GRANULARITIES = {"raw": None, "minute": 60, "hour": 3600, "day": 86400}


class IngestThrottle(UserRateThrottle):
    scope = "ingest"


class MeasurementIngestQueryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        if self.request.method == "POST":
            return [IngestThrottle()]
        return super().get_throttles()

    # ------------------------------------------------------------------ POST
    def post(self, request):
        payload = request.data if isinstance(request.data, list) else [request.data]
        if len(payload) > MAX_BULK:
            return Response(
                {"detail": f"Bulk ingest limited to {MAX_BULK} measurements."}, status=400
            )
        serializer = MeasurementIngestSerializer(data=payload, many=True)
        serializer.is_valid(raise_exception=True)

        allowed_bracelets = {b.id: b for b in bracelets_for(request.user).distinct()}
        to_create, errors = [], []
        touched_bracelets = {}
        for item in serializer.validated_data:
            bracelet = item["bracelet"]
            if bracelet.id not in allowed_bracelets:
                errors.append({"bracelet": bracelet.id, "detail": "Not your bracelet."})
                continue
            if bracelet.baby_id is None:
                errors.append({"bracelet": bracelet.id, "detail": "Bracelet not paired."})
                continue
            to_create.append(Measurement(baby_id=bracelet.baby_id, **item))
            touched_bracelets[bracelet.id] = item

        if errors and not to_create:
            return Response({"errors": errors}, status=400)

        created = Measurement.objects.bulk_create(to_create)

        # Update bracelet liveness/battery from the latest sample per bracelet.
        now = timezone.now()
        for bid, item in touched_bracelets.items():
            bracelet = allowed_bracelets[bid]
            bracelet.last_seen_at = now
            if item.get("battery") is not None:
                bracelet.battery_level = item["battery"]
            bracelet.save(update_fields=["last_seen_at", "battery_level"])
            # Auto-resolve any open NO_DATA alert now that data flows again.
            from alerts.models import Alert

            Alert.objects.filter(
                baby_id=bracelet.baby_id, type=Alert.Type.NO_DATA, resolved_at__isnull=True
            ).update(resolved_at=now)

        # bulk_create with SQLite/Postgres returns objects with PKs — run rules.
        alerts_created = 0
        for m in created:
            alerts_created += len(run_rules(m, critical_only=True))  # sync, latency-critical
            evaluate_non_critical_rules.delay(m.id)                  # async remainder

        return Response(
            {"created": len(created), "alerts_triggered": alerts_created, "errors": errors},
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------- GET
    def get(self, request):
        baby_id = request.query_params.get("baby_id")
        if not baby_id:
            return Response({"detail": "baby_id is required."}, status=400)
        baby = babies_for(request.user).filter(pk=baby_id).first()
        if baby is None:
            return Response({"detail": "Baby not found."}, status=404)

        to = parse_datetime(request.query_params.get("to", "")) or timezone.now()
        frm = parse_datetime(request.query_params.get("from", "")) or (to - timedelta(hours=24))
        if to - frm > timedelta(days=MAX_RANGE_DAYS):
            return Response({"detail": f"Range limited to {MAX_RANGE_DAYS} days."}, status=400)

        granularity = request.query_params.get("granularity", "raw")
        if granularity not in GRANULARITIES:
            return Response({"detail": f"granularity must be one of {list(GRANULARITIES)}."}, status=400)

        qs = Measurement.objects.filter(
            baby=baby, recorded_at__gte=frm, recorded_at__lte=to
        ).order_by("recorded_at")

        if granularity == "raw":
            paginator = DefaultPagination()
            page = paginator.paginate_queryset(qs, request)
            return paginator.get_paginated_response(
                MeasurementSerializer(page, many=True).data
            )

        # Aggregated buckets computed in SQL-portable Python (bounded window).
        seconds = GRANULARITIES[granularity]
        buckets: dict[int, dict] = {}
        for m in qs.iterator(chunk_size=1000):
            key = int(m.recorded_at.timestamp()) // seconds * seconds
            b = buckets.setdefault(
                key, {"hr": [], "temp": [], "spo2": [], "battery": [], "movement": [], "count": 0}
            )
            b["count"] += 1
            if m.heart_rate is not None:
                b["hr"].append(m.heart_rate)
            if m.temperature is not None:
                b["temp"].append(m.temperature)
            if m.spo2 is not None:
                b["spo2"].append(m.spo2)
            if m.battery is not None:
                b["battery"].append(m.battery)
            if m.movement and m.movement.get("magnitude") is not None:
                b["movement"].append(m.movement["magnitude"])

        def avg(xs):
            return round(sum(xs) / len(xs), 2) if xs else None

        results = [
            {
                "bucket": timezone.datetime.fromtimestamp(k, tz=timezone.get_current_timezone()),
                "heart_rate_avg": avg(v["hr"]),
                "temperature_avg": avg(v["temp"]),
                "spo2_avg": avg(v["spo2"]),
                "battery_avg": avg(v["battery"]),
                "movement_magnitude_avg": avg(v["movement"]),
                "heart_rate_min": min(v["hr"]) if v["hr"] else None,
                "heart_rate_max": max(v["hr"]) if v["hr"] else None,
                "count": v["count"],
            }
            for k, v in sorted(buckets.items())
        ]
        return Response({"granularity": granularity, "results": MeasurementBucketSerializer(results, many=True).data})
