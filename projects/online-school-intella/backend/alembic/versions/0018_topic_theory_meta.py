"""Add structured theory meta field to topics

Revision ID: 0018_topic_theory_meta
Revises: 0017_support_question_subject
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0018_topic_theory_meta"
down_revision = "0017_support_question_subject"
branch_labels = None
depends_on = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "topics", "theory_meta_json"):
        op.add_column(
            "topics",
            sa.Column("theory_meta_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "topics", "theory_meta_json"):
        op.drop_column("topics", "theory_meta_json")
