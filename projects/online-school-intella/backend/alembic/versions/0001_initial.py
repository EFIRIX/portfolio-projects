"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-19 09:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_role_enum = sa.Enum("student", "admin", name="userrole")
question_type_enum = sa.Enum("topic_test", "diagnostic", "exam", name="questiontype")


def upgrade() -> None:

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("key_dates", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_topics_id", "topics", ["id"])

    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("key_dates", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_lessons_id", "lessons", ["id"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", question_type_enum, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_option", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_questions_id", "questions", ["id"])
    op.create_index("ix_questions_topic_id", "questions", ["topic_id"])

    op.create_table(
        "test_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_percent", sa.Float(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_test_attempts_id", "test_attempts", ["id"])
    op.create_index("ix_test_attempts_user_id", "test_attempts", ["user_id"])
    op.create_index("ix_test_attempts_topic_id", "test_attempts", ["topic_id"])

    op.create_table(
        "diagnostic_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_percent", sa.Float(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("weak_topics", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("details", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_diagnostic_results_id", "diagnostic_results", ["id"])
    op.create_index("ix_diagnostic_results_user_id", "diagnostic_results", ["user_id"])

    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_percent", sa.Float(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exam_attempts_id", "exam_attempts", ["id"])
    op.create_index("ix_exam_attempts_user_id", "exam_attempts", ["user_id"])

    op.create_table(
        "progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total_topics", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mastered_topics", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("weak_topics", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_progress_user_id"),
    )
    op.create_index("ix_progress_id", "progress", ["id"])
    op.create_index("ix_progress_user_id", "progress", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_progress_user_id", table_name="progress")
    op.drop_index("ix_progress_id", table_name="progress")
    op.drop_table("progress")

    op.drop_index("ix_exam_attempts_user_id", table_name="exam_attempts")
    op.drop_index("ix_exam_attempts_id", table_name="exam_attempts")
    op.drop_table("exam_attempts")

    op.drop_index("ix_diagnostic_results_user_id", table_name="diagnostic_results")
    op.drop_index("ix_diagnostic_results_id", table_name="diagnostic_results")
    op.drop_table("diagnostic_results")

    op.drop_index("ix_test_attempts_topic_id", table_name="test_attempts")
    op.drop_index("ix_test_attempts_user_id", table_name="test_attempts")
    op.drop_index("ix_test_attempts_id", table_name="test_attempts")
    op.drop_table("test_attempts")

    op.drop_index("ix_questions_topic_id", table_name="questions")
    op.drop_index("ix_questions_id", table_name="questions")
    op.drop_table("questions")

    op.drop_index("ix_lessons_id", table_name="lessons")
    op.drop_table("lessons")

    op.drop_index("ix_topics_id", table_name="topics")
    op.drop_table("topics")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    question_type_enum.drop(op.get_bind(), checkfirst=True)
    user_role_enum.drop(op.get_bind(), checkfirst=True)
