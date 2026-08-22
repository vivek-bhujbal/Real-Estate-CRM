from dataclasses import dataclass
from itertools import count

from httpx import AsyncClient

_sequence = count(1)


@dataclass(frozen=True, slots=True)
class AuthenticatedOrganization:
    headers: dict[str, str]
    body: dict[str, object]
    slug: str
    email: str
    password: str


async def organization_factory(
    client: AsyncClient,
    *,
    permissions_label: str = "workflow",
) -> AuthenticatedOrganization:
    """Create an isolated organization only inside the current database fixture."""
    number = next(_sequence)
    slug = f"test-{permissions_label}-{number}"
    email = f"admin-{permissions_label}-{number}@example.com"
    password = "Isolated-test-password-42!"
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": f"Isolated Test Organization {number}",
            "organization_slug": slug,
            "admin_full_name": "Isolated Test Administrator",
            "admin_email": email,
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return AuthenticatedOrganization(
        headers={"Authorization": f"Bearer {body['access_token']}"},
        body=body,
        slug=slug,
        email=email,
        password=password,
    )
