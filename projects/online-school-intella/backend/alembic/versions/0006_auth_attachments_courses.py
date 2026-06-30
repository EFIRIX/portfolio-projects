"""Auth hardening, chat attachments and courses

Revision ID: 0006_auth_attachments_courses
Revises: 0005_support_roles_social_layer
Create Date: 2026-04-19 22:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_auth_attachments_courses"
down_revision: Union[str, None] = "0005_support_roles_social_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


course_level_enum = sa.Enum("basic", "standard", "advanced", name="courselevel")
course_purchase_status_enum = sa.Enum("purchased", "in_progress", "completed", name="coursepurchasestatus")


def upgrade() -> None:
    op.add_column("users", sa.Column("login", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_users_login", "users", ["login"], unique=True)

    bind = op.get_bind()
    course_level_enum.create(bind, checkfirst=True)
    course_purchase_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_weeks", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("price_rub", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", course_level_enum, nullable=False, server_default="standard"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("title", name="uq_courses_title"),
    )
    op.create_index("ix_courses_id", "courses", ["id"])

    op.create_table(
        "course_purchases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", course_purchase_status_enum, nullable=False, server_default="purchased"),
        sa.Column("purchased_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "course_id", name="uq_course_purchase_user_course"),
    )
    op.create_index("ix_course_purchases_id", "course_purchases", ["id"])
    op.create_index("ix_course_purchases_user_id", "course_purchases", ["user_id"])
    op.create_index("ix_course_purchases_course_id", "course_purchases", ["course_id"])

    op.create_table(
        "support_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("support_chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("support_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_support_attachments_storage_key"),
    )
    op.create_index("ix_support_attachments_id", "support_attachments", ["id"])
    op.create_index("ix_support_attachments_uploader_id", "support_attachments", ["uploader_id"])
    op.create_index("ix_support_attachments_chat_id", "support_attachments", ["chat_id"])
    op.create_index("ix_support_attachments_message_id", "support_attachments", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_support_attachments_message_id", table_name="support_attachments")
    op.drop_index("ix_support_attachments_chat_id", table_name="support_attachments")
    op.drop_index("ix_support_attachments_uploader_id", table_name="support_attachments")
    op.drop_index("ix_support_attachments_id", table_name="support_attachments")
    op.drop_table("support_attachments")

    op.drop_index("ix_course_purchases_course_id", table_name="course_purchases")
    op.drop_index("ix_course_purchases_user_id", table_name="course_purchases")
    op.drop_index("ix_course_purchases_id", table_name="course_purchases")
    op.drop_table("course_purchases")

    op.drop_index("ix_courses_id", table_name="courses")
    op.drop_table("courses")

    bind = op.get_bind()
    course_purchase_status_enum.drop(bind, checkfirst=True)
    course_level_enum.drop(bind, checkfirst=True)

    op.drop_index("ix_users_login", table_name="users")
    op.drop_column("users", "is_active")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "login")
