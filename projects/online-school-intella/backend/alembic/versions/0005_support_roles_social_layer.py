"""Add support roles and social layer tables

Revision ID: 0005_support_roles_social_layer
Revises: 0004_user_reset_token_version
Create Date: 2026-04-19 18:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_support_roles_social_layer"
down_revision: Union[str, None] = "0004_user_reset_token_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


chat_status_enum = sa.Enum("open", "closed", name="chatstatus")
message_status_enum = sa.Enum("sent", "read", name="messagestatus")
question_status_enum = sa.Enum("new", "in_progress", "answered", "archived", name="supportquestionstatus")
question_priority_enum = sa.Enum("low", "normal", "high", name="supportquestionpriority")
question_category_enum = sa.Enum("topic", "test_error", "exam_general", name="supportquestioncategory")


def _extend_user_role_enum() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'curator'")
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'moderator'")


def upgrade() -> None:
    _extend_user_role_enum()

    bind = op.get_bind()
    chat_status_enum.create(bind, checkfirst=True)
    message_status_enum.create(bind, checkfirst=True)
    question_status_enum.create(bind, checkfirst=True)
    question_priority_enum.create(bind, checkfirst=True)
    question_category_enum.create(bind, checkfirst=True)

    op.add_column("users", sa.Column("nickname", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("accent_color", sa.String(length=32), nullable=False, server_default="#6366F1"),
    )
    op.add_column(
        "users",
        sa.Column("avatar_frame", sa.String(length=32), nullable=False, server_default="classic"),
    )
    op.add_column(
        "users",
        sa.Column("profile_theme", sa.String(length=32), nullable=False, server_default="clean"),
    )
    op.create_index("ix_users_nickname", "users", ["nickname"], unique=True)

    op.create_table(
        "support_chats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("curator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_attempt_id", sa.Integer(), nullable=True),
        sa.Column("status", chat_status_enum, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_chats_id", "support_chats", ["id"])
    op.create_index("ix_support_chats_student_id", "support_chats", ["student_id"])
    op.create_index("ix_support_chats_curator_id", "support_chats", ["curator_id"])
    op.create_index("ix_support_chats_topic_id", "support_chats", ["topic_id"])

    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("support_chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", message_status_enum, nullable=False, server_default="sent"),
        sa.Column("context_type", sa.String(length=64), nullable=True),
        sa.Column("context_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_support_messages_id", "support_messages", ["id"])
    op.create_index("ix_support_messages_chat_id", "support_messages", ["chat_id"])
    op.create_index("ix_support_messages_sender_id", "support_messages", ["sender_id"])

    op.create_table(
        "support_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_curator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_attempt_id", sa.Integer(), nullable=True),
        sa.Column("category", question_category_enum, nullable=False, server_default="exam_general"),
        sa.Column("status", question_status_enum, nullable=False, server_default="new"),
        sa.Column("priority", question_priority_enum, nullable=False, server_default="normal"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_questions_id", "support_questions", ["id"])
    op.create_index("ix_support_questions_student_id", "support_questions", ["student_id"])
    op.create_index("ix_support_questions_assigned_curator_id", "support_questions", ["assigned_curator_id"])
    op.create_index("ix_support_questions_topic_id", "support_questions", ["topic_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("href", sa.String(length=255), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])

    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "code", name="uq_user_achievement_code"),
    )
    op.create_index("ix_user_achievements_id", "user_achievements", ["id"])
    op.create_index("ix_user_achievements_user_id", "user_achievements", ["user_id"])
    op.create_index("ix_user_achievements_code", "user_achievements", ["code"])


def downgrade() -> None:
    op.drop_index("ix_user_achievements_code", table_name="user_achievements")
    op.drop_index("ix_user_achievements_user_id", table_name="user_achievements")
    op.drop_index("ix_user_achievements_id", table_name="user_achievements")
    op.drop_table("user_achievements")

    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_support_questions_topic_id", table_name="support_questions")
    op.drop_index("ix_support_questions_assigned_curator_id", table_name="support_questions")
    op.drop_index("ix_support_questions_student_id", table_name="support_questions")
    op.drop_index("ix_support_questions_id", table_name="support_questions")
    op.drop_table("support_questions")

    op.drop_index("ix_support_messages_sender_id", table_name="support_messages")
    op.drop_index("ix_support_messages_chat_id", table_name="support_messages")
    op.drop_index("ix_support_messages_id", table_name="support_messages")
    op.drop_table("support_messages")

    op.drop_index("ix_support_chats_topic_id", table_name="support_chats")
    op.drop_index("ix_support_chats_curator_id", table_name="support_chats")
    op.drop_index("ix_support_chats_student_id", table_name="support_chats")
    op.drop_index("ix_support_chats_id", table_name="support_chats")
    op.drop_table("support_chats")

    op.drop_index("ix_users_nickname", table_name="users")
    op.drop_column("users", "profile_theme")
    op.drop_column("users", "avatar_frame")
    op.drop_column("users", "accent_color")
    op.drop_column("users", "nickname")

    bind = op.get_bind()
    question_category_enum.drop(bind, checkfirst=True)
    question_priority_enum.drop(bind, checkfirst=True)
    question_status_enum.drop(bind, checkfirst=True)
    message_status_enum.drop(bind, checkfirst=True)
    chat_status_enum.drop(bind, checkfirst=True)
