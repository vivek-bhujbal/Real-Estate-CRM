from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.entities import AuditLog, Booking, Commission, Customer, Project, Territory, Unit
from app.models.enums import BookingStatus, CommissionStatus


async def _register(client: AsyncClient) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Partner Workspace",
            "organization_slug": "partner-workspace",
            "admin_full_name": "Partner Administrator",
            "admin_email": "partner-admin@example.com",
            "password": "Secure-partner-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _approver(
    client: AsyncClient, admin_headers: dict[str, str]
) -> tuple[dict[str, str], str]:
    role = await client.post(
        "/api/v1/rbac/roles",
        headers=admin_headers,
        json={
            "name": "Partner Independent Approver",
            "permission_codes": [
                "partners.view",
                "partners.update",
                "partners.approve",
                "partners.assign",
                "commissions.view",
                "commissions.approve",
            ],
        },
    )
    assert role.status_code == 201, role.text
    password = "Secure-partner-approver-42!"
    user = await client.post(
        "/api/v1/organization/users",
        headers=admin_headers,
        json={
            "full_name": "Partner Compliance Approver",
            "email": "partner-approver@example.com",
            "password": password,
            "role_ids": [role.json()["id"]],
            "is_active": True,
        },
    )
    assert user.status_code == 201, user.text
    assigned = await client.put(
        f"/api/v1/rbac/users/{user.json()['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [role.json()["id"]]},
    )
    assert assigned.status_code == 200, assigned.text
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "partner-workspace",
            "email": "partner-approver@example.com",
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user.json()["id"]


