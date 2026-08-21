from datetime import date, timedelta

from httpx import AsyncClient


async def _setup_users(client: AsyncClient) -> tuple[dict[str, str], dict[str, str], str, str]:
    registered = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Quotation Workspace",
            "organization_slug": "quotation-workspace",
            "admin_full_name": "Quotation Administrator",
            "admin_email": "quotation-admin@example.com",
            "password": "Secure-quotation-admin-42!",
        },
    )
    assert registered.status_code == 201, registered.text
    admin = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    salesperson = await client.post(
        "/api/v1/organization/users",
        headers=admin,
        json={
            "full_name": "Pricing Salesperson",
            "email": "pricing-sales@example.com",
            "password": "Secure-pricing-sales-42!",
            "is_active": True,
        },
    )
    approver = await client.post(
        "/api/v1/organization/users",
        headers=admin,
        json={
            "full_name": "Discount Approver",
            "email": "discount-approver@example.com",
            "password": "Secure-discount-approver-42!",
            "is_active": True,
        },
    )
    assert salesperson.status_code == approver.status_code == 201
    sales_role = await client.post(
        "/api/v1/rbac/roles",
        headers=admin,
        json={
            "name": "Quotation Sales Test",
            "permission_codes": [
                "quotations.view",
                "quotations.create",
                "quotations.update",
                "quotations.approve",
                "quotations.export",
                "customers.view",
                "projects.view",
                "inventory.view",
            ],
        },
    )
    approver_role = await client.post(
        "/api/v1/rbac/roles",
        headers=admin,
        json={
            "name": "Discount Approver Test",
            "permission_codes": ["quotations.view", "quotations.approve"],
        },
    )
    assert sales_role.status_code == approver_role.status_code == 201
    for user_id, role_id in (
        (salesperson.json()["id"], sales_role.json()["id"]),
        (approver.json()["id"], approver_role.json()["id"]),
    ):
        assigned = await client.put(
            f"/api/v1/rbac/users/{user_id}/roles",
            headers=admin,
            json={"role_ids": [role_id]},
        )
        assert assigned.status_code == 200, assigned.text

    async def login(email: str, password: str) -> dict[str, str]:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "organization_slug": "quotation-workspace",
                "email": email,
                "password": password,
            },
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return (
        admin,
        await login("pricing-sales@example.com", "Secure-pricing-sales-42!"),
        approver.json()["id"],
        (await login("discount-approver@example.com", "Secure-discount-approver-42!"))[
            "Authorization"
        ],
    )


async def _commercial_records(
    client: AsyncClient, admin: dict[str, str], approver_id: str
) -> tuple[str, str, str]:
    project = await client.post(
        "/api/v1/projects",
        headers=admin,
        json={"name": "Commercial Project", "code": "commercial", "default_currency": "INR"},
    )
    tower = await client.post(
        f"/api/v1/projects/{project.json()['id']}/towers",
        headers=admin,
        json={"name": "Tower One", "code": "T1"},
    )
    floor = await client.post(
        f"/api/v1/projects/{project.json()['id']}/floors",
        headers=admin,
        json={"tower_id": tower.json()["id"], "name": "Fifth floor", "floor_number": 5},
    )
    unit = await client.post(
        f"/api/v1/projects/{project.json()['id']}/units",
        headers=admin,
        json={
            "tower_id": tower.json()["id"],
            "floor_id": floor.json()["id"],
            "unit_number": "T1-501",
            "unit_type": "3 BHK",
            "area_sqft": "1400",
            "facing": "East",
            "base_price": "10000000",
        },
    )
    customer = await client.post(
        "/api/v1/customers",
        headers=admin,
        json={"full_name": "Quotation Buyer", "email": "quotation-buyer@example.com"},
    )
    price_list = await client.post(
        "/api/v1/price-lists",
        headers=admin,
        json={
            "project_id": project.json()["id"],
            "name": "Launch Price List",
            "code": "LAUNCH_01",
            "currency": "INR",
            "effective_from": str(date.today()),
            "pricing_rules": {
                "floor_rise": {
                    "label": "Floor rise",
                    "start_floor": 2,
                    "amount_per_floor": "100000",
                    "taxable": True,
                },
                "premiums": [
                    {
                        "code": "EAST",
                        "label": "East-facing premium",
                        "calculation": "percentage",
                        "value": "2",
                        "taxable": True,
                        "optional": False,
                        "match_field": "facing",
                        "match_value": "East",
                    }
                ],
                "parking_options": [
                    {
                        "code": "COVERED",
                        "label": "Covered parking",
                        "calculation": "fixed",
                        "value": "500000",
                        "taxable": True,
                    }
                ],
                "amenity_charges": [
                    {
                        "code": "CLUB",
                        "label": "Club membership",
                        "calculation": "fixed",
                        "value": "200000",
                        "taxable": True,
                    }
                ],
                "charges": [
                    {
                        "code": "LEGAL",
                        "label": "Legal charge",
                        "calculation": "fixed",
                        "value": "100000",
                        "taxable": True,
                    }
                ],
                "taxes": [{"code": "GST", "label": "GST", "rate_percent": "5", "applies_to": []}],
                "discount_policy": {
                    "self_approval_limit_percent": "2",
                    "maximum_discount_percent": "10",
                    "approval_matrix": [
                        {
                            "name": "Director approval",
                            "minimum_discount_percent": "2.0001",
                            "maximum_discount_percent": "10",
                            "approver_user_ids": [approver_id],
                            "approver_role_ids": [],
                        }
                    ],
                },
                "booking_amount": {"calculation": "percentage", "value": "10"},
            },
        },
    )
    assert price_list.status_code == 201, price_list.text
    activated = await client.post(
        f"/api/v1/price-lists/{price_list.json()['id']}/status",
        headers=admin,
        json={"status": "ACTIVE"},
    )
    assert activated.status_code == 200, activated.text
    return customer.json()["id"], unit.json()["id"], price_list.json()["id"]


