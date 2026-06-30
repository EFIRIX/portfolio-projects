"""Add reset token version to users

Revision ID: 0004_user_reset_token_version
Revises: 0003_topic_section_metadata
Create Date: 2026-04-19 14:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_user_reset_token_version"
down_revision: Union[str, None] = "0003_topic_section_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("reset_token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "reset_token_version")
