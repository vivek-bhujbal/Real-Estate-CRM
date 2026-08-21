from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.db.session import SessionFactory
from app.models.entities import AuditLog, CustomerDocument


async def _register(
    client: AsyncClient, *, slug: str, email: str
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": f"Workspace {slug}",
            "organization_slug": slug,
            "admin_full_name": "Document Administrator",
            "admin_email": email,
            "password": "Secure-document-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _customer(client: AsyncClient, headers: dict[str, str], name: str) -> dict[str, object]:
    response = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": name, "email": f"{name.lower().replace(' ', '-')}@example.com"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _booking(
    client: AsyncClient, headers: dict[str, str], customer_id: str
) -> dict[str, object]:
    project = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Document Project", "code": "doc-project", "default_currency": "INR"},
    )
    assert project.status_code == 201, project.text
    unit = await client.post(
        f"/api/v1/projects/{project.json()['id']}/units",
        headers=headers,
        json={"unit_number": "DOC-101", "base_price": "7500000"},
    )
    assert unit.status_code == 201, unit.text
    booking = await client.post(
        f"/api/v1/inventory/units/{unit.json()['id']}/booking",
        headers=headers,
        json={
            "customer_id": customer_id,
            "booking_number": "DOC-BOOKING-1",
            "booking_amount": "500000",
            "currency": "INR",
        },
    )
    assert booking.status_code == 201, booking.text
    return booking.json()


async def test_secure_kyc_workflow_versioning_and_tenant_isolation(
    client: AsyncClient,
) -> None:
    headers, session = await _register(
        client, slug="document-workspace", email="document-admin@example.com"
    )
    customer = await _customer(client, headers, "KYC Customer")
    other_customer = await _customer(client, headers, "Other Customer")
    booking = await _booking(client, headers, str(customer["id"]))

    mismatch = await client.post(
        "/api/v1/documents/requests",
        headers=headers,
        json={
            "customer_id": other_customer["id"],
            "booking_id": booking["id"],
            "document_type": "PAN Card",
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "BOOKING_CUSTOMER_MISMATCH"

    requested = await client.post(
        "/api/v1/documents/requests",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "booking_id": booking["id"],
            "document_type": "PAN Card",
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["status"] == "PENDING"
    assert requested.json()["file_name"] is None
    assert "storage_key" not in requested.json()
    document_id = requested.json()["id"]

    invalid_file = await client.post(
        f"/api/v1/documents/{document_id}/upload",
        headers=headers,
        files={"file": ("pan.pdf", b"not a real pdf", "application/pdf")},
    )
    assert invalid_file.status_code == 415
    assert invalid_file.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    pdf_bytes = b"%PDF-1.7\nsecure kyc document\n%%EOF"
    uploaded = await client.post(
        f"/api/v1/documents/{document_id}/upload",
        headers=headers,
        files={"file": ("pan-card.pdf", pdf_bytes, "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "UPLOADED"
    assert uploaded.json()["content_type"] == "application/pdf"
    assert uploaded.json()["booking_number"] == "DOC-BOOKING-1"
    assert "storage_key" not in uploaded.json()

    started = await client.post(
        f"/api/v1/documents/{document_id}/review/start",
        headers=headers,
        json={"reviewer_user_id": session["user"]["id"], "notes": "Identity review started"},
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "UNDER_REVIEW"
    assert started.json()["reviewer_name"] == "Document Administrator"

    verified = await client.post(
        f"/api/v1/documents/{document_id}/review",
        headers=headers,
        json={"status": "VERIFIED", "notes": "PAN details match"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "VERIFIED"
    assert verified.json()["reviewed_at"] is not None

    download = await client.get(f"/api/v1/documents/{document_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == pdf_bytes
    assert download.headers["cache-control"].startswith("private, no-store")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in download.headers["content-disposition"]

    second_pdf = b"%PDF-1.7\ncorrected kyc document\n%%EOF"
    version = await client.post(
        f"/api/v1/documents/{document_id}/versions",
        headers=headers,
        files={"file": ("pan-card-corrected.pdf", second_pdf, "application/pdf")},
    )
    assert version.status_code == 201, version.text
    assert version.json()["version"] == 2
    assert version.json()["status"] == "UPLOADED"
    second_id = version.json()["id"]

    history = await client.get(f"/api/v1/documents/{second_id}/versions", headers=headers)
    assert history.status_code == 200
    assert [item["version"] for item in history.json()] == [2, 1]
    assert history.json()[0]["is_current"] is True
    assert history.json()[1]["is_current"] is False

    await client.post(f"/api/v1/documents/{second_id}/review/start", headers=headers, json={})
    rejected = await client.post(
        f"/api/v1/documents/{second_id}/review",
        headers=headers,
        json={"status": "REJECTED", "rejection_reason": "Image is incomplete"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["rejection_reason"] == "Image is incomplete"

    listed = await client.get(f"/api/v1/documents?customer_id={customer['id']}", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == second_id

    expiring = await client.post(
        "/api/v1/documents/requests",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "document_type": "Address proof",
            "expiry_date": (date.today() + timedelta(days=1)).isoformat(),
        },
    )
    assert expiring.status_code == 201
    async with SessionFactory() as db:
        await db.execute(
            update(CustomerDocument)
            .where(CustomerDocument.id == expiring.json()["id"])
            .values(expiry_date=date.today() - timedelta(days=1))
        )
        await db.commit()
    expired = await client.get(f"/api/v1/documents/{expiring.json()['id']}", headers=headers)
    assert expired.status_code == 200
    assert expired.json()["status"] == "EXPIRED"

    other_headers, _ = await _register(
        client, slug="document-other", email="document-other@example.com"
    )
    hidden = await client.get(f"/api/v1/documents/{second_id}/download", headers=other_headers)
    assert hidden.status_code == 404

    async with SessionFactory() as db:
        actions = set(
            await db.scalars(
                select(AuditLog.action).where(
                    AuditLog.entity_type == "document",
                    AuditLog.entity_id.in_([document_id, second_id]),
                )
            )
        )
    assert {
        "document.requested",
        "document.uploaded",
        "document.review_started",
        "document.verified",
        "document.downloaded",
        "document.version_uploaded",
        "document.rejected",
    }.issubset(actions)
