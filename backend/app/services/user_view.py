"""사용자 표시 정보(이름·프로필 사진 주소). 다른 서비스가 순환 참조 없이 쓰도록 의존성이 없는 모듈로 분리."""
from app.models import User
from app.schemas.user import UserBrief


def avatar_url(user: User) -> str | None:
    """프로필 사진 주소. 바꿀 때마다 파일 이름이 달라지므로 브라우저가 오래 캐시해도 된다."""
    if not user.avatar_key:
        return None
    file_id = user.avatar_key.rsplit("/", 1)[-1].removesuffix(".webp")
    return f"/api/v1/media/avatars/{user.id}/{file_id}"


def brief(user: User) -> UserBrief:
    return UserBrief(id=str(user.id), username=user.username, display_name=user.display_name, avatar_url=avatar_url(user))
