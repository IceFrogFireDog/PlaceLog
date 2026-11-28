"""two-factor authentication (TOTP) and recovery codes

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("totp_salt", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("totp_pending_salt", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recovery_codes_user_id"), "recovery_codes", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_recovery_codes_user_id"), table_name="recovery_codes")
    op.drop_table("recovery_codes")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("totp_last_step")
        batch.drop_column("totp_enabled_at")
        batch.drop_column("totp_pending_salt")
        batch.drop_column("totp_salt")
