from fastapi import APIRouter

from app.api.v1 import (
    auth,
    bookings,
    customers,
    dashboard,
    documents,
    finance,
    inventory,
    leads,
    organization,
    partners,
    post_sales,
    property_lifecycle,
    quotations,
    rbac,
    site_visits,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(bookings.router)
api_router.include_router(dashboard.router)
api_router.include_router(rbac.router)
api_router.include_router(organization.router)
api_router.include_router(leads.router)
api_router.include_router(customers.router)
api_router.include_router(documents.router)
api_router.include_router(finance.router)
api_router.include_router(post_sales.router)
api_router.include_router(property_lifecycle.router)
api_router.include_router(partners.router)
api_router.include_router(inventory.router)
api_router.include_router(site_visits.router)
api_router.include_router(quotations.router)
