from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..schemas import ReorderRecommendationItem
from ..services.reorder import get_all_reorder_recommendations
from ..config import DEFAULT_SERVICE_LEVEL_Z, DEFAULT_AS_OF_DATE

router = APIRouter(prefix="/api/reorder", tags=["Smart Reorder Planner"])

@router.get("", response_model=List[ReorderRecommendationItem])
@router.get("/", response_model=List[ReorderRecommendationItem])
@router.get("/recommendations", response_model=List[ReorderRecommendationItem])
def get_recommendations(
    z_score: float = Query(DEFAULT_SERVICE_LEVEL_Z, description="Service level z-score (e.g. 1.65 for 95%)"),
    as_of_date: str = Query(DEFAULT_AS_OF_DATE, description="As-of analysis date"),
    db: Session = Depends(get_db)
):
    recommendations = get_all_reorder_recommendations(
        db,
        z_score=z_score,
        as_of_date=as_of_date
    )
    return recommendations
