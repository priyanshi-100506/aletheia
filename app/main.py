from fastapi import FastAPI
from app.routers import webhooks

app = FastAPI(
    title="ALETHEIA Core Engine",
    description="Autonomous AIOps Incident Resolver & Self-Healing Engine",
    version="0.1.0",
)

app.include_router(webhooks.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "engine": "Aletheia v0.1.0"}
