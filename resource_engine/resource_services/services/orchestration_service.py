import logging
from pathlib import Path
from uuid import uuid4

from resource_services.schemas.agent_assignment import AgentAssignmentRequest
from resource_services.schemas.allocation import AllocationResult, WarehouseAllocation
from resource_services.schemas.demand_fulfilment import DemandFulfilmentRequest
from resource_services.schemas.mission import MissionCreationRequest
from resource_services.schemas.orchestration import (
    OrchestrationError,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStage,
    RouteBoundaryResult,
    RoutePickup,
    RoutingInputs,
)
from resource_services.schemas.resource_requirement import ResourceRequirementResult
from resource_services.services.agent_assignment_service import (
    AgentAssignmentService,
    NoResponderAvailableError,
)
from resource_services.services.demand_fulfilment_service import (
    DemandFulfilmentService,
)
from resource_services.services.mission_creation_service import (
    MissionCreationService,
)
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)
from resource_services.services.route_engine_client import RouteEngineClient


logger = logging.getLogger(__name__)

IMMEDIATE_RESPONSE_RESOURCES = {
    "search_and_rescue",
    "first_aid_trauma",
    "emergency_medical_care",
    "tools_equipment",
    "heavy_machinery_debris_clearance",
}

TIME_CRITICAL_INCIDENT_KEYWORDS = {
    "structural_collapse",
    "building_collapse",
    "collapse",
    "landslide",
    "earthquake",
    "debris_flow",
    "slab",
    "rubble",
    "trapped",
}