async def test_discount_matrix_quotation_versions_and_pdf(client: AsyncClient) -> None:
    admin, salesperson, approver_id, approver_token = await _setup_users(client)
    approver = {"Authorization": approver_token}
    customer_id, unit_id, price_list_id = await _commercial_records(client, admin, approver_id)
    request = {
        "customer_id": customer_id,
        "unit_id": unit_id,
        "price_list_id": price_list_id,
        "parking": [{"code": "COVERED", "quantity": 1}],
        "amenity_codes": ["CLUB"],
        "requested_discount_amount": "600000",
        "request_notes": "Competitive offer received from another project",
    }
    preview = await client.post("/api/v1/cost-sheets/preview", headers=salesperson, json=request)
    assert preview.status_code == 200, preview.text
    assert preview.json()["gross_value"] == "11408000.00"
    assert preview.json()["status"] == "PENDING_APPROVAL"
    created = await client.post("/api/v1/cost-sheets", headers=salesperson, json=request)
    assert created.status_code == 201, created.text
    approval = created.json()["approval"]
    assert approval["approval_level_name"] == "Director approval"
    assert approval["previous_value"] == "11978400.00"
    assert approval["final_approved_value"] is None
    assert approval["request_notes"] == request["request_notes"]

    self_approval = await client.post(
        f"/api/v1/cost-sheets/{created.json()['id']}/approval",
        headers=salesperson,
        json={"status": "APPROVED", "notes": "Attempted bypass"},
    )
    assert self_approval.status_code == 403
    assert self_approval.json()["error"]["code"] == "SELF_APPROVAL_NOT_ALLOWED"

    approved = await client.post(
        f"/api/v1/cost-sheets/{created.json()['id']}/approval",
        headers=approver,
        json={"status": "APPROVED", "notes": "Commercial rationale verified"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval"]["approver_user_id"] == approver_id
    assert approved.json()["approval"]["final_approved_value"] == "11378400.00"
    assert approved.json()["approval"]["decided_at"] is not None

    quotation = await client.post(
        "/api/v1/quotations",
        headers=salesperson,
        json={
            "cost_sheet_id": created.json()["id"],
            "valid_until": str(date.today() + timedelta(days=15)),
        },
    )
    assert quotation.status_code == 201, quotation.text
    assert quotation.json()["version"] == 1
    pdf = await client.get(f"/api/v1/quotations/{quotation.json()['id']}/pdf", headers=salesperson)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-1.4")

    revision_sheet = await client.post(
        "/api/v1/cost-sheets",
        headers=salesperson,
        json={**request, "requested_discount_amount": "500000", "request_notes": "Revised terms"},
    )
    assert revision_sheet.status_code == 201, revision_sheet.text
    revision_approval = await client.post(
        f"/api/v1/cost-sheets/{revision_sheet.json()['id']}/approval",
        headers=approver,
        json={"status": "APPROVED", "notes": "Revision verified"},
    )
    assert revision_approval.status_code == 200, revision_approval.text
    version = await client.post(
        f"/api/v1/quotations/{quotation.json()['id']}/versions",
        headers=salesperson,
        json={
            "cost_sheet_id": revision_sheet.json()["id"],
            "valid_until": str(date.today() + timedelta(days=20)),
        },
    )
    assert version.status_code == 201, version.text
    assert version.json()["version"] == 2
    assert len(version.json()["history"]) == 2
    old_version = await client.get(
        f"/api/v1/quotations/{quotation.json()['id']}", headers=salesperson
    )
    assert old_version.json()["status"] == "SUPERSEDED"

    audits = await client.get(
        "/api/v1/organization/audit-logs?entity_type=discount_approval&page_size=100",
        headers=admin,
    )
    assert audits.status_code == 200
    actions = {item["action"] for item in audits.json()["items"]}
    assert {"discount_approval.requested", "discount_approval.decided"} <= actions


async def test_approval_reason_and_matrix_are_mandatory(client: AsyncClient) -> None:
    admin, salesperson, approver_id, _ = await _setup_users(client)
    customer_id, unit_id, price_list_id = await _commercial_records(client, admin, approver_id)
    missing_reason = await client.post(
        "/api/v1/cost-sheets",
        headers=salesperson,
        json={
            "customer_id": customer_id,
            "unit_id": unit_id,
            "price_list_id": price_list_id,
            "requested_discount_amount": "600000",
        },
    )
    assert missing_reason.status_code == 400
    assert missing_reason.json()["error"]["code"] == "DISCOUNT_REASON_REQUIRED"

    unit_response = await client.get(f"/api/v1/inventory/units/{unit_id}", headers=admin)
    invalid_matrix = await client.post(
        "/api/v1/price-lists",
        headers=admin,
        json={
            "project_id": unit_response.json()["project_id"],
            "name": "Invalid approver list",
            "code": "INVALID_APPROVER",
            "currency": "INR",
            "effective_from": str(date.today()),
            "pricing_rules": {
                "discount_policy": {
                    "self_approval_limit_percent": "0",
                    "approval_matrix": [
                        {
                            "name": "Unknown approver",
                            "minimum_discount_percent": "0.0001",
                            "approver_user_ids": ["not-a-real-user"],
                        }
                    ],
                }
            },
        },
    )
    assert invalid_matrix.status_code == 400
    assert invalid_matrix.json()["error"]["code"] == "INVALID_APPROVAL_MATRIX"
