import os
import sys
import json
from pathlib import Path

if os.getenv("ENVIRONMENT") == "production" or os.getenv("NODE_ENV") == "production":
    print("CRITICAL: Test data reset is strictly prohibited in production mode.", file=sys.stderr)
    sys.exit(1)

root_dir = Path(__file__).resolve().parent.parent

# 1. Reset live_orchestrations.json
live_path = root_dir / "resource_engine" / "resource_services" / "database" / "live_orchestrations.json"
live_path.parent.mkdir(parents=True, exist_ok=True)
live_path.write_text("[]", encoding="utf-8")
print(f"[OK] Cleared {live_path.name} -> exactly 5 default scenarios active.")

# 2. Reset responders.json
resp_path = root_dir / "resource_engine" / "resource_services" / "database" / "responders.json"
if resp_path.exists():
    responders = json.loads(resp_path.read_text(encoding="utf-8"))
    for r in responders:
        r["status"] = "AVAILABLE"
    resp_path.write_text(json.dumps(responders, indent=2), encoding="utf-8")
    print(f"[OK] Reset {len(responders)} fleet responders to AVAILABLE.")

print("Safe test lifecycle reset complete.")
