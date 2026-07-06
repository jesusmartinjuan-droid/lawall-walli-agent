"""Backs the frontend dashboard screen. Not explicitly enumerated in the
original API list but required to render mailbox/document/prompt/draft
counters and recent errors without the frontend re-deriving them client-side."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return MonitoringService(db).get_dashboard_summary()
