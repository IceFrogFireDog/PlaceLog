from datetime import datetime

from app.schemas.common import StrictModel
from pydantic import BaseModel

from app.schemas.user import UserBrief


class FriendRequestIn(StrictModel):
    target_user_id: str


class FriendshipOut(BaseModel):
    id: str
    status: str
    direction: str | None = None  # incoming / outgoing (PENDING일 때)
    user: UserBrief  # 상대방
    created_at: datetime
    accepted_at: datetime | None = None