class OrchestrationService:
    def __init__(
        self,
        requirement_rules_path: str | Path,
        warehouses_path: str | Path,
        responders_path: str | Path,
        route_engine_client: RouteEngineClient | None = None,
    ):
        self.requirement_rules_path = requirement_rules_path
        self.warehouses_path = warehouses_path
        self.responders_path = responders_path
        self.route_engine_client = route_engine_client or RouteEngineClient()

    def _should_use_two_phase(self, request: OrchestrationRequest, requirement: ResourceRequirementResult) -> bool:
        norm_type = (request.incident_type or "").lower().strip().replace(" ", "_").replace("-", "_")
        is_type_match = any(k in norm_type for k in ["collapse", "slab", "landslide", "earthquake", "trapped"])

        hazard_details = getattr(request, "hazard_details", []) or []
        has_hazard_keyword = any(
            any(k in str(h).lower() for k in ["collapse", "slab", "landslide", "rubble", "trapped"])
            for h in hazard_details
        )

        locality_name = getattr(request.locality, "name", "").lower()
        has_loc_keyword = any(k in locality_name for k in ["collapse", "slab", "landslide", "earthquake"])

        if not (is_type_match or has_hazard_keyword or has_loc_keyword):
            return False

        reqs = requirement.requirements or {}
        has_immediate = any(k in IMMEDIATE_RESPONSE_RESOURCES and (v or 0) > 0 for k, v in reqs.items())
        has_followup = any(k not in IMMEDIATE_RESPONSE_RESOURCES and (v or 0) > 0 for k, v in reqs.items())

        return has_immediate and has_followup

    def run(self, request: OrchestrationRequest) -> OrchestrationResult:
        result = OrchestrationResult(
            orchestration_id=f"ORCH-{uuid4().hex[:8].upper()}",
            incident_id=request.incident_id,
            status="FAILED",
            phase="SINGLE_PHASE",
        )

        # STEP 1 - Resource Requirement
        try:
            requirement = ResourceRequirementService(
                self.requirement_rules_path
            ).calculate(request, urgency=request.urgency)
        except Exception as error:
            return self._failed(result, "REQUIREMENT", error)

        result.requirement = requirement
        result.completed_stages.append("REQUIREMENT")

        # Check for Two-Phase Emergency Mission
        if self._should_use_two_phase(request, requirement):
            logger.info("Triggering Two-Phase Emergency Mission for time-critical incident %s (%s)", request.incident_id, request.incident_type)
            return self._run_two_phase(request, requirement)

        # STEP 2 - Resource Allocation (urgency/priority come from the request)
        try:
            allocation_service = ResourceAllocationService(
                self.warehouses_path,
                self.requirement_rules_path,
            )

            allocation = allocation_service.allocate(
                incident_id=request.incident_id,
                requirements=requirement.requirements,
                severity=request.severity,
                urgency=request.urgency,
                priority=request.priority,
            )
        except Exception as error:
            return self._failed(result, "ALLOCATION", error)

        result.allocation = allocation
        result.completed_stages.append("ALLOCATION")

        # STEP 3 - Demand Fulfilment
        try:
            demand_fulfilment = DemandFulfilmentService().verify(
                DemandFulfilmentRequest(
                    allocation_id=allocation.allocation_id,
                    incident_id=allocation.incident_id,
                    required_resources=allocation.required_resources,
                    allocated_resources=allocation.allocated_resources,
                )
            )
        except Exception as error:
            return self._failed(result, "DEMAND_FULFILMENT", error)

        result.demand_fulfilment = demand_fulfilment
        result.fulfilment_status = demand_fulfilment.fulfilment_status
        result.completed_stages.append("DEMAND_FULFILMENT")

        # STEP 4 - Mission Creation
        try:
            mission_request = self._build_mission_request(
                request,
                allocation,
                allocation_service,
            )
            mission_request.phase = "SINGLE_PHASE"

            mission = MissionCreationService().create_mission(mission_request)
        except Exception as error:
            return self._failed(result, "MISSION_CREATION", error)

        result.mission = mission
        result.completed_stages.append("MISSION_CREATION")

        if not mission_request.warehouse_pickups:
            result.status = "MISSION_NOT_DISPATCHABLE"
            result.error = OrchestrationError(
                stage="AGENT_ASSIGNMENT",
                error_code="NO_WAREHOUSE_PICKUP",
                message=(
                    "Allocation produced no warehouse pickup, so there is no "
                    "pickup location to assign a responder to. Agent "
                    "Assignment was not called."
                ),
            )
            return result

        # STEP 5 - Agent Assignment
        first_pickup = mission_request.warehouse_pickups[0]

        try:
            assignment = AgentAssignmentService(self.responders_path).assign(
                AgentAssignmentRequest(
                    mission_id=mission.mission_id,
                    required_responder_types=mission.required_responder_types,
                    first_warehouse_location=first_pickup.location,
                    first_warehouse_id=first_pickup.warehouse_id,
                )
            )
        except NoResponderAvailableError as error:
            result.status = "NO_RESPONDER_AVAILABLE"
            result.error = OrchestrationError(
                stage="AGENT_ASSIGNMENT",
                error_code=error.error_code,
                message=str(error),
            )
            return result
        except Exception as error:
            return self._failed(result, "AGENT_ASSIGNMENT", error)

        result.agent_assignment = assignment
        result.completed_stages.append("AGENT_ASSIGNMENT")

        # STEP 6 - Route Engine boundary
        try:
            route = self.route_engine_client.plan_route(
                RoutingInputs(
                    mission_id=mission.mission_id,
                    responder_id=assignment.responder_id,
                    responder_location=assignment.responder_location,
                    pickups=[
                        RoutePickup(
                            warehouse_id=pickup.warehouse_id,
                            location=pickup.location,
                        )
                        for pickup in mission_request.warehouse_pickups
                    ],
                    destination=mission.destination,
                    vehicle_type=assignment.responder_type,
                    priority=allocation.final_priority_level,
                )
            )
        except Exception as error:
            return self._failed(result, "ROUTE_ENGINE", error)

        # Check emergency response threshold and evaluate potential safeguards
        if route.status == "ROUTE_PLANNED" and route.route and route.route.estimated_time_minutes is not None:
            threshold = self._get_emergency_threshold(request.incident_type, allocation.final_priority_level)
            route.route.emergency_threshold_minutes = threshold

            if route.route.estimated_time_minutes > threshold:
                logger.warning(
                    "Mission %s route ETA (%.1f min) exceeds emergency threshold (%.1f min) for %s",
                    mission.mission_id,
                    route.route.estimated_time_minutes,
                    threshold,
                    request.incident_type,
                )
                try:
                    assignment_svc = AgentAssignmentService(self.responders_path)
                    all_resp = assignment_svc.responders
                    required_types = set(mission.required_responder_types)
                    other_eligible = [
                        r for r in all_resp
                        if r.status == "AVAILABLE"
                        and r.vehicle_type in required_types
                        and r.responder_id != assignment.responder_id
                    ]

                    for alt_resp in other_eligible:
                        alt_inputs = RoutingInputs(
                            mission_id=mission.mission_id,
                            responder_id=alt_resp.responder_id,
                            responder_location=alt_resp.location,
                            pickups=[
                                RoutePickup(
                                    warehouse_id=pickup.warehouse_id,
                                    location=pickup.location,
                                )
                                for pickup in mission_request.warehouse_pickups
                            ],
                            destination=mission.destination,
                            vehicle_type=alt_resp.vehicle_type,
                            priority=allocation.final_priority_level,
                        )
                        alt_route = self.route_engine_client.plan_route(alt_inputs)
                        if (
                            alt_route.status == "ROUTE_PLANNED"
                            and alt_route.route
                            and alt_route.route.estimated_time_minutes is not None
                            and alt_route.route.estimated_time_minutes < route.route.estimated_time_minutes
                        ):
                            assignment_svc._update_status(assignment.responder_id, from_status="BUSY", to_status="AVAILABLE")
                            assignment_svc._update_status(alt_resp.responder_id, from_status="AVAILABLE", to_status="BUSY")
                            assignment_svc._record_assignment(mission.mission_id, assignment.assignment_id, alt_resp.responder_id)

                            assignment.responder_id = alt_resp.responder_id
                            assignment.responder_name = alt_resp.name
                            assignment.responder_location = alt_resp.location
                            assignment.responder_type = alt_resp.vehicle_type
                            route = alt_route
                            route.route.emergency_threshold_minutes = threshold
                            logger.info(
                                "Emergency ETA safeguard switched mission %s to closer responder %s (new ETA: %.1f min)",
                                mission.mission_id,
                                alt_resp.responder_id,
                                route.route.estimated_time_minutes,
                            )
                            break
                except Exception as eval_err:
                    logger.warning("Error evaluating alternative responders during ETA safeguard: %s", eval_err)

                if route.route.estimated_time_minutes > threshold:
                    route.route.emergency_threshold_exceeded = True
                    route.route.eta_review_escalation = True
                    route.route.emergency_threshold_warning = (
                        f"EMERGENCY ETA ESCALATION: Estimated arrival time ({route.route.estimated_time_minutes:.1f} mins) "
                        f"exceeds the operational target of {threshold:.0f} mins for {request.incident_type}. "
                        "Priority review and emergency dispatch escalation active."
                    )

        result.route = route
        result.completed_stages.append("ROUTE_ENGINE")

        if route.status == "ROUTE_PLANNED":
            result.status = "COMPLETED"
        elif route.status == "NO_SAFE_ROUTE_FOUND":
            result.status = "NO_SAFE_ROUTE_FOUND"
        else:
            result.status = "ROUTE_ENGINE_NOT_CONNECTED"

        return result

    def _run_two_phase(
        self,
        request: OrchestrationRequest,
        requirement: ResourceRequirementResult,
    ) -> OrchestrationResult:
        immediate_reqs = {
            k: v for k, v in requirement.requirements.items()
            if k in IMMEDIATE_RESPONSE_RESOURCES and (v or 0) > 0
        }
        follow_up_reqs = {
            k: v for k, v in requirement.requirements.items()
            if k not in IMMEDIATE_RESPONSE_RESOURCES and (v or 0) > 0
        }

        allocation_service = ResourceAllocationService(
            self.warehouses_path,
            self.requirement_rules_path,
        )
        working_inventory = allocation_service._build_working_inventory()
        parent_mission_id = f"MIS-{uuid4().hex[:8].upper()}"

        # -------------------------------------------------------------
        # SUB-MISSION A: IMMEDIATE_RESPONSE
        # -------------------------------------------------------------
        res_a = OrchestrationResult(
            orchestration_id=f"ORCH-{uuid4().hex[:8].upper()}-A",
            incident_id=request.incident_id,
            status="FAILED",
            phase="IMMEDIATE_RESPONSE",
            parent_mission_id=parent_mission_id,
        )
        res_a.completed_stages.append("REQUIREMENT")
        res_a.requirement = ResourceRequirementResult(
            incident_id=request.incident_id,
            requirements=immediate_reqs,
        )

        try:
            alloc_a = allocation_service._allocate_from_inventory(
                incident_id=f"{request.incident_id}-A",
                requirements=immediate_reqs,
                severity=request.severity,
                urgency=request.urgency,
                priority=request.priority,
                working_inventory=working_inventory,
            )
            res_a.allocation = alloc_a
            res_a.completed_stages.append("ALLOCATION")
        except Exception as error:
            return self._failed(res_a, "ALLOCATION", error)

        try:
            demand_a = DemandFulfilmentService().verify(
                DemandFulfilmentRequest(
                    allocation_id=alloc_a.allocation_id,
                    incident_id=alloc_a.incident_id,
                    required_resources=alloc_a.required_resources,
                    allocated_resources=alloc_a.allocated_resources,
                )
            )
            res_a.demand_fulfilment = demand_a
            res_a.fulfilment_status = demand_a.fulfilment_status
            res_a.completed_stages.append("DEMAND_FULFILMENT")
        except Exception as error:
            return self._failed(res_a, "DEMAND_FULFILMENT", error)

        try:
            mission_req_a = self._build_mission_request(
                request,
                alloc_a,
                allocation_service,
            )
            mission_req_a.phase = "IMMEDIATE_RESPONSE"
            mission_req_a.parent_mission_id = parent_mission_id
            mission_a = MissionCreationService().create_mission(mission_req_a)
            mission_a.mission_id = f"{parent_mission_id}-A"
            res_a.mission = mission_a
            res_a.completed_stages.append("MISSION_CREATION")
        except Exception as error:
            return self._failed(res_a, "MISSION_CREATION", error)

        assignment_a = None
        route_a = None

        if not mission_req_a.warehouse_pickups:
            res_a.status = "MISSION_NOT_DISPATCHABLE"
        else:
            first_pickup_a = mission_req_a.warehouse_pickups[0]
            try:
                assignment_a = AgentAssignmentService(self.responders_path).assign(
                    AgentAssignmentRequest(
                        mission_id=mission_a.mission_id,
                        required_responder_types=mission_a.required_responder_types,
                        first_warehouse_location=first_pickup_a.location,
                        first_warehouse_id=first_pickup_a.warehouse_id,
                    )
                )
                res_a.agent_assignment = assignment_a
                res_a.completed_stages.append("AGENT_ASSIGNMENT")
            except NoResponderAvailableError as error:
                res_a.status = "NO_RESPONDER_AVAILABLE"
                res_a.error = OrchestrationError(
                    stage="AGENT_ASSIGNMENT",
                    error_code=error.error_code,
                    message=str(error),
                )
            except Exception as error:
                return self._failed(res_a, "AGENT_ASSIGNMENT", error)

            if assignment_a:
                try:
                    route_a = self.route_engine_client.plan_route(
                        RoutingInputs(
                            mission_id=mission_a.mission_id,
                            responder_id=assignment_a.responder_id,
                            responder_location=assignment_a.responder_location,
                            pickups=[
                                RoutePickup(
                                    warehouse_id=p.warehouse_id,
                                    location=p.location,
                                )
                                for p in mission_req_a.warehouse_pickups
                            ],
                            destination=mission_a.destination,
                            vehicle_type=assignment_a.responder_type,
                            priority=alloc_a.final_priority_level,
                        )
                    )
                    res_a.route = route_a
                    res_a.completed_stages.append("ROUTE_ENGINE")

                    if route_a.status == "ROUTE_PLANNED" and route_a.route and route_a.route.estimated_time_minutes is not None:
                        threshold = self._get_emergency_threshold(request.incident_type, alloc_a.final_priority_level)
                        route_a.route.emergency_threshold_minutes = threshold

                        if route_a.route.estimated_time_minutes > threshold:
                            route_a.route.emergency_threshold_exceeded = True
                            route_a.route.eta_review_escalation = True
                            route_a.route.emergency_threshold_warning = (
                                f"EMERGENCY ETA ESCALATION: Sub-Mission A arrival time ({route_a.route.estimated_time_minutes:.1f} mins) "
                                f"exceeds operational target of {threshold:.0f} mins for time-critical incident. Priority corridor escort active."
                            )

                    if route_a.status == "ROUTE_PLANNED":
                        res_a.status = "COMPLETED"
                    elif route_a.status == "NO_SAFE_ROUTE_FOUND":
                        res_a.status = "NO_SAFE_ROUTE_FOUND"
                    else:
                        res_a.status = "ROUTE_ENGINE_NOT_CONNECTED"
                except Exception as error:
                    return self._failed(res_a, "ROUTE_ENGINE", error)

        # -------------------------------------------------------------
        # SUB-MISSION B: FOLLOW_UP_LOGISTICS
        # -------------------------------------------------------------
        res_b = OrchestrationResult(
            orchestration_id=f"ORCH-{uuid4().hex[:8].upper()}-B",
            incident_id=request.incident_id,
            status="FAILED",
            phase="FOLLOW_UP_LOGISTICS",
            parent_mission_id=parent_mission_id,
        )
        res_b.completed_stages.append("REQUIREMENT")
        res_b.requirement = ResourceRequirementResult(
            incident_id=request.incident_id,
            requirements=follow_up_reqs,
        )

        try:
            # Reconcile shared inventory: working_inventory already deducted by Phase A! Zero stock duplication!
            alloc_b = allocation_service._allocate_from_inventory(
                incident_id=f"{request.incident_id}-B",
                requirements=follow_up_reqs,
                severity=request.severity,
                urgency=request.urgency,
                priority=request.priority,
                working_inventory=working_inventory,
            )
            res_b.allocation = alloc_b
            res_b.completed_stages.append("ALLOCATION")
        except Exception as error:
            return self._failed(res_b, "ALLOCATION", error)

        try:
            demand_b = DemandFulfilmentService().verify(
                DemandFulfilmentRequest(
                    allocation_id=alloc_b.allocation_id,
                    incident_id=alloc_b.incident_id,
                    required_resources=alloc_b.required_resources,
                    allocated_resources=alloc_b.allocated_resources,
                )
            )
            res_b.demand_fulfilment = demand_b
            res_b.fulfilment_status = demand_b.fulfilment_status
            res_b.completed_stages.append("DEMAND_FULFILMENT")
        except Exception as error:
            return self._failed(res_b, "DEMAND_FULFILMENT", error)

        try:
            mission_req_b = self._build_mission_request(
                request,
                alloc_b,
                allocation_service,
            )
            mission_req_b.phase = "FOLLOW_UP_LOGISTICS"
            mission_req_b.parent_mission_id = parent_mission_id
            mission_b = MissionCreationService().create_mission(mission_req_b)
            mission_b.mission_id = f"{parent_mission_id}-B"
            res_b.mission = mission_b
            res_b.completed_stages.append("MISSION_CREATION")
        except Exception as error:
            return self._failed(res_b, "MISSION_CREATION", error)

        assignment_b = None
        route_b = None

        if not mission_req_b.warehouse_pickups:
            res_b.status = "MISSION_NOT_DISPATCHABLE"
        else:
            first_pickup_b = mission_req_b.warehouse_pickups[0]
            try:
                assignment_b = AgentAssignmentService(self.responders_path).assign(
                    AgentAssignmentRequest(
                        mission_id=mission_b.mission_id,
                        required_responder_types=mission_b.required_responder_types,
                        first_warehouse_location=first_pickup_b.location,
                        first_warehouse_id=first_pickup_b.warehouse_id,
                    )
                )
                res_b.agent_assignment = assignment_b
                res_b.completed_stages.append("AGENT_ASSIGNMENT")
            except NoResponderAvailableError:
                # Phase B responder unavailability does not derail Phase A!
                res_b.status = "NO_RESPONDER_AVAILABLE"
            except Exception as error:
                logger.warning("Phase B assignment error: %s", error)
                res_b.status = "NO_RESPONDER_AVAILABLE"

            if assignment_b:
                try:
                    route_b = self.route_engine_client.plan_route(
                        RoutingInputs(
                            mission_id=mission_b.mission_id,
                            responder_id=assignment_b.responder_id,
                            responder_location=assignment_b.responder_location,
                            pickups=[
                                RoutePickup(
                                    warehouse_id=p.warehouse_id,
                                    location=p.location,
                                )
                                for p in mission_req_b.warehouse_pickups
                            ],
                            destination=mission_b.destination,
                            vehicle_type=assignment_b.responder_type,
                            priority=alloc_b.final_priority_level,
                        )
                    )
                    res_b.route = route_b
                    res_b.completed_stages.append("ROUTE_ENGINE")

                    if route_b.status == "ROUTE_PLANNED":
                        res_b.status = "COMPLETED"
                    elif route_b.status == "NO_SAFE_ROUTE_FOUND":
                        res_b.status = "NO_SAFE_ROUTE_FOUND"
                    else:
                        res_b.status = "ROUTE_ENGINE_NOT_CONNECTED"
                except Exception as error:
                    logger.warning("Phase B route planning error: %s", error)
                    res_b.status = "ROUTE_ENGINE_NOT_CONNECTED"

        # -------------------------------------------------------------
        # COMBINED PARENT ORCHESTRATION RESULT
        # -------------------------------------------------------------
        combined_allocated = dict(alloc_a.allocated_resources)
        for r_k, r_v in alloc_b.allocated_resources.items():
            combined_allocated[r_k] = combined_allocated.get(r_k, 0.0) + r_v

        combined_wh_map = {}
        for wa in alloc_a.warehouse_allocations + alloc_b.warehouse_allocations:
            if wa.warehouse_id not in combined_wh_map:
                combined_wh_map[wa.warehouse_id] = dict(wa.supplies)
            else:
                for k, v in wa.supplies.items():
                    combined_wh_map[wa.warehouse_id][k] = combined_wh_map[wa.warehouse_id].get(k, 0.0) + v

        combined_warehouse_allocations = [
            WarehouseAllocation(warehouse_id=wid, supplies=supp)
            for wid, supp in combined_wh_map.items()
        ]

        remaining_shortage = {
            r_k: max(0.0, float(requirement.requirements.get(r_k, 0.0)) - float(combined_allocated.get(r_k, 0.0)))
            for r_k in requirement.requirements
        }
        total_required = sum(requirement.requirements.values())
        total_allocated = sum(combined_allocated.values())
        if total_allocated == 0:
            alloc_status = "FAILED"
        elif total_allocated >= total_required:
            alloc_status = "ALLOCATED"
        else:
            alloc_status = "PARTIAL"

        combined_alloc = AllocationResult(
            allocation_id=f"ALL-{uuid4().hex[:8].upper()}",
            incident_id=request.incident_id,
            required_resources=requirement.requirements,
            warehouse_allocations=combined_warehouse_allocations,
            allocated_resources=combined_allocated,
            remaining_shortage=remaining_shortage,
            allocation_status=alloc_status,
            normalized_priority=alloc_a.normalized_priority,
            overall_priority_score=alloc_a.overall_priority_score,
            final_priority_level=alloc_a.final_priority_level,
        )

        combined_demand = DemandFulfilmentService().verify(
            DemandFulfilmentRequest(
                allocation_id=combined_alloc.allocation_id,
                incident_id=request.incident_id,
                required_resources=combined_alloc.required_resources,
                allocated_resources=combined_alloc.allocated_resources,
            )
        )

        parent_result = OrchestrationResult(
            orchestration_id=f"ORCH-{uuid4().hex[:8].upper()}",
            incident_id=request.incident_id,
            status=res_a.status,
            phase="TWO_PHASE_COORDINATED",
            fulfilment_status=combined_demand.fulfilment_status,
            completed_stages=[
                "REQUIREMENT",
                "ALLOCATION",
                "DEMAND_FULFILMENT",
                "MISSION_CREATION",
                "AGENT_ASSIGNMENT",
                "ROUTE_ENGINE",
            ],
            requirement=requirement,
            allocation=combined_alloc,
            demand_fulfilment=combined_demand,
            mission=mission_a,
            agent_assignment=assignment_a,
            route=route_a,
            sub_missions=[res_a, res_b],
        )

        return parent_result

    def _build_mission_request(
        self,
        request: OrchestrationRequest,
        allocation: AllocationResult,
        allocation_service: ResourceAllocationService,
    ) -> MissionCreationRequest:
        locations = {
            warehouse.warehouse_id: warehouse.location
            for warehouse in allocation_service.warehouses
        }

        return MissionCreationRequest(
            incident_id=request.incident_id,
            destination=request.location,
            risk_score=request.severity,
            priority=allocation.final_priority_level,
            patient_present=request.patient_present,
            resources=allocation.allocated_resources,
            warehouse_pickups=[
                {
                    "warehouse_id": pickup.warehouse_id,
                    "location": locations[pickup.warehouse_id],
                    "supplies": pickup.supplies,
                }
                for pickup in allocation.warehouse_allocations
            ],
            affected_population=request.locality.affected_population,
            risk_indicators=getattr(request, "hazard_details", []) or [],
            incident_type=request.incident_type,
        )

    def _failed(
        self,
        result: OrchestrationResult,
        stage: OrchestrationStage,
        error: Exception,
    ) -> OrchestrationResult:
        logger.exception(
            "Orchestration %s stopped at %s",
            result.orchestration_id,
            stage,
        )

        result.status = "FAILED"
        result.error = OrchestrationError(
            stage=stage,
            error_code="STAGE_FAILED",
            message=f"{type(error).__name__}: {error}",
        )

        return result

    def _get_emergency_threshold(self, incident_type: str | None, priority_level: str | None) -> float:
        import os, json
        env_override = os.getenv("EMERGENCY_ETA_THRESHOLD_MINUTES")
        if env_override:
            try:
                return float(env_override)
            except ValueError:
                pass

        try:
            with open(self.requirement_rules_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
            thresholds = rules.get("emergency_response_thresholds", {})
            cats = thresholds.get("categories", {})
            norm_type = (incident_type or "").lower().strip().replace(" ", "_").replace("-", "_")

            time_critical_cats = {
                "structural_collapse": 90.0,
                "building_collapse": 90.0,
                "collapse": 90.0,
                "landslide": 90.0,
                "earthquake": 90.0,
            }

            base = cats.get(norm_type) or time_critical_cats.get(norm_type)
            if base is not None:
                if priority_level == "CRITICAL":
                    base *= thresholds.get("severity_multipliers", {}).get("CRITICAL", 1.0)
                return round(float(base), 1)

            return float(thresholds.get("default_threshold_minutes", 90.0))
        except Exception:
            return 90.0 if (incident_type and any(k in incident_type.lower() for k in ["collapse", "slab", "landslide", "earthquake"])) else 120.0
