"""Add support chat subject and tags

Revision ID: 0016_support_chat_subject_tags
Revises: 0015_oral_admission_v1
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016_support_chat_subject_tags"
down_revision = "0015_oral_admission_v1"
branch_labels = None
depends_on = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "support_chats", "subject"):
        op.add_column("support_chats", sa.Column("subject", sa.String(length=255), nullable=True))

    if not _has_column(bind, "support_chats", "tags_json"):
        op.add_column(
            "support_chats",
            sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )

    if not _has_column(bind, "oral_responses", "video_url"):
        op.add_column("oral_responses", sa.Column("video_url", sa.String(length=512), nullable=True))



def downgrade() -> None:
    bind = op.get_bind()

    if _has_column(bind, "oral_responses", "video_url"):
        op.drop_column("oral_responses", "video_url")

    if _has_column(bind, "support_chats", "tags_json"):
        op.drop_column("support_chats", "tags_json")

    if _has_column(bind, "support_chats", "subject"):
        op.drop_column("support_chats", "subject")
