"""role deadline dialog upgrade

Revision ID: 0011_role_deadline_dialog_upgrade
Revises: 0010_dashboard_deadlines_profile_birthdate
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_role_deadline_dialog_upgrade"
down_revision = "0010_dashboard_deadlines_profile_birthdate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    deadline_category = sa.Enum("curator_review", "self_study", "checkpoint", name="deadlinecategory")
    chat_status = sa.Enum(
        "open",
        "in_progress",
        "waiting_response",
        "resolved",
        "closed",
        "archived",
        name="chatstatus",
        create_type=False,
    )
    deadline_category.create(op.get_bind(), checkfirst=True)

    op.add_column("user_deadlines", sa.Column("category", deadline_category, nullable=False, server_default="self_study"))
    op.add_column("user_deadlines", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("user_deadlines", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_deadlines", sa.Column("canceled_by_id", sa.Integer(), nullable=True))
    op.create_index("ix_user_deadlines_category", "user_deadlines", ["category"], unique=False)
    op.create_index("ix_user_deadlines_created_by_id", "user_deadlines", ["created_by_id"], unique=False)
    op.create_index("ix_user_deadlines_canceled_by_id", "user_deadlines", ["canceled_by_id"], unique=False)
    op.create_foreign_key(None, "user_deadlines", "users", ["created_by_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "user_deadlines", "users", ["canceled_by_id"], ["id"], ondelete="SET NULL")

    op.execute("ALTER TYPE chatstatus ADD VALUE IF NOT EXISTS 'in_progress'")
    op.execute("ALTER TYPE chatstatus ADD VALUE IF NOT EXISTS 'waiting_response'")
    op.execute("ALTER TYPE chatstatus ADD VALUE IF NOT EXISTS 'resolved'")
    op.execute("ALTER TYPE chatstatus ADD VALUE IF NOT EXISTS 'archived'")

    op.add_column("support_chats", sa.Column("close_reason", sa.String(length=255), nullable=True))
    op.add_column("support_chats", sa.Column("close_comment", sa.Text(), nullable=True))
    op.add_column("support_chats", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("support_chats", sa.Column("closed_by_id", sa.Integer(), nullable=True))
    op.create_index("ix_support_chats_closed_by_id", "support_chats", ["closed_by_id"], unique=False)
    op.create_foreign_key(None, "support_chats", "users", ["closed_by_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "support_chat_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("support_chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_status", chat_status, nullable=True),
        sa.Column("to_status", chat_status, nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_chat_status_history_chat_id", "support_chat_status_history", ["chat_id"], unique=False)
    op.create_index("ix_support_chat_status_history_actor_id", "support_chat_status_history", ["actor_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_support_chat_status_history_actor_id", table_name="support_chat_status_history")
    op.drop_index("ix_support_chat_status_history_chat_id", table_name="support_chat_status_history")
    op.drop_table("support_chat_status_history")

    op.drop_constraint(None, "support_chats", type_="foreignkey")
    op.drop_index("ix_support_chats_closed_by_id", table_name="support_chats")
    op.drop_column("support_chats", "closed_by_id")
    op.drop_column("support_chats", "closed_at")
    op.drop_column("support_chats", "close_comment")
    op.drop_column("support_chats", "close_reason")

    op.drop_constraint(None, "user_deadlines", type_="foreignkey")
    op.drop_constraint(None, "user_deadlines", type_="foreignkey")
    op.drop_index("ix_user_deadlines_canceled_by_id", table_name="user_deadlines")
    op.drop_index("ix_user_deadlines_created_by_id", table_name="user_deadlines")
    op.drop_index("ix_user_deadlines_category", table_name="user_deadlines")
    op.drop_column("user_deadlines", "canceled_by_id")
    op.drop_column("user_deadlines", "canceled_at")
    op.drop_column("user_deadlines", "created_by_id")
    op.drop_column("user_deadlines", "category")
    sa.Enum(name="deadlinecategory").drop(op.get_bind(), checkfirst=True)
