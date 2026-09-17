from fastapi import APIRouter
from app.api.v1.endpoints import jobs, patch, webhooks, approval, incident

api_router = APIRouter()
api_router.include_router(incident.router, prefix="", tags=["Incident Ingestion"])
api_router.include_router(patch.router, prefix="/patch", tags=["Patch Generation"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(approval.router, prefix="", tags=["Approval & Activity"])