async def test_partner_lifecycle_secure_documents_lead_protection_and_audit(
    client: AsyncClient,
) -> None:
    admin, session = await _register(client)
    approver, approver_id = await _approver(client, admin)
    org = session["user"]["organization"]["id"]
    async with SessionFactory() as db:
        project = Project(
            organization_id=org,
            name="Partner Project",
            code="PARTNER-PROJECT",
            default_currency="INR",
        )
        territory = Territory(
            organization_id=org,
            name="Partner Territory",
            code="PARTNER-TERRITORY",
            is_active=True,
        )
        db.add_all([project, territory])
        await db.commit()
        project_id, territory_id = project.id, territory.id

    created = await client.post(
        "/api/v1/partners",
        headers=admin,
        json={
            "code": "CP-001",
            "name": "Verified Channel Network",
            "legal_name": "Verified Channel Network Private Limited",
            "partner_type": "COMPANY",
            "registration_number": "REG-CP-001",
            "registration_date": str(date.today()),
            "contact_name": "Primary Partner Contact",
            "email": "contact@verified-channel.example",
            "phone": "+91 9876543210",
            "address_line1": "100 Partner Avenue",
            "city": "Pune",
            "state": "Maharashtra",
            "postal_code": "411001",
            "country": "India",
            "application_notes": "Submitted through verified onboarding channel",
        },
    )
    assert created.status_code == 201, created.text
    partner_id = created.json()["partner"]["id"]
    assert created.json()["partner"]["status"] == "APPLICATION"

    assignments = await client.put(
        f"/api/v1/partners/{partner_id}/assignments",
        headers=admin,
        json={"territory_ids": [territory_id], "project_ids": [project_id]},
    )
    assert assignments.status_code == 200, assignments.text
    compliance = await client.put(
        f"/api/v1/partners/{partner_id}/compliance",
        headers=admin,
        json={
            "tax_identifier": "PANCP001",
            "gst_number": "GSTCP001",
            "tax_registration_name": "Verified Channel Network Private Limited",
            "bank_account_holder": "Verified Channel Network Private Limited",
            "bank_name": "Partner Bank",
            "bank_branch": "Pune",
            "bank_ifsc": "BANK0001234",
            "bank_account_last4": "6789",
            "bank_account_reference": "vault://partner-bank-account-cp001",
            "lead_protection_days": 45,
        },
    )
    assert compliance.status_code == 200, compliance.text
    started = await client.post(
        f"/api/v1/partners/{partner_id}/lifecycle/document-verification",
        headers=admin,
        json={"notes": "Application profile accepted for compliance verification"},
    )
    assert started.status_code == 200, started.text
    requested_document = await client.post(
        f"/api/v1/partners/{partner_id}/documents",
        headers=admin,
        json={"document_type": "COMPANY_REGISTRATION"},
    )
    document_id = requested_document.json()["documents"][0]["id"]
    uploaded = await client.post(
        f"/api/v1/partners/{partner_id}/documents/{document_id}/upload",
        headers=admin,
        files={"file": ("registration.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    verified = await client.post(
        f"/api/v1/partners/{partner_id}/documents/{document_id}/decision",
        headers=approver,
        json={"status": "VERIFIED", "notes": "Registry evidence verified"},
    )
    assert verified.status_code == 200, verified.text
    documents_complete = await client.post(
        f"/api/v1/partners/{partner_id}/lifecycle/documents-complete",
        headers=approver,
        json={"notes": "All requested documents verified"},
    )
    assert documents_complete.json()["partner"]["status"] == "AGREEMENT_PENDING"
    agreement = await client.post(
        f"/api/v1/partners/{partner_id}/agreements",
        headers=admin,
        json={
            "agreement_number": "CPA-001",
            "effective_from": str(date.today()),
            "commission_percent": "2.5",
            "terms_summary": "Commission payable after booking confirmation and approval",
        },
    )
    assert agreement.status_code == 201, agreement.text
    agreement_id = agreement.json()["agreements"][0]["id"]
    signed = await client.post(
        f"/api/v1/partners/{partner_id}/agreements/{agreement_id}/signed-copy",
        headers=approver,
        files={"file": ("signed-agreement.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert signed.status_code == 200, signed.text
    structure = await client.post(
        f"/api/v1/partners/{partner_id}/commission-structures",
        headers=admin,
        json={
            "project_id": project_id,
            "name": "Project partner commission",
            "rate_percent": "2.5",
            "calculation_basis": "AGREED_VALUE",
            "effective_from": str(date.today()),
        },
    )
    assert structure.status_code == 201, structure.text
    approval_request = await client.post(
        f"/api/v1/partners/{partner_id}/lifecycle/submit-approval",
        headers=admin,
        json={"notes": "Agreement and commercial structure complete"},
    )
    assert approval_request.json()["partner"]["status"] == "APPROVAL_PENDING"
    self_approval = await client.post(
        f"/api/v1/partners/{partner_id}/lifecycle/approve",
        headers=admin,
        json={"notes": "Application creator self-approval attempt"},
    )
    assert self_approval.status_code == 403
    approved = await client.post(
        f"/api/v1/partners/{partner_id}/lifecycle/approve",
        headers=approver,
        json={"notes": "Independent onboarding approval complete"},
    )
    assert approved.json()["partner"]["status"] == "APPROVED"
    activated = await client.post(
        f"/api/v1/partners/{partner_id}/lifecycle/activate/final",
        headers=approver,
        json={"notes": "Partner activated after all gates passed"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["partner"]["status"] == "ACTIVE"

    lead = await client.post(
        f"/api/v1/partners/{partner_id}/leads",
        headers=admin,
        json={
            "full_name": "Protected Partner Lead",
            "email": "protected-lead@example.com",
            "phone": "+91 9000000001",
            "requirements": "Two-bedroom home",
            "registration_notes": "Registered from partner campaign",
        },
    )
    assert lead.status_code == 201, lead.text
    assert lead.json()["leads"][0]["status"] == "APPROVED"
    duplicate = await client.post(
        f"/api/v1/partners/{partner_id}/leads",
        headers=admin,
        json={
            "full_name": "Duplicate Protected Lead",
            "email": "protected-lead@example.com",
            "registration_notes": "Duplicate claim",
        },
    )
    assert duplicate.status_code == 409
    private_download = await client.get(
        f"/api/v1/partners/{partner_id}/documents/{document_id}/download",
        headers=admin,
    )
    assert private_download.status_code == 200
    assert private_download.content.startswith(b"%PDF-")
    unauthenticated = await client.get(
        f"/api/v1/partners/{partner_id}/documents/{document_id}/download"
    )
    assert unauthenticated.status_code == 401

    # Commercial records are always derived from real booking rows; payout totals are
    # recomputed and locked on the server rather than accepted from the browser.
    async with SessionFactory() as db:
        customer = Customer(
            organization_id=org,
            full_name="Protected Partner Customer",
            email="protected-customer@example.com",
        )
        unit = Unit(
            organization_id=org,
            project_id=project_id,
            unit_number="CP-UNIT-001",
            base_price=Decimal("100000.00"),
            currency="INR",
        )
        db.add_all([customer, unit])
        await db.flush()
        booking = Booking(
            organization_id=org,
            unit_id=unit.id,
            customer_id=customer.id,
            booked_by_user_id=session["user"]["id"],
            channel_partner_id=partner_id,
            booking_number="CP-BOOKING-001",
            status=BookingStatus.CONFIRMED,
            booking_amount=Decimal("10000.00"),
            agreed_price=Decimal("100000.00"),
            discount_amount=Decimal("0.00"),
            currency="INR",
            active_unit_key=unit.id,
        )
        db.add(booking)
        await db.flush()
        commission = Commission(
            organization_id=org,
            channel_partner_id=partner_id,
            booking_id=booking.id,
            status=CommissionStatus.APPROVED,
            rate_percent=Decimal("2.5000"),
            amount=Decimal("2500.00"),
            currency="INR",
        )
        db.add(commission)
        await db.commit()
        commission_id = commission.id

    payout = await client.post(
        f"/api/v1/partners/{partner_id}/payouts",
        headers=admin,
        json={
            "payout_number": "CP-PAYOUT-001",
            "commission_ids": [commission_id],
            "notes": "Approved booking commission",
        },
    )
    assert payout.status_code == 201, payout.text
    payout_row = payout.json()["payouts"][0]
    payout_id = payout_row["id"]
    assert payout_row["amount"] == "2500.00"
    self_payout_approval = await client.post(
        f"/api/v1/partners/{partner_id}/payouts/{payout_id}/decision",
        headers=admin,
        json={"status": "APPROVED", "notes": "Self approval attempt"},
    )
    assert self_payout_approval.status_code == 403
    payout_approval = await client.post(
        f"/api/v1/partners/{partner_id}/payouts/{payout_id}/decision",
        headers=approver,
        json={"status": "APPROVED", "notes": "Independent payout approval"},
    )
    assert payout_approval.status_code == 200, payout_approval.text
    paid = await client.post(
        f"/api/v1/partners/{partner_id}/payouts/{payout_id}/process",
        headers=approver,
        json={"reference_number": "BANK-TRANSFER-CP-001"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["payouts"][0]["status"] == "COMPLETED"
    assert paid.json()["commissions"][0]["status"] == "PAID"

    dispute = await client.post(
        f"/api/v1/partners/{partner_id}/disputes",
        headers=admin,
        json={
            "category": "PAYOUT_QUERY",
            "description": "Partner requested clarification of the bank reference",
            "commission_payout_id": payout_id,
        },
    )
    assert dispute.status_code == 201, dispute.text
    dispute_id = dispute.json()["disputes"][0]["id"]
    assigned = await client.post(
        f"/api/v1/partners/{partner_id}/disputes/{dispute_id}/assign",
        headers=admin,
        json={"assigned_to_user_id": approver_id},
    )
    assert assigned.status_code == 200, assigned.text
    resolved = await client.post(
        f"/api/v1/partners/{partner_id}/disputes/{dispute_id}/decision",
        headers=approver,
        json={
            "status": "COMPLETED",
            "resolution": "Bank transfer reference was verified and shared with the partner",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["disputes"][0]["status"] == "COMPLETED"

    async with SessionFactory() as db:
        actions = set(await db.scalars(select(AuditLog.action)))
    assert {
        "partner.application.created",
        "partner.compliance.updated",
        "partner.assignments.updated",
        "partner.document.uploaded",
        "partner.document.reviewed",
        "partner.agreement.signed",
        "partner.commission_structure.created",
        "partner.approval.decided",
        "partner.activated",
        "partner.lead.registered",
        "partner.payout.requested",
        "partner.payout.decided",
        "partner.payout.processed",
        "partner.dispute.created",
        "partner.dispute.assigned",
        "partner.dispute.resolved",
    }.issubset(actions)
    assert approver_id
