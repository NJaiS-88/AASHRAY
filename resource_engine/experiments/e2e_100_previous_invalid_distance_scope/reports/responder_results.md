# Responder results

| Responder ID | Vehicle Type | Initial Status | Number of Missions | Completed | Cancelled | Times Reused | Final Status |
|---|---|---|---|---|---|---|---|
| R001 | RESCUE_TRUCK | AVAILABLE | 38 | 3 | 35 | 37 | AVAILABLE |
| R002 | AMBULANCE | AVAILABLE | 62 | 12 | 50 | 61 | AVAILABLE |
| R003 | FIRE_TRUCK | AVAILABLE | 0 | 0 | 0 | 0 | AVAILABLE |
| R004 | RESCUE_TRUCK | AVAILABLE | 0 | 0 | 0 | 0 | AVAILABLE |
| R005 | AMBULANCE | BUSY | 0 | 0 | 0 | 0 | BUSY |

Final responder state equals the initial state: **YES** (responders.json byte-identical: True; no manual reset was performed, the runner never writes responders.json).

R003 (FIRE_TRUCK) is never selected: Mission Creation requests AMBULANCE when a patient is present and RESCUE_TRUCK otherwise. R005 is BUSY in the initial data with no mission record, so no lifecycle operation can release it, and none did. R004 was never needed because each mission was closed before the next scenario, so the closest rescue truck (R001) was always available.
