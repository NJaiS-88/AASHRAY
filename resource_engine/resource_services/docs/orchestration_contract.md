# Orchestration Contract

Integration rules between the existing services and the MVP orchestrator
(`services/orchestration_service.py`, `POST /orchestrate`). This document
records the contracts it follows and the design decisions taken for the MVP.
Items marked **RULE** or **DECIDED** are agreed decisions. Items marked
**PENDING** have no implementation yet.

## Service chain

```
Incident
  → Resource Requirement   (ResourceRequirementService.calculate)
  → Resource Allocation    (ResourceAllocationService.allocate)
  → Demand Fulfilment      (DemandFulfilmentService.verify)
  → Mission Creation       (MissionCreationService.create_mission)
  → Agent Assignment       (AgentAssignmentService.assign)
  → Route Engine boundary  (RouteEngineClient.plan_route; PENDING, see "Route Engine")
```

`OrchestrationService.run` executes this chain in order and stops at the
first stage that cannot continue. `tests/test_mission_pipeline.py` also runs
the chain with its own test wiring; `tests/test_orchestrator.py` tests the
orchestrator itself.

## Orchestrator (MVP)

**Input: `OrchestrationRequest`** (`schemas/orchestration.py`) is the existing
`IncidentAllocationRequest`: the existing `Incident` (including
`patient_present`, default `false`) plus `urgency` (0–1) and the categorical
`priority` (`LOW | MODERATE | HIGH | CRITICAL`).

`urgency` and `priority` are required because `ResourceAllocationService.allocate`
requires them and no upstream service produces them yet. The caller supplies
them explicitly, exactly as for `POST /resource/allocate`. The orchestrator
never defaults or derives them. `priority` here is the allocation **input**;
the mission's priority is Allocation's computed `final_priority_level`.

**Stage hand-offs:**

| Stage | Receives | Keeps in the result |
|---|---|---|
| Requirement | the request (it is an `Incident`) | `requirement` |
| Allocation | `requirement.requirements`, `severity`, `urgency`, `priority`; service built as `ResourceAllocationService(warehouses, rules)` like `/resource/allocate` | `allocation` |
| Demand Fulfilment | `allocation.required_resources` and `allocated_resources` (as dicts) | `demand_fulfilment`, `fulfilment_status` |
| Mission Creation | `MissionCreationRequest` per the MVP mapping below | `mission` |
| Agent Assignment | see "Agent Assignment inputs" | `agent_assignment` |
| Route Engine boundary | `RoutingInputs`: mission id, assigned responder id and location, pickups (id and location, in pickup order), destination | `route` |

**Result: `OrchestrationResult`** contains `orchestration_id`, `incident_id`,
`status`, `fulfilment_status`, `completed_stages` (stages that returned a
result, in order), each stage's output (`null` if the stage did not run) and
`error` (`stage`, `error_code`, `message`).

| `status` | Meaning | HTTP |
|---|---|---|
| `ROUTE_ENGINE_NOT_CONNECTED` | Responder assigned; the route boundary is not connected. The normal MVP outcome. | 200 |
| `COMPLETED` | Responder assigned and a route planned. Unreachable until the Route Engine is integrated. | 200 |
| `MISSION_NOT_DISPATCHABLE` | `NO_WAREHOUSE_PICKUP`; Agent Assignment not called. | 409 |
| `NO_RESPONDER_AVAILABLE` | Mission created; no eligible responder. | 409 |
| `FAILED` | A stage raised an error: `error.stage`, `error_code = "STAGE_FAILED"`, `message` = exception type and text. | 500 |

`fulfilment_status` (`FULLY_FULFILLED | PARTIALLY_FULFILLED`, from Demand
Fulfilment) is reported separately from `status`: a partially fulfilled
mission is still dispatched. The response body is always the full
`OrchestrationResult`, so the outputs of the stages that ran are kept. Invalid
input returns 422.

Stop behaviour: a failure at any stage stops the pipeline there and no later
stage runs. Stages before Agent Assignment have no side effects. The
orchestrator never changes responder status itself.

## Shared value sets

- **Priority:** `schemas/allocation.py::PriorityLevel` =
  `LOW | MODERATE | HIGH | CRITICAL`. Resource Allocation is the source of
  truth; `MissionCreationRequest.priority` and `MissionCreationResult.priority`
  reuse the same type. `MEDIUM` is not accepted.

