"""EdTech ecosystem delta v1 tables and support extensions

Revision ID: 0009_ecosystem_delta_v1
Revises: 0008
Create Date: 2026-04-21 18:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_ecosystem_delta_v1"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


counterpart_role_enum = sa.Enum("curator", "methodist", name="counterpartrole")
assignee_role_enum = sa.Enum("curator", "methodist", name="supportquestionassigneerole")
flashcard_mode_enum = sa.Enum("quick_review", "pre_test", "pre_exam", name="flashcardmode")
learning_activity_type_enum = sa.Enum(
    "topic",
    "lesson",
    "flashcards",
    "topic_test",
    "mistakes",
    "exam",
    "milestone",
    name="learningactivitytype",
)
currency_reason_enum = sa.Enum(
    "topic_test",
    "exam",
    "milestone",
    "streak",
    "daily_plan",
    "wheel_cost",
    "wheel_reward",
    "admin_adjustment",
    name="currencyreason",
)


def _extend_user_role_enum() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'methodist'")


def upgrade() -> None:
    _extend_user_role_enum()

    bind = op.get_bind()
    counterpart_role_enum.create(bind, checkfirst=True)
    assignee_role_enum.create(bind, checkfirst=True)
    flashcard_mode_enum.create(bind, checkfirst=True)
    learning_activity_type_enum.create(bind, checkfirst=True)
    currency_reason_enum.create(bind, checkfirst=True)

    op.add_column(
        "support_chats",
        sa.Column("counterpart_role", counterpart_role_enum, nullable=False, server_default="curator"),
    )
    op.add_column(
        "support_questions",
        sa.Column("assigned_role", assignee_role_enum, nullable=True),
    )
    op.add_column(
        "test_attempts",
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "flashcards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mode", flashcard_mode_enum, nullable=False, server_default="quick_review"),
        sa.Column("front_text", sa.String(length=255), nullable=False),
        sa.Column("back_text", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_flashcards_id", "flashcards", ["id"])
    op.create_index("ix_flashcards_topic_id", "flashcards", ["topic_id"])
    op.create_index("ix_flashcards_author_id", "flashcards", ["author_id"])

    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", learning_activity_type_enum, nullable=False, server_default="topic"),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_sessions_id", "learning_sessions", ["id"])
    op.create_index("ix_learning_sessions_user_id", "learning_sessions", ["user_id"])
    op.create_index("ix_learning_sessions_topic_id", "learning_sessions", ["topic_id"])

    op.create_table(
        "milestone_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=False),
        sa.Column("topic_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("pass_threshold", sa.Float(), nullable=False, server_default="70"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_milestone_assessments_id", "milestone_assessments", ["id"])

    op.create_table(
        "milestone_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("milestone_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_percent", sa.Float(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("details", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_milestone_attempts_id", "milestone_attempts", ["id"])
    op.create_index("ix_milestone_attempts_assessment_id", "milestone_attempts", ["assessment_id"])
    op.create_index("ix_milestone_attempts_user_id", "milestone_attempts", ["user_id"])

    op.create_table(
        "currency_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", currency_reason_enum, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_currency_transactions_id", "currency_transactions", ["id"])
    op.create_index("ix_currency_transactions_user_id", "currency_transactions", ["user_id"])

    op.create_table(
        "wheel_spins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("reward_type", sa.String(length=64), nullable=False),
        sa.Column("reward_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_label", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_wheel_spins_id", "wheel_spins", ["id"])
    op.create_index("ix_wheel_spins_user_id", "wheel_spins", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_wheel_spins_user_id", table_name="wheel_spins")
    op.drop_index("ix_wheel_spins_id", table_name="wheel_spins")
    op.drop_table("wheel_spins")

    op.drop_index("ix_currency_transactions_user_id", table_name="currency_transactions")
    op.drop_index("ix_currency_transactions_id", table_name="currency_transactions")
    op.drop_table("currency_transactions")

    op.drop_index("ix_milestone_attempts_user_id", table_name="milestone_attempts")
    op.drop_index("ix_milestone_attempts_assessment_id", table_name="milestone_attempts")
    op.drop_index("ix_milestone_attempts_id", table_name="milestone_attempts")
    op.drop_table("milestone_attempts")

    op.drop_index("ix_milestone_assessments_id", table_name="milestone_assessments")
    op.drop_table("milestone_assessments")

    op.drop_index("ix_learning_sessions_topic_id", table_name="learning_sessions")
    op.drop_index("ix_learning_sessions_user_id", table_name="learning_sessions")
    op.drop_index("ix_learning_sessions_id", table_name="learning_sessions")
    op.drop_table("learning_sessions")

    op.drop_index("ix_flashcards_author_id", table_name="flashcards")
    op.drop_index("ix_flashcards_topic_id", table_name="flashcards")
    op.drop_index("ix_flashcards_id", table_name="flashcards")
    op.drop_table("flashcards")

    op.drop_column("test_attempts", "duration_seconds")
    op.drop_column("support_questions", "assigned_role")
    op.drop_column("support_chats", "counterpart_role")

    bind = op.get_bind()
    currency_reason_enum.drop(bind, checkfirst=True)
    learning_activity_type_enum.drop(bind, checkfirst=True)
    flashcard_mode_enum.drop(bind, checkfirst=True)
    assignee_role_enum.drop(bind, checkfirst=True)
    counterpart_role_enum.drop(bind, checkfirst=True)
