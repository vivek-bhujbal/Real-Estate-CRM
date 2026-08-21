from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.models.enums import CustomerStatus
from app.schemas.customers import (
    Customer360View,
    CustomerActivityPayload,
    CustomerActivityView,
    CustomerCreate,
    CustomerStats,
    CustomerUpdate,
    CustomerView,
)
from app.schemas.leads import AssigneeView
from app.schemas.organization import Page
from app.services import customers as customer_service
from app.services.organization import MutationContext

router = APIRouter(prefix="/customers", tags=["customer-360"])

CustomerReader = Annotated[SecurityContext, Depends(require_permissions("customers.view"))]
CustomerCreator = Annotated[SecurityContext, Depends(require_permissions("customers.create"))]
CustomerUpdater = Annotated[SecurityContext, Depends(require_permissions("customers.update"))]
CustomerDeleter = Annotated[SecurityContext, Depends(require_permissions("customers.delete"))]
CustomerAssigner = Annotated[SecurityContext, Depends(require_permissions("customers.assign"))]
ActivityCreator = Annotated[
    SecurityContext, Depends(require_permissions("customers.view", "activities.create"))
]
ActivityUpdater = Annotated[
    SecurityContext, Depends(require_permissions("customers.view", "activities.update"))
]
ActivityDeleter = Annotated[
    SecurityContext, Depends(require_permissions("customers.view", "activities.delete"))
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/stats", response_model=CustomerStats)
async def stats(db: DbSession, context: CustomerReader) -> CustomerStats:
    return await customer_service.customer_stats(db, context.organization_id)


@router.get("/assignees", response_model=list[AssigneeView])
async def assignees(db: DbSession, context: CustomerAssigner) -> list[AssigneeView]:
    return await customer_service.list_assignees(db, context.organization_id)


@router.get("", response_model=Page[CustomerView])
async def customers(
    db: DbSession,
    context: CustomerReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: CustomerStatus | None = None,
    owner_user_id: str | None = None,
    branch_id: str | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CustomerView]:
    return await customer_service.list_customers(
        db,
        context.organization_id,
        q=q,
        status=status,
        owner_user_id=owner_user_id,
        branch_id=branch_id,
        page=page,
        page_size=page_size,
        permissions=context.permissions,
    )


@router.post("", response_model=CustomerView, status_code=201)
async def create_customer(
    payload: CustomerCreate,
    request: Request,
    db: DbSession,
    context: CustomerCreator,
) -> CustomerView:
    return await customer_service.create_customer(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/{customer_id}", response_model=CustomerView)
async def customer(customer_id: str, db: DbSession, context: CustomerReader) -> CustomerView:
    return await customer_service.get_customer(
        db, context.organization_id, customer_id, context.permissions
    )


@router.patch("/{customer_id}", response_model=CustomerView)
async def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    request: Request,
    db: DbSession,
    context: CustomerUpdater,
) -> CustomerView:
    return await customer_service.update_customer(
        db, context.organization_id, customer_id, payload, _context(request, context)
    )


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: str,
    request: Request,
    db: DbSession,
    context: CustomerDeleter,
) -> None:
    await customer_service.delete_customer(
        db, context.organization_id, customer_id, _context(request, context)
    )


@router.get("/{customer_id}/360", response_model=Customer360View)
async def customer_360(customer_id: str, db: DbSession, context: CustomerReader) -> Customer360View:
    return await customer_service.customer_360(
        db, context.organization_id, customer_id, context.permissions
    )


@router.get("/{customer_id}/activities", response_model=list[CustomerActivityView])
async def activities(
    customer_id: str,
    db: DbSession,
    context: Annotated[
        SecurityContext, Depends(require_permissions("customers.view", "activities.view"))
    ],
) -> list[CustomerActivityView]:
    return await customer_service.list_activities(db, context.organization_id, customer_id)


@router.post("/{customer_id}/activities", response_model=CustomerActivityView, status_code=201)
async def create_activity(
    customer_id: str,
    payload: CustomerActivityPayload,
    request: Request,
    db: DbSession,
    context: ActivityCreator,
) -> CustomerActivityView:
    return await customer_service.create_activity(
        db,
        context.organization_id,
        customer_id,
        payload,
        _context(request, context),
    )


@router.put("/{customer_id}/activities/{activity_id}", response_model=CustomerActivityView)
async def update_activity(
    customer_id: str,
    activity_id: str,
    payload: CustomerActivityPayload,
    request: Request,
    db: DbSession,
    context: ActivityUpdater,
) -> CustomerActivityView:
    return await customer_service.update_activity(
        db,
        context.organization_id,
        customer_id,
        activity_id,
        payload,
        _context(request, context),
    )


@router.delete("/{customer_id}/activities/{activity_id}", status_code=204)
async def delete_activity(
    customer_id: str,
    activity_id: str,
    request: Request,
    db: DbSession,
    context: ActivityDeleter,
) -> None:
    await customer_service.delete_activity(
        db,
        context.organization_id,
        customer_id,
        activity_id,
        _context(request, context),
    )
