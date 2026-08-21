from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.models.enums import LeadStatus
from app.schemas.leads import (
    AgeingBucket,
    AssigneeView,
    BulkAssignmentPayload,
    CompleteFollowUpPayload,
    DuplicateCheckPayload,
    DuplicateGroup,
    DuplicateMatch,
    DuplicateResolutionPayload,
    ImportBatchView,
    ImportPreview,
    ImportRequest,
    KanbanColumn,
    LeadActivityPayload,
    LeadActivityView,
    LeadAssignmentPayload,
    LeadConversionPayload,
    LeadConversionView,
    LeadCreate,
    LeadNotePayload,
    LeadNoteView,
    LeadSourcePayload,
    LeadSourceView,
    LeadStats,
    LeadUpdate,
    LeadView,
    LostLeadPayload,
    LostReasonPayload,
    LostReasonView,
    QualificationPayload,
    ScoreRulePayload,
    ScoreRuleView,
    StatusTransitionPayload,
    TimelineItem,
)
from app.schemas.organization import Page
from app.services import leads as lead_service
from app.services.organization import MutationContext

router = APIRouter(prefix="/leads", tags=["Lead management"])

LeadsReader = Annotated[SecurityContext, Depends(require_permissions("leads.view"))]
LeadsCreator = Annotated[SecurityContext, Depends(require_permissions("leads.create"))]
LeadsUpdater = Annotated[SecurityContext, Depends(require_permissions("leads.update"))]
LeadsDeleter = Annotated[SecurityContext, Depends(require_permissions("leads.delete"))]
LeadsAssigner = Annotated[SecurityContext, Depends(require_permissions("leads.assign"))]
LeadsApprover = Annotated[SecurityContext, Depends(require_permissions("leads.approve"))]
LeadsManager = Annotated[SecurityContext, Depends(require_permissions("leads.manage"))]
LeadImporter = Annotated[
    SecurityContext, Depends(require_permissions("leads.manage", "leads.create"))
]
LeadConverter = Annotated[
    SecurityContext, Depends(require_permissions("leads.approve", "customers.create"))
]
ActivitiesReader = Annotated[
    SecurityContext, Depends(require_permissions("leads.view", "activities.view"))
]
ActivitiesCreator = Annotated[
    SecurityContext, Depends(require_permissions("leads.view", "activities.create"))
]
ActivitiesUpdater = Annotated[
    SecurityContext, Depends(require_permissions("leads.view", "activities.update"))
]
ActivitiesDeleter = Annotated[
    SecurityContext, Depends(require_permissions("leads.view", "activities.delete"))
]

SearchQuery = Annotated[str | None, Query(max_length=100)]
PageQuery = Annotated[int, Query(ge=1, le=100_000)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
ScoreQuery = Annotated[int | None, Query(ge=0, le=100)]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/sources", response_model=list[LeadSourceView])
async def sources(db: DbSession, context: LeadsReader) -> list[LeadSourceView]:
    return await lead_service.list_sources(db, context.organization_id)


@router.post("/sources", response_model=LeadSourceView, status_code=201)
async def create_source(
    payload: LeadSourcePayload, request: Request, db: DbSession, context: LeadsManager
) -> LeadSourceView:
    return await lead_service.create_source(
        db, context.organization_id, payload, _context(request, context)
    )


@router.put("/sources/{source_id}", response_model=LeadSourceView)
async def update_source(
    source_id: str,
    payload: LeadSourcePayload,
    request: Request,
    db: DbSession,
    context: LeadsManager,
) -> LeadSourceView:
    return await lead_service.update_source(
        db, context.organization_id, source_id, payload, _context(request, context)
    )


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: str, request: Request, db: DbSession, context: LeadsManager
) -> None:
    await lead_service.delete_source(
        db, context.organization_id, source_id, _context(request, context)
    )


@router.get("/lost-reasons", response_model=list[LostReasonView])
async def lost_reasons(db: DbSession, context: LeadsReader) -> list[LostReasonView]:
    return await lead_service.list_lost_reasons(db, context.organization_id)


@router.post("/lost-reasons", response_model=LostReasonView, status_code=201)
async def create_lost_reason(
    payload: LostReasonPayload, request: Request, db: DbSession, context: LeadsManager
) -> LostReasonView:
    return await lead_service.create_lost_reason(
        db, context.organization_id, payload, _context(request, context)
    )


