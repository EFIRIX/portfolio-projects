"""Add support question subject field

Revision ID: 0017_support_question_subject
Revises: 0016_support_chat_subject_tags
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0017_support_question_subject"
down_revision = "0016_support_chat_subject_tags"
branch_labels = None
depends_on = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "support_questions", "subject"):
        op.add_column("support_questions", sa.Column("subject", sa.String(length=255), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "support_questions", "subject"):
        op.drop_column("support_questions", "subject")
