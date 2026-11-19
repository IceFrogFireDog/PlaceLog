from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import optional_user
from app.models import User
from app.schemas.map import MapResponse
from app.services import map_service

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/places", response_model=MapResponse)
def places(mode: Literal["WORLD", "FRIENDS", "ME"] = "WORLD", bbox: str | None = None, zoom: int = 2, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    return map_service.get_map(db, viewer, mode, bbox, zoom)
