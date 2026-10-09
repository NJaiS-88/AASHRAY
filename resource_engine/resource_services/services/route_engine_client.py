import logging
import os
from typing import Any, Literal

import httpx

from resource_services.schemas.common import Location
from resource_services.schemas.mission import RouteData, RouteLeg
from resource_services.schemas.orchestration import (
    RouteBoundaryResult,
    RoutingInputs,
)


logger = logging.getLogger(__name__)


class RouteEngineAPIError(Exception):
    """Raised when the Route Engine responds with an HTTP error (4xx/5xx)."""

    def __init__(self, status_code: int, message: str, details: Any = None):
        super().__init__(f"Route Engine returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.details = details


def decode_polyline(encoded: str) -> list[Location]:
    """Decode a Google-encoded polyline string into a list of Location objects."""
    if not encoded:
        return []

    coordinates: list[Location] = []
    index = 0
    length = len(encoded)
    lat = 0
    lng = 0

    while index < length:
        # Decode latitude
        shift = 0
        result = 0
        while index < length:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        # Decode longitude
        shift = 0
        result = 0
        while index < length:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coordinates.append(Location(latitude=lat / 1e5, longitude=lng / 1e5))

    return coordinates


def map_responder_vehicle_type(vehicle_type: str | None) -> str | None:
    """Map AASHRAY responder vehicle type to Route Engine resourceType."""
    if not vehicle_type:
        return None
    normalized = vehicle_type.upper()
    if normalized == "AMBULANCE":
        return "AMBULANCE"
    if normalized == "RESCUE_TRUCK":
        return "RESCUE_VEHICLE"
    if normalized == "FIRE_TRUCK":
        return "DEFAULT"
    return "DEFAULT"


def map_priority(priority: str | None) -> str | None:
    """Map AASHRAY allocation PriorityLevel to Route Engine priority enum.

    AASHRAY: LOW | MODERATE | HIGH | CRITICAL
    Route Engine: LOW | MEDIUM | HIGH | CRITICAL
    Missing / None: omitted (not defaulted to MEDIUM).
    """
    if not priority:
        return None
    normalized = priority.upper()
    if normalized == "LOW":
        return "LOW"
    if normalized == "MODERATE":
        return "MEDIUM"
    if normalized == "HIGH":
        return "HIGH"
    if normalized == "CRITICAL":
        return "CRITICAL"
    return None


def leg_mission_id(mission_id: str, leg_index: int) -> str:
    """Route Engine mission ID for one leg of an AASHRAY mission.

    The Route Engine keeps one MissionRouteState per missionId (upsert), so
    each leg needs its own ID or later legs overwrite earlier ones. The
    AASHRAY mission ID itself is unchanged.
    """
    return f"{mission_id}-LEG-{leg_index}"


class RouteEngineClient:
    """Boundary and adapter connecting AASHRAY to the external Route Engine.

    When ROUTE_ENGINE_URL is not set (default), returns ROUTE_ENGINE_NOT_CONNECTED.
    When configured, decomposes the mission into sequential legs:
      Responder -> Warehouse 1 -> Warehouse 2 ... -> Destination
    and queries the Route Engine for each leg, composing the result.
    Each leg is sent with its own missionId (see leg_mission_id).
    """

    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv("ROUTE_ENGINE_URL")
        )
        self.http_client = http_client
        self.timeout = timeout

    def plan_route(self, routing_inputs: RoutingInputs) -> RouteBoundaryResult:
        if not self.base_url:
            return RouteBoundaryResult(
                status="ROUTE_ENGINE_NOT_CONNECTED",
                routing_inputs=routing_inputs,
                message="Route Engine integration is pending; no route was requested.",
            )

        # Decompose mission into sequential waypoint legs:
        # Responder -> Warehouse 1 -> Warehouse 2 ... -> Destination
        waypoints: list[
            tuple[
                Literal["RESPONDER", "WAREHOUSE", "DESTINATION"],
                str,
                Location,
            ]
        ] = [
            (
                "RESPONDER",
                routing_inputs.responder_id,
                routing_inputs.responder_location,
            )
        ]

        for pickup in routing_inputs.pickups:
            waypoints.append(
                (
                    "WAREHOUSE",
                    pickup.warehouse_id,
                    pickup.location,
                )
            )

        waypoints.append(
            (
                "DESTINATION",
                "INCIDENT_DESTINATION",
                routing_inputs.destination,
            )
        )

        legs_to_plan: list[
            tuple[
                int,
                tuple[Literal["RESPONDER", "WAREHOUSE", "DESTINATION"], str, Location],
                tuple[Literal["RESPONDER", "WAREHOUSE", "DESTINATION"], str, Location],
            ]
        ] = []
        for i in range(len(waypoints) - 1):
            legs_to_plan.append((i, waypoints[i], waypoints[i + 1]))

        planned_legs: list[RouteLeg] = []
        client = self.http_client or httpx.Client(timeout=self.timeout)
        should_close_client = self.http_client is None

        try:
            for leg_index, (src_type, src_id, src_loc), (dst_type, dst_id, dst_loc) in legs_to_plan:
                route_engine_mission_id = leg_mission_id(
                    routing_inputs.mission_id,
                    leg_index,
                )

                payload: dict[str, Any] = {
                    "source": {
                        "latitude": src_loc.latitude,
                        "longitude": src_loc.longitude,
                    },
                    "destination": {
                        "latitude": dst_loc.latitude,
                        "longitude": dst_loc.longitude,
                    },
                    "missionId": route_engine_mission_id,
                    "resourceId": routing_inputs.responder_id,
                }

                mapped_vehicle = map_responder_vehicle_type(routing_inputs.vehicle_type)
                if mapped_vehicle:
                    payload["resourceType"] = mapped_vehicle

                mapped_priority = map_priority(routing_inputs.priority)
                if mapped_priority:
                    payload["priority"] = mapped_priority

                try:
                    response = client.post(
                        f"{self.base_url.rstrip('/')}/api/routes/optimize",
                        json=payload,
                    )
                except httpx.RequestError as exc:
                    logger.warning(
                        "Route Engine connection failed on leg %d: %s",
                        leg_index,
                        exc,
                    )
                    return RouteBoundaryResult(
                        status="ROUTE_ENGINE_NOT_CONNECTED",
                        routing_inputs=routing_inputs,
                        route=None,
                        message=(
                            f"Route Engine connection failed at leg {leg_index} "
                            f"({src_id} -> {dst_id}): {exc}"
                        ),
                    )

                if response.status_code == 400:
                    try:
                        err_body = response.json()
                    except Exception:
                        err_body = response.text
                    raise RouteEngineAPIError(400, "Validation Error", details=err_body)

                if response.status_code != 200:
                    raise RouteEngineAPIError(response.status_code, response.text)

                body = response.json()
                data = body.get("data", {})
                route_status = data.get("status")

                if route_status == "NO_SAFE_ROUTE_FOUND" or not data.get("primaryRoute"):
                    reasons = data.get("decisionReasons") or []
                    reasons_str = "; ".join(reasons) if reasons else "No safe route found"
                    return RouteBoundaryResult(
                        status="NO_SAFE_ROUTE_FOUND",
                        routing_inputs=routing_inputs,
                        route=RouteData(status="NOT_AVAILABLE"),
                        message=(
                            f"Leg {leg_index} ({src_id} -> {dst_id}) failed: {reasons_str}"
                        ),
                    )

                primary = data["primaryRoute"]
                dist_meters = primary.get("distanceMeters", 0)
                dur_seconds = primary.get("durationSeconds", 0)
                encoded_poly = primary.get("encodedPolyline")
                leg_coords = decode_polyline(encoded_poly) if encoded_poly else []
                assessment = primary.get("roadConditionAssessment") or {}

                raw_reasons = primary.get("reasons") or []
                reason_strings: list[str] = []
                for r in raw_reasons:
                    if isinstance(r, dict):
                        reason_strings.append(r.get("message", str(r)))
                    else:
                        reason_strings.append(str(r))

                planned_leg = RouteLeg(
                    leg_index=leg_index,
                    route_engine_mission_id=route_engine_mission_id,
                    source_type=src_type if src_type in ("RESPONDER", "WAREHOUSE") else "WAREHOUSE",
                    source_id=src_id,
                    destination_type=dst_type if dst_type in ("WAREHOUSE", "DESTINATION") else "DESTINATION",
                    destination_id=dst_id,
                    source_location=src_loc,
                    destination_location=dst_loc,
                    distance_km=round(dist_meters / 1000.0, 2),
                    estimated_time_minutes=round(dur_seconds / 60.0, 2),
                    coordinates=leg_coords,
                    encoded_polyline=encoded_poly,
                    route_id=primary.get("routeId"),
                    score=primary.get("score"),
                    road_condition_status=assessment.get("status"),
                    road_condition_confidence=assessment.get("confidence"),
                    matched_incidents=primary.get("matchedIncidents") or [],
                    reasons=reason_strings,
                )
                planned_legs.append(planned_leg)

        finally:
            if should_close_client:
                client.close()

        # Combine coordinates in mission order, deduplicating adjacent identical points
        combined_coords: list[Location] = []
        for leg in planned_legs:
            for coord in leg.coordinates:
                if (
                    combined_coords
                    and abs(combined_coords[-1].latitude - coord.latitude) < 1e-7
                    and abs(combined_coords[-1].longitude - coord.longitude) < 1e-7
                ):
                    continue
                combined_coords.append(coord)

        total_distance = round(sum(leg.distance_km for leg in planned_legs), 2)
        total_duration = round(sum(leg.estimated_time_minutes for leg in planned_legs), 2)

        combined_route = RouteData(
            status="AVAILABLE",
            distance_km=total_distance,
            estimated_time_minutes=total_duration,
            coordinates=combined_coords,
            legs=planned_legs,
        )

        return RouteBoundaryResult(
            status="ROUTE_PLANNED",
            routing_inputs=routing_inputs,
            route=combined_route,
            message=f"Successfully planned route across {len(planned_legs)} leg(s).",
        )
