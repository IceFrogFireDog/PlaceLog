import uuid

from app.core.errors import not_found


def parse_uuid(value: str, what: str = "리소스") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as e:
        raise not_found(what) from e
