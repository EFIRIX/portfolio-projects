"""Add question difficulty

Revision ID: 0002_question_difficulty
Revises: 0001_initial
Create Date: 2026-04-19 12:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_question_difficulty"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


question_difficulty_enum = sa.Enum("easy", "medium", "hard", name="questiondifficulty")


def upgrade() -> None:
    bind = op.get_bind()
    question_difficulty_enum.create(bind, checkfirst=True)

    op.add_column(
        "questions",
        sa.Column("difficulty", question_difficulty_enum, nullable=False, server_default="medium"),
    )


def downgrade() -> None:
    op.drop_column("questions", "difficulty")
    question_difficulty_enum.drop(op.get_bind(), checkfirst=True)
