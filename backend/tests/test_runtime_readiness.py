from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import app


async def test_application_lifespan_health_and_api_documentation() -> None:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://readiness.test") as client:
            live = await client.get("/health/live")
            metrics = await client.get("/metrics")
            docs = await client.get("/docs")
            schema = await client.get("/openapi.json")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert metrics.status_code == 200
    assert "estateops_http_requests_total" in metrics.text
    assert docs.status_code == 200
    assert schema.status_code == 200
    assert len(schema.json()["paths"]) >= 100


def test_api_documentation_is_disabled_in_production() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key="unique-production-readiness-secret-key-42!",
        password_reset_delivery="smtp",
        public_web_url="https://crm.example.com",
        smtp_host="smtp.example.com",
        smtp_from_email="no-reply@example.com",
        cors_origins=["https://crm.example.com"],
        malware_scan_mode="clamav",
        clamav_host="scanner.internal",
        metrics_bearer_token="production-metrics-token-with-32-characters",
        storage_backend="s3",
        s3_bucket="estateops-private-documents",
        s3_region="ap-south-1",
    )
    assert settings.docs_enabled is False
