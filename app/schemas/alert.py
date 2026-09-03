from typing import List, Optional
from pydantic import BaseModel, Field

class AlertLabel(BaseModel):
    alertname: str
    severity: Optional[str] = "warning"
    service: Optional[str] = "unknown-service"
    instance: Optional[str] = None

class AlertAnnotation(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    stack_trace: Optional[str] = Field(default=None, alias="stackTrace")

class SingleAlert(BaseModel):
    status: str
    labels: AlertLabel
    annotations: AlertAnnotation
    startsAt: str
    endsAt: Optional[str] = None

class PrometheusWebhookPayload(BaseModel):
    version: str
    groupKey: str
    status: str
    receiver: str
    alerts: List[SingleAlert]
