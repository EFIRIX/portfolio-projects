"""Add topic section metadata

Revision ID: 0003_topic_section_metadata
Revises: 0002_question_difficulty
Create Date: 2026-04-19 13:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_topic_section_metadata"
down_revision: Union[str, None] = "0002_question_difficulty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("topics", sa.Column("section", sa.String(length=255), nullable=True))
    op.add_column("topics", sa.Column("section_order", sa.Integer(), nullable=True))
    op.create_index("ix_topics_section", "topics", ["section"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_topics_section", table_name="topics")
    op.drop_column("topics", "section_order")
    op.drop_column("topics", "section")