## DECIDED: MVP mapping into `MissionCreationRequest`

| Field | MVP source | Status |
|---|---|---|
| `incident_id` | `Incident.incident_id` | |
| `destination` | `Incident.location` (the only location on `Incident`) | assumed, to be confirmed. Used by the orchestrator. |
| `risk_score` | `Incident.severity` | **DECIDED.** Both are bounded to [0, 1]. |
| `priority` | `AllocationResult.final_priority_level` | **DECIDED** |
| `patient_present` | `Incident.patient_present` | **DECIDED.** `Incident.patient_present` defaults to `false`. |
| `resources` (`dict[str, float]`) | `AllocationResult.allocated_resources`, as a dict | **DECIDED.** The **actually allocated** resources, not the required resources. |
| `warehouse_pickups` | `AllocationResult.warehouse_allocations`, same order. `supplies` = each allocation's `supplies`; `location` looked up by `warehouse_id` in the existing warehouse data (`warehouses.json` / `ResourceAllocationService.warehouses`) | established |

Mission Creation does not calculate resource quantities. It receives the
allocated resources through `resources` and returns them unchanged in
`MissionCreationResult.resources`.

Mission Creation does **not** receive separate `required_resources`,
`allocated_resources` or `fulfilment_status` fields. Those stay upstream:

- **Resource Allocation:** `AllocationResult.required_resources`,
  `allocated_resources`, `allocation_status` and `remaining_shortage`.
- **Demand Fulfilment:** `DemandFulfilmentResult.fulfilment_status`
  (`FULLY_FULFILLED | PARTIALLY_FULFILLED`) and `total_shortage`.

Consequences under the current code (verified by tests):

- The existing responder-type rule is unchanged. A patient present means
  `["AMBULANCE"]`; otherwise `["RESCUE_TRUCK"]` for every priority and
  resource total. Ambulances are requested only when
  `Incident.patient_present` is `true`.
- The resource-quantity part of that rule receives `resources`, i.e. the
  allocated resources.
- A partially fulfilled allocation still produces a mission, carrying the
  allocated amount in `resources` (for example, 4,000 water required and
  2,750 allocated gives `resources.water == 2750`). It is dispatched if it
  has at least one warehouse pickup.
- Mission Creation only passes `risk_score` through. It does not affect
  responder type.

## Data handoff from `MissionCreationResult`

| Needed by the orchestrator | Where it comes from |
|---|---|
| `mission_id` | `MissionCreationResult.mission_id` |
| `incident_id` | `MissionCreationResult.incident_id` |
| `destination` | `MissionCreationResult.destination` |
| `required_responder_types` | `MissionCreationResult.required_responder_types` |
| `priority` | `MissionCreationResult.priority` |
| risk | `MissionCreationResult.risk_score` |
| allocated resources | `MissionCreationResult.resources` |
| required resources, fulfilment status, shortage | **Not on `MissionCreationResult`.** Keep them from `AllocationResult` and `DemandFulfilmentResult` (see above). |
| warehouse pickup IDs | `MissionCreationResult.pickup_sequence[*].warehouse_id` (items with `type == "WAREHOUSE"`) |
| warehouse pickup supplies | `MissionCreationResult.pickup_sequence[*].supplies` |
| warehouse pickup **locations** | **Only** `MissionCreationRequest.warehouse_pickups[*].location`. `PickupSequenceItem` has no location, so the orchestrator must keep the request it built. |

Ordering invariant (verified): Mission Creation emits warehouse steps in the
same order as `warehouse_pickups`, so `pickup_sequence[0]` is
`warehouse_pickups[0]`.

Agent Assignment must not read `warehouses.json`; the orchestrator resolves
warehouse locations before calling it.

## Agent Assignment inputs

The orchestrator passes exactly:

```json
{
  "mission_id":               "<MissionCreationResult.mission_id>",
  "required_responder_types": "<MissionCreationResult.required_responder_types>",
  "first_warehouse_location": "<MissionCreationRequest.warehouse_pickups[0].location>",
  "first_warehouse_id":       "<MissionCreationRequest.warehouse_pickups[0].warehouse_id>"
}
```

- `required_responder_types` must be non-empty and contain only
  `RESCUE_TRUCK`, `AMBULANCE` or `FIRE_TRUCK`. The list means "any one of these
  types"; one responder is assigned.
