from typing import Any

from pydantic import BaseModel, Field


class GenericAlertPayload(BaseModel):
    error_log: str
    target_file: str | None = None


class DatadogAlert(BaseModel):
    title: str | None = None
    message: str | None = None
    body: str | None = None
    alert_type: str | None = Field(None, alias="alertType")
    tags: list[str] = Field(default_factory=list)
    target_file: str | None = None
    error_log: str | None = None
    model_config = {"extra": "allow", "populate_by_name": True}

    def normalized(self) -> GenericAlertPayload:
        details = self.message or self.body or self.error_log or self.title or "Datadog alert"
        if self.tags:
            details = f"{details}\nTags: {', '.join(self.tags)}"
        return GenericAlertPayload(error_log=details, target_file=self.target_file)


class PrometheusAlert(BaseModel):
    alerts: list[dict[str, Any]]
    model_config = {"extra": "allow"}

    def normalized(self) -> GenericAlertPayload:
        firing = [alert for alert in self.alerts if alert.get("status") == "firing"]
        selected = firing or self.alerts
        lines = []
        target_file = None
        for alert in selected:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            lines.append(annotations.get("description") or annotations.get("summary") or labels.get("alertname", "Prometheus alert"))
            target_file = target_file or labels.get("target_file")
        return GenericAlertPayload(error_log="\n".join(lines), target_file=target_file)


def normalize_alert(payload: dict[str, Any]) -> GenericAlertPayload:
    if "alerts" in payload:
        return PrometheusAlert.model_validate(payload).normalized()
    if "error_log" in payload:
        return GenericAlertPayload.model_validate(payload)
    return DatadogAlert.model_validate(payload).normalized()