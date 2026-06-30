"""learning path persistence, parent links and flashcard SR

Revision ID: 0014_learning_path_parent_v2
Revises: 0013_privacy_consent
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_learning_path_parent_v2"
down_revision = "0013_privacy_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_type t
                        JOIN pg_enum e ON e.enumtypid = t.oid
                        WHERE t.typname = 'userrole'
                          AND e.enumlabel = 'parent'
                    ) THEN
                        ALTER TYPE userrole ADD VALUE 'parent';
                    END IF;
                END
                $$;
                """
            )
        )

    learning_plan_item_status = sa.Enum("pending", "completed", "skipped", name="learningplanitemstatus", create_type=False)
    learning_plan_item_status.create(bind, checkfirst=True)

    op.create_table(
        "learning_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("target_exam_date", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("weak_topic_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("forecast_index", sa.Float(), nullable=False, server_default="0"),
        sa.Column("forecast_trend", sa.Float(), nullable=False, server_default="0"),
        sa.Column("remaining_to_goal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_step", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_plans_id", "learning_plans", ["id"], unique=False)
    op.create_index("ix_learning_plans_user_id", "learning_plans", ["user_id"], unique=True)

    op.create_table(
        "learning_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("learning_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("href", sa.String(length=255), nullable=False),
        sa.Column("action_label", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_today", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("week_index", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", learning_plan_item_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_plan_items_id", "learning_plan_items", ["id"], unique=False)
    op.create_index("ix_learning_plan_items_plan_id", "learning_plan_items", ["plan_id"], unique=False)
    op.create_index("ix_learning_plan_items_user_id", "learning_plan_items", ["user_id"], unique=False)
    op.create_index("ix_learning_plan_items_topic_id", "learning_plan_items", ["topic_id"], unique=False)
    op.create_index("ix_learning_plan_items_is_today", "learning_plan_items", ["is_today"], unique=False)
    op.create_index("ix_learning_plan_items_status", "learning_plan_items", ["status"], unique=False)

    op.create_table(
        "user_flashcard_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("card_key", sa.String(length=96), nullable=False),
        sa.Column("success_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviews_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("easiness", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "card_key", name="uq_user_flashcard_review_key"),
    )
    op.create_index("ix_user_flashcard_reviews_id", "user_flashcard_reviews", ["id"], unique=False)
    op.create_index("ix_user_flashcard_reviews_user_id", "user_flashcard_reviews", ["user_id"], unique=False)
    op.create_index("ix_user_flashcard_reviews_topic_id", "user_flashcard_reviews", ["topic_id"], unique=False)
    op.create_index("ix_user_flashcard_reviews_card_key", "user_flashcard_reviews", ["card_key"], unique=False)
    op.create_index("ix_user_flashcard_reviews_due_at", "user_flashcard_reviews", ["due_at"], unique=False)

    op.create_table(
        "parent_invite_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=24), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_parent_invite_codes_id", "parent_invite_codes", ["id"], unique=False)
    op.create_index("ix_parent_invite_codes_student_id", "parent_invite_codes", ["student_id"], unique=False)
    op.create_index("ix_parent_invite_codes_code", "parent_invite_codes", ["code"], unique=True)
    op.create_index("ix_parent_invite_codes_expires_at", "parent_invite_codes", ["expires_at"], unique=False)

    op.create_table(
        "parent_student_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("parent_id", "student_id", name="uq_parent_student_link"),
    )
    op.create_index("ix_parent_student_links_id", "parent_student_links", ["id"], unique=False)
    op.create_index("ix_parent_student_links_parent_id", "parent_student_links", ["parent_id"], unique=False)
    op.create_index("ix_parent_student_links_student_id", "parent_student_links", ["student_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_parent_student_links_student_id", table_name="parent_student_links")
    op.drop_index("ix_parent_student_links_parent_id", table_name="parent_student_links")
    op.drop_index("ix_parent_student_links_id", table_name="parent_student_links")
    op.drop_table("parent_student_links")

    op.drop_index("ix_parent_invite_codes_expires_at", table_name="parent_invite_codes")
    op.drop_index("ix_parent_invite_codes_code", table_name="parent_invite_codes")
    op.drop_index("ix_parent_invite_codes_student_id", table_name="parent_invite_codes")
    op.drop_index("ix_parent_invite_codes_id", table_name="parent_invite_codes")
    op.drop_table("parent_invite_codes")

    op.drop_index("ix_user_flashcard_reviews_due_at", table_name="user_flashcard_reviews")
    op.drop_index("ix_user_flashcard_reviews_card_key", table_name="user_flashcard_reviews")
    op.drop_index("ix_user_flashcard_reviews_topic_id", table_name="user_flashcard_reviews")
    op.drop_index("ix_user_flashcard_reviews_user_id", table_name="user_flashcard_reviews")
    op.drop_index("ix_user_flashcard_reviews_id", table_name="user_flashcard_reviews")
    op.drop_table("user_flashcard_reviews")

    op.drop_index("ix_learning_plan_items_status", table_name="learning_plan_items")
    op.drop_index("ix_learning_plan_items_is_today", table_name="learning_plan_items")
    op.drop_index("ix_learning_plan_items_topic_id", table_name="learning_plan_items")
    op.drop_index("ix_learning_plan_items_user_id", table_name="learning_plan_items")
    op.drop_index("ix_learning_plan_items_plan_id", table_name="learning_plan_items")
    op.drop_index("ix_learning_plan_items_id", table_name="learning_plan_items")
    op.drop_table("learning_plan_items")

    op.drop_index("ix_learning_plans_user_id", table_name="learning_plans")
    op.drop_index("ix_learning_plans_id", table_name="learning_plans")
    op.drop_table("learning_plans")

    sa.Enum(name="learningplanitemstatus").drop(op.get_bind(), checkfirst=True)