- `first_warehouse_location` is required. Agent Assignment selects the
  closest AVAILABLE responder to it by straight-line distance, using each
  responder's latest known location, and never looks at the destination.
- Outcomes:
  - **Success:** the selected responder has already been persisted as `BUSY`,
    and the mission recorded as `ASSIGNED` to it in `missions.json` (see
    "Mission lifecycle"), when the assignment is returned.
  - **No eligible responder:** `NoResponderAvailableError`
    (`error_code = "NO_RESPONDER_AVAILABLE"`), HTTP 409. No status changes.
  - **Mission already closed:** `MissionStateError`
    (`error_code = "MISSION_ALREADY_CLOSED"`), HTTP 409. No status changes.
  - **Status could not be persisted:** `ResponderStatusError`, HTTP 500
    (`"Agent assignment failed: ..."`). No assignment is reported and
    `responders.json` is unchanged. If BUSY was saved but the mission record
    was not, the responder is returned to AVAILABLE.

## RULE: missions with zero warehouse pickups are not dispatchable

**Condition `NO_WAREHOUSE_PICKUP` → outcome `MISSION_NOT_DISPATCHABLE`.**

If `warehouse_pickups` is empty there is no pickup target, so Agent
Assignment cannot select a responder. The orchestrator must:

1. Detect it with `len(warehouse_pickups) == 0`, which is the same as
   `AllocationResult.warehouse_allocations == []`.
2. **Not call Agent Assignment.** (It cannot be called anyway:
   `first_warehouse_location` is a required field, so the request fails
   validation with 422.)
3. **Not** invent or guess a warehouse or location.
4. Report the mission as `MISSION_NOT_DISPATCHABLE` with reason
   `NO_WAREHOUSE_PICKUP`, keeping the allocation result (including its
   shortage) unchanged.

**Implemented by the orchestrator:** after Mission Creation it checks the
pickups and stops with `status = "MISSION_NOT_DISPATCHABLE"` and
`error = {stage: "AGENT_ASSIGNMENT", error_code: "NO_WAREHOUSE_PICKUP"}`.
`POST /orchestrate` returns 409 with the full result. The mission (which has
only the `DESTINATION` step) is included, and no responder status changes.

Detect this from the **empty pickup list, not from `allocation_status`**.
Existing allocation behaviour, which is unchanged, produces an empty list in
two ways:

| Case | `allocation_status` | `warehouse_allocations` |
|---|---|---|
| No stock for any required resource | `PARTIALLY_FULFILLED` | `[]` |
| All-zero demand | `FULLY_FULFILLED` | `[]` |

Mission Creation itself still accepts an empty `warehouse_pickups` list and
produces a pickup sequence containing only the `DESTINATION` step. The check
is an orchestration-level validation, made at the latest before Agent
Assignment.

## Responder state model

`database/responders.json` keeps its structure. `status` and `location` are
**independent fields**, matching the `Responder` schema
(`schemas/agent_assignment.py`). Status is never encoded through location.

```
AVAILABLE ──(assigned to a mission)──────────────▶ BUSY
BUSY ──(mission COMPLETED or CANCELLED only)──────▶ AVAILABLE
```

| Transition | State |
|---|---|
| `AVAILABLE → BUSY` | **IMPLEMENTED** in `AgentAssignmentService.assign`. Persisted before the assignment is returned. |
| `BUSY → AVAILABLE` | **IMPLEMENTED.** `MissionLifecycleService` calls `AgentAssignmentService.release_responder` when the responder's mission is completed or cancelled (`POST /mission/{mission_id}/complete` or `/cancel`). |

How a status change is applied (both transitions):

- Selection always reads the persisted file, so a BUSY responder is never
  selected again.
- The change is compare-and-set: the record is re-read and must still be in
  the expected state (`AVAILABLE` to assign, `BUSY` to release), otherwise
  `ResponderStatusError`.
- Only `status` is written. `location` and every other field are kept.
- The file is written to a temporary file and then atomically replaced, so a
  failed write never leaves a truncated `responders.json`.
- Values are preserved but the file is re-serialized: on the first real write,
  numbers such as `19.0800` are written as `19.08`.