@router.put("/lost-reasons/{reason_id}", response_model=LostReasonView)
async def update_lost_reason(
    reason_id: str,
    payload: LostReasonPayload,
    request: Request,
    db: DbSession,
    context: LeadsManager,
) -> LostReasonView:
    return await lead_service.update_lost_reason(
        db, context.organization_id, reason_id, payload, _context(request, context)
    )


@router.delete("/lost-reasons/{reason_id}", status_code=204)
async def delete_lost_reason(
    reason_id: str, request: Request, db: DbSession, context: LeadsManager
) -> None:
    await lead_service.delete_lost_reason(
        db, context.organization_id, reason_id, _context(request, context)
    )


@router.get("/score-rules", response_model=list[ScoreRuleView])
async def score_rules(db: DbSession, context: LeadsReader) -> list[ScoreRuleView]:
    return await lead_service.list_score_rules(db, context.organization_id)


@router.post("/score-rules", response_model=ScoreRuleView, status_code=201)
async def create_score_rule(
    payload: ScoreRulePayload, request: Request, db: DbSession, context: LeadsManager
) -> ScoreRuleView:
    return await lead_service.create_score_rule(
        db, context.organization_id, payload, _context(request, context)
    )


@router.put("/score-rules/{rule_id}", response_model=ScoreRuleView)
async def update_score_rule(
    rule_id: str,
    payload: ScoreRulePayload,
    request: Request,
    db: DbSession,
    context: LeadsManager,
) -> ScoreRuleView:
    return await lead_service.update_score_rule(
        db, context.organization_id, rule_id, payload, _context(request, context)
    )


@router.delete("/score-rules/{rule_id}", status_code=204)
async def delete_score_rule(
    rule_id: str, request: Request, db: DbSession, context: LeadsManager
) -> None:
    await lead_service.delete_score_rule(
        db, context.organization_id, rule_id, _context(request, context)
    )


@router.post("/score-rules/recompute", response_model=dict[str, int])
async def recompute_scores(
    request: Request, db: DbSession, context: LeadsManager
) -> dict[str, int]:
    count = await lead_service.recompute_all_scores(
        db, context.organization_id, _context(request, context)
    )
    return {"updated": count}


@router.get("/assignees", response_model=list[AssigneeView])
async def assignees(db: DbSession, context: LeadsAssigner) -> list[AssigneeView]:
    return await lead_service.list_assignees(db, context.organization_id)


@router.get("/stats", response_model=LeadStats)
async def stats(db: DbSession, context: LeadsReader) -> LeadStats:
    return await lead_service.lead_stats(db, context.organization_id)


@router.post("/duplicate-check", response_model=list[DuplicateMatch])
async def duplicate_check(
    payload: DuplicateCheckPayload, db: DbSession, context: LeadsReader
) -> list[DuplicateMatch]:
    return await lead_service.check_duplicates(db, context.organization_id, payload)


@router.get("/duplicates", response_model=list[DuplicateGroup])
async def duplicates(db: DbSession, context: LeadsReader) -> list[DuplicateGroup]:
    return await lead_service.duplicate_groups(db, context.organization_id)


@router.post("/duplicates/resolve", status_code=204)
async def resolve_duplicates(
    payload: DuplicateResolutionPayload,
    request: Request,
    db: DbSession,
    context: LeadsApprover,
) -> None:
    await lead_service.resolve_duplicates(
        db, context.organization_id, payload, _context(request, context)
    )


@router.post("/imports/preview", response_model=ImportPreview)
async def preview_import(
    payload: ImportRequest, db: DbSession, context: LeadImporter
) -> ImportPreview:
    return await lead_service.preview_import(db, context.organization_id, payload)


@router.post("/imports", response_model=ImportBatchView, status_code=201)
async def commit_import(
    payload: ImportRequest, request: Request, db: DbSession, context: LeadImporter
) -> ImportBatchView:
    return await lead_service.commit_import(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/imports", response_model=list[ImportBatchView])
async def imports(db: DbSession, context: LeadImporter) -> list[ImportBatchView]:
    return await lead_service.list_imports(db, context.organization_id)


@router.get("/kanban", response_model=list[KanbanColumn])
async def kanban(db: DbSession, context: LeadsReader) -> list[KanbanColumn]:
    return await lead_service.kanban(db, context.organization_id)


@router.get("/ageing/buckets", response_model=list[AgeingBucket])
async def ageing_buckets(db: DbSession, context: LeadsReader) -> list[AgeingBucket]:
    return await lead_service.ageing_buckets(db, context.organization_id)


@router.get("/ageing", response_model=Page[LeadView])
async def ageing(
    db: DbSession,
    context: LeadsReader,
    q: SearchQuery = None,
    min_days: Annotated[int, Query(ge=0, le=3650)] = 0,
    max_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[LeadView]:
    if max_days is not None and max_days < min_days:
        max_days = min_days
    return await _list(
        db,
        context,
        q=q,
        minimum_age_days=min_days,
        maximum_age_days=max_days,
        page=page,
        page_size=page_size,
    )


@router.get("/unattended", response_model=Page[LeadView])
async def unattended(
    db: DbSession,
    context: LeadsReader,
    q: SearchQuery = None,
    days: Annotated[int, Query(ge=1, le=365)] = 2,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[LeadView]:
    return await _list(
        db,
        context,
        q=q,
        unattended_days=days,
        page=page,
        page_size=page_size,
    )


@router.get("/allocation", response_model=Page[LeadView])
async def allocation(
    db: DbSession,
    context: LeadsReader,
    q: SearchQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[LeadView]:
    return await _list(
        db,
        context,
        q=q,
        unassigned_only=True,
        page=page,
        page_size=page_size,
    )


@router.post("/bulk-assign", response_model=list[LeadView])
async def bulk_assign(
    payload: BulkAssignmentPayload,
    request: Request,
    db: DbSession,
    context: LeadsAssigner,
) -> list[LeadView]:
    return await lead_service.bulk_assign(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("", response_model=Page[LeadView])
async def leads(
    db: DbSession,
    context: LeadsReader,
    q: SearchQuery = None,
    status: LeadStatus | None = None,
    source_id: str | None = None,
    owner_user_id: str | None = None,
    branch_id: str | None = None,
    min_score: ScoreQuery = None,
    max_score: ScoreQuery = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    include_linked_duplicates: bool = False,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[LeadView]:
    return await _list(
        db,
        context,
        q=q,
        status=status,
        source_id=source_id,
        owner_user_id=owner_user_id,
        branch_id=branch_id,
        min_score=min_score,
        max_score=max_score,
        created_from=created_from,
        created_to=created_to,
        include_linked_duplicates=include_linked_duplicates,
        page=page,
        page_size=page_size,
    )


async def _list(
    db: DbSession,
    context: SecurityContext,
    *,
    q: str | None = None,
    status: LeadStatus | None = None,
    source_id: str | None = None,
    owner_user_id: str | None = None,
    branch_id: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    unattended_days: int | None = None,
    unassigned_only: bool = False,
    minimum_age_days: int | None = None,
    maximum_age_days: int | None = None,
    include_linked_duplicates: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> Page[LeadView]:
    return await lead_service.list_leads(
        db,
        context.organization_id,
        q=q,
        status=status,
        source_id=source_id,
        owner_user_id=owner_user_id,
        branch_id=branch_id,
        min_score=min_score,
        max_score=max_score,
        created_from=created_from,
        created_to=created_to,
        unattended_days=unattended_days,
        unassigned_only=unassigned_only,
        minimum_age_days=minimum_age_days,
        maximum_age_days=maximum_age_days,
        include_linked_duplicates=include_linked_duplicates,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=LeadView, status_code=201)
async def create_lead(
    payload: LeadCreate, request: Request, db: DbSession, context: LeadsCreator
) -> LeadView:
    return await lead_service.create_lead(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/{lead_id}", response_model=LeadView)
async def lead(lead_id: str, db: DbSession, context: LeadsReader) -> LeadView:
    return await lead_service.get_lead(db, context.organization_id, lead_id)


@router.patch("/{lead_id}", response_model=LeadView)
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    request: Request,
    db: DbSession,
    context: LeadsUpdater,
) -> LeadView:
    return await lead_service.update_lead(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: str, request: Request, db: DbSession, context: LeadsDeleter) -> None:
    await lead_service.delete_lead(db, context.organization_id, lead_id, _context(request, context))


@router.post("/{lead_id}/assignment", response_model=LeadView)
async def assign_lead(
    lead_id: str,
    payload: LeadAssignmentPayload,
    request: Request,
    db: DbSession,
    context: LeadsAssigner,
) -> LeadView:
    return await lead_service.assign_lead(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.post("/{lead_id}/status", response_model=LeadView)
async def transition_status(
    lead_id: str,
    payload: StatusTransitionPayload,
    request: Request,
    db: DbSession,
    context: LeadsUpdater,
) -> LeadView:
    return await lead_service.transition_status(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.post("/{lead_id}/qualify", response_model=LeadView)
async def qualify_lead(
    lead_id: str,
    payload: QualificationPayload,
    request: Request,
    db: DbSession,
    context: LeadsUpdater,
) -> LeadView:
    return await lead_service.qualify_lead(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.post("/{lead_id}/lost", response_model=LeadView)
async def mark_lost(
    lead_id: str,
    payload: LostLeadPayload,
    request: Request,
    db: DbSession,
    context: LeadsUpdater,
) -> LeadView:
    return await lead_service.mark_lead_lost(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.post("/{lead_id}/convert", response_model=LeadConversionView, status_code=201)
async def convert_lead(
    lead_id: str,
    payload: LeadConversionPayload,
    request: Request,
    db: DbSession,
    context: LeadConverter,
) -> LeadConversionView:
    return await lead_service.convert_lead(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.get("/{lead_id}/activities", response_model=list[LeadActivityView])
async def activities(
    lead_id: str, db: DbSession, context: ActivitiesReader
) -> list[LeadActivityView]:
    return await lead_service.list_activities(db, context.organization_id, lead_id)


@router.post("/{lead_id}/activities", response_model=LeadActivityView, status_code=201)
async def create_activity(
    lead_id: str,
    payload: LeadActivityPayload,
    request: Request,
    db: DbSession,
    context: ActivitiesCreator,
) -> LeadActivityView:
    return await lead_service.create_activity(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.put("/{lead_id}/activities/{activity_id}", response_model=LeadActivityView)
async def update_activity(
    lead_id: str,
    activity_id: str,
    payload: LeadActivityPayload,
    request: Request,
    db: DbSession,
    context: ActivitiesUpdater,
) -> LeadActivityView:
    return await lead_service.update_activity(
        db,
        context.organization_id,
        lead_id,
        activity_id,
        payload,
        _context(request, context),
    )


@router.post("/{lead_id}/activities/{activity_id}/complete", response_model=LeadActivityView)
async def complete_follow_up(
    lead_id: str,
    activity_id: str,
    payload: CompleteFollowUpPayload,
    request: Request,
    db: DbSession,
    context: ActivitiesUpdater,
) -> LeadActivityView:
    return await lead_service.complete_follow_up(
        db,
        context.organization_id,
        lead_id,
        activity_id,
        payload,
        _context(request, context),
    )


@router.delete("/{lead_id}/activities/{activity_id}", status_code=204)
async def delete_activity(
    lead_id: str,
    activity_id: str,
    request: Request,
    db: DbSession,
    context: ActivitiesDeleter,
) -> None:
    await lead_service.delete_activity(
        db,
        context.organization_id,
        lead_id,
        activity_id,
        _context(request, context),
    )


@router.get("/{lead_id}/notes", response_model=list[LeadNoteView])
async def notes(lead_id: str, db: DbSession, context: ActivitiesReader) -> list[LeadNoteView]:
    return await lead_service.list_notes(db, context.organization_id, lead_id)


@router.post("/{lead_id}/notes", response_model=LeadNoteView, status_code=201)
async def create_note(
    lead_id: str,
    payload: LeadNotePayload,
    request: Request,
    db: DbSession,
    context: ActivitiesCreator,
) -> LeadNoteView:
    return await lead_service.create_note(
        db, context.organization_id, lead_id, payload, _context(request, context)
    )


@router.put("/{lead_id}/notes/{note_id}", response_model=LeadNoteView)
async def update_note(
    lead_id: str,
    note_id: str,
    payload: LeadNotePayload,
    request: Request,
    db: DbSession,
    context: ActivitiesUpdater,
) -> LeadNoteView:
    return await lead_service.update_note(
        db,
        context.organization_id,
        lead_id,
        note_id,
        payload,
        _context(request, context),
    )


@router.delete("/{lead_id}/notes/{note_id}", status_code=204)
async def delete_note(
    lead_id: str,
    note_id: str,
    request: Request,
    db: DbSession,
    context: ActivitiesDeleter,
) -> None:
    await lead_service.delete_note(
        db,
        context.organization_id,
        lead_id,
        note_id,
        _context(request, context),
    )


@router.get("/{lead_id}/timeline", response_model=list[TimelineItem])
async def timeline(lead_id: str, db: DbSession, context: LeadsReader) -> list[TimelineItem]:
    return await lead_service.timeline(db, context.organization_id, lead_id)
