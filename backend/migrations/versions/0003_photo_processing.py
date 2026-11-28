"""photo processing status (PROCESSING/READY/FAILED) + globe index

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08 14:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 기존 사진은 이미 변환이 끝났으므로 READY (server_default로 채워진다)
    with op.batch_alter_table("photos") as batch:
        batch.add_column(sa.Column("status", sa.String(length=10), server_default="READY", nullable=False))
        batch.add_column(sa.Column("processing_error", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("processing_attempts", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint("ck_photos_status", "status IN ('PROCESSING','READY','FAILED')")
        batch.create_index(batch.f("ix_photos_status"), ["status"], unique=False)
    # 지구본 전체 지도(WORLD) 집계용 부분 인덱스
    world = sa.text("visibility = 'PUBLIC' AND status = 'READY'")
    op.create_index("ix_photos_world_place", "photos", ["place_id"], unique=False, postgresql_where=world, sqlite_where=world)


def downgrade() -> None:
    op.drop_index("ix_photos_world_place", table_name="photos")
    with op.batch_alter_table("photos") as batch:
        batch.drop_index(batch.f("ix_photos_status"))
        batch.drop_constraint("ck_photos_status", type_="check")
        batch.drop_column("processing_started_at")
        batch.drop_column("processing_attempts")
        batch.drop_column("processing_error")
        batch.drop_column("status")