**DECIDED: the orchestrator does not release responders.** Once Agent
Assignment has made a responder BUSY, the responder **stays BUSY** even if the
Route Engine boundary is not connected (`ROUTE_ENGINE_NOT_CONNECTED`), finds
no safe route (`NO_SAFE_ROUTE_FOUND`) or fails (`FAILED` at `ROUTE_ENGINE`).
The mission stays `ASSIGNED`; only completing or cancelling it releases the
responder.

## Mission lifecycle

```
CREATED ──(Agent Assignment)──▶ ASSIGNED ──(complete)──▶ COMPLETED
                                         └─(cancel)────▶ CANCELLED
```

- `CREATED` is what Mission Creation returns. Mission Creation has no side
  effects, so a mission is persisted only once a responder is assigned.
- `database/missions.json` (next to `responders.json`; `MissionStore`,
  `schemas/mission_lifecycle.py::MissionRecord`) stores each assigned
  mission's status and its assignments (`assignment_id`, `responder_id`).
  This is the mission ↔ responder link. `responders.json` is unchanged.
- `/agent/assign` called again for the same `ASSIGNED` mission assigns and
  records another responder (existing behaviour). The orchestrator assigns
  exactly one.
- `COMPLETED` and `CANCELLED` are final.

`POST /mission/{mission_id}/complete` and `POST /mission/{mission_id}/cancel`
(`MissionLifecycleService`):

| Mission state | Result |
|---|---|
| No record (never assigned) | 409 `MISSION_NOT_ASSIGNED`. No responder changes. |
| `ASSIGNED` | Releases the mission's own responders `BUSY → AVAILABLE` (location kept), then closes the mission. 200 with `released_responders`. |
| Already closed the same way | 200, `previous_status` equal to `status`, `released_responders = []`. Nothing changes (idempotent). |
| Closed the other way | 409 `MISSION_ALREADY_CLOSED`. Nothing changes. |

Which responders to release comes **only** from the mission's record, never
from which responders are BUSY. A recorded responder is skipped (left as is)
if it is no longer BUSY, or if another `ASSIGNED` mission also lists it, so
closing one mission never frees a responder serving another. Responders are
released before the mission is closed: if closing fails the mission stays
`ASSIGNED`, and retrying is safe for the same reason.

## DECIDED: responder location

- The `location` in `responders.json` is the responder's **latest known
  position**. Agent Assignment uses it as-is for distance.
- Assigning or releasing a responder never changes its location; it keeps its
  latest known coordinates.
- **No real-time GPS and no periodic (e.g. 5-minute) location updates yet.**
  The update mechanism will be added later.

## Route Engine

**No Route Engine API is to be invented.** The Route Engine contract must be
inspected from the **actual Route Engine repository** before any integration.
Mission Creation's route behaviour is unchanged (`RouteData` with status
`NOT_AVAILABLE`).

No Route Engine code exists in this repository or elsewhere on the
development machine.

**Implemented now: a boundary only.** `services/route_engine_client.py::RouteEngineClient.plan_route`
receives `RoutingInputs` (`schemas/orchestration.py`) and returns a
`RouteBoundaryResult` with `status = "ROUTE_ENGINE_NOT_CONNECTED"` and
`route = null`. It makes **no network call** and guesses no endpoint.
`RoutingInputs` is the orchestrator's internal hand-off (assigned responder
location, pickup locations in order, destination). It is **not** the Route
Engine's API.

**PENDING:** once the real Route Engine API has been inspected and tested
with real coordinates, replace only `RouteEngineClient`. It maps
`RoutingInputs` to the real request and the real response to
`RouteBoundaryResult(status="ROUTE_PLANNED", route=...)`, and the
orchestrator then reports `COMPLETED`. `RouteBoundaryResult` itself may need
adjusting at that point.

Order: the orchestrator runs the boundary after Agent Assignment, so the
assigned responder's location is available to it. Agent Assignment depends
on no Route Engine output, so this order works whether or not the real Route
Engine needs the responder location as its origin.

## Open items

- **Route Engine integration** (see "Route Engine").
- **Urgency and categorical priority have no upstream source.** The
  orchestrator requires the caller to supply them (`OrchestrationRequest`).
- **Concurrent assignment:** the compare-and-set narrows the window, but two
  simultaneous requests can still race between reading and writing the file.
  The same applies to `missions.json` and to completing/cancelling. There is
  no locking (deliberately, per earlier instructions).
- Confirm `destination = Incident.location`.
- Data paths are relative to the repository root, so the service must run
  from there.
