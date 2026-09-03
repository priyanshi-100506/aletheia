import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from app.schemas.alert import PrometheusWebhookPayload

logger = logging.getLogger("aletheia")
router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

def process_firing_alert(alert_payload: PrometheusWebhookPayload):
    for alert in alert_payload.alerts:
        if alert.status == "firing":
            logger.info(
                f"[ALETHEIA TRIGGERED] Incident: {alert.labels.alertname} | "
                f"Service: {alert.labels.service}"
            )

@router.post("/prometheus", status_code=status.HTTP_202_ACCEPTED)
async def handle_prometheus_alert(
    payload: PrometheusWebhookPayload, 
    background_tasks: BackgroundTasks
):
    if not payload.alerts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="No alerts in payload"
        )

    background_tasks.add_task(process_firing_alert, payload)

    return {
        "status": "acknowledged",
        "alerts_received": len(payload.alerts),
    }
