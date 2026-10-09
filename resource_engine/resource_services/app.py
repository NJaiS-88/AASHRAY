from fastapi import FastAPI

from resource_services.routes.resource_routes import router as resource_router
from resource_services.routes.demand_routes import router as demand_router
from resource_services.routes.mission_routes import router as mission_router
from resource_services.routes.agent_assignment_routes import (
    router as agent_assignment_router,
)
from resource_services.routes.orchestration_routes import (
    router as orchestration_router,
)


app = FastAPI(
    title="AASHRAY Resource Service",
    version="1.0.0",
    description="Resource requirement, allocation, demand fulfilment, and mission creation service.",
)


app.include_router(resource_router)
app.include_router(demand_router)
app.include_router(mission_router)
app.include_router(agent_assignment_router)
app.include_router(orchestration_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "resource_service",
    }