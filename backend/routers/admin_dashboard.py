"""Admin dashboard: overview stats + collection-rate breakdown."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_db
from backend.db.models.admin_user import AdminUser
from backend.schemas.dashboard import CollectionsByPeriodResponse, DashboardOverviewResponse
from backend.services import dashboard_service

router = APIRouter(prefix="/api/v1/admin/dashboard", tags=["admin-dashboard"], dependencies=[Depends(get_current_admin)])


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_overview(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
) -> DashboardOverviewResponse:
    return DashboardOverviewResponse(**dashboard_service.get_overview(db, admin.community_id))


@router.get("/collections", response_model=list[CollectionsByPeriodResponse])
def get_collections(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
) -> list[CollectionsByPeriodResponse]:
    return [CollectionsByPeriodResponse(**r) for r in dashboard_service.get_collections_by_period(db, admin.community_id)]
