"""Add profile birthdate/onboarding fields and user deadlines table

Revision ID: 0010_dashboard_deadlines_profile_birthdate
Revises: 0009_ecosystem_delta_v1
Create Date: 2026-04-21 20:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_dashboard_deadlines_profile_birthdate"
down_revision: Union[str, None] = "0009_ecosystem_delta_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


deadline_type_enum = sa.Enum("topic", "test", "exam", "milestone", "onboarding", name="deadlinetype")
deadline_urgency_enum = sa.Enum("normal", "soon", "urgent", name="deadlineurgency")
deadline_source_enum = sa.Enum("system", "manual", name="deadlinesource")


def upgrade() -> None:
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    deadline_type_enum.create(bind, checkfirst=True)
    deadline_urgency_enum.create(bind, checkfirst=True)
    deadline_source_enum.create(bind, checkfirst=True)

    op.create_table(
        "user_deadlines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("item_type", deadline_type_enum, nullable=False),
        sa.Column("item_ref", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("urgency", deadline_urgency_enum, nullable=False, server_default="normal"),
        sa.Column("source", deadline_source_enum, nullable=False, server_default="system"),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "item_type", "item_ref", "source", name="uq_user_deadlines_item"),
    )
    op.create_index("ix_user_deadlines_id", "user_deadlines", ["id"])
    op.create_index("ix_user_deadlines_user_id", "user_deadlines", ["user_id"])
    op.create_index("ix_user_deadlines_item_type", "user_deadlines", ["item_type"])
    op.create_index("ix_user_deadlines_due_at", "user_deadlines", ["due_at"])
    op.create_index("ix_user_deadlines_urgency", "user_deadlines", ["urgency"])
    op.create_index("ix_user_deadlines_is_done", "user_deadlines", ["is_done"])


def downgrade() -> None:
    op.drop_index("ix_user_deadlines_is_done", table_name="user_deadlines")
    op.drop_index("ix_user_deadlines_urgency", table_name="user_deadlines")
    op.drop_index("ix_user_deadlines_due_at", table_name="user_deadlines")
    op.drop_index("ix_user_deadlines_item_type", table_name="user_deadlines")
    op.drop_index("ix_user_deadlines_user_id", table_name="user_deadlines")
    op.drop_index("ix_user_deadlines_id", table_name="user_deadlines")
    op.drop_table("user_deadlines")

    bind = op.get_bind()
    deadline_source_enum.drop(bind, checkfirst=True)
    deadline_urgency_enum.drop(bind, checkfirst=True)
    deadline_type_enum.drop(bind, checkfirst=True)

    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "date_of_birth")
