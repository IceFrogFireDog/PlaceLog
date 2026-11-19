"""사용자 표시 정보. 다른 서비스가 순환 참조 없이 쓰도록 의존성이 없는 모듈로 분리."""
from app.models import User
from app.schemas.user import UserBrief


def brief(user: User) -> UserBrief:
    return UserBrief(id=str(user.id), username=user.username, display_name=user.display_name)
