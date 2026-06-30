"""learning responses

Revision ID: 0012_learning_responses
Revises: 0011_role_deadline_dialog_upgrade
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_learning_responses"
down_revision = "0011_role_deadline_dialog_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    source_type = sa.Enum(
        "topic",
        "topic_test",
        "exam",
        "milestone",
        "curator_task",
        name="learningresponsesourcetype",
    )
    response_status = sa.Enum(
        "draft",
        "sent",
        "in_review",
        "reviewed",
        "needs_revision",
        name="learningresponsestatus",
    )
    reviewer_role = sa.Enum(
        "curator",
        "methodist",
        name="learningresponsereviewerrole",
    )

    source_type.create(op.get_bind(), checkfirst=True)
    response_status.create(op.get_bind(), checkfirst=True)
    reviewer_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "learning_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewer_role", reviewer_role, nullable=True),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_ref", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("test_attempt_id", sa.Integer(), sa.ForeignKey("test_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("exam_attempt_id", sa.Integer(), sa.ForeignKey("exam_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("milestone_attempt_id", sa.Integer(), sa.ForeignKey("milestone_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("support_chats.id", ondelete="SET NULL"), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_answer", sa.Text(), nullable=True),
        sa.Column("audio_file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("video_file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", response_status, nullable=False, server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("rubric_scores_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rubric_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_learning_responses_student_id", "learning_responses", ["student_id"], unique=False)
    op.create_index("ix_learning_responses_reviewer_id", "learning_responses", ["reviewer_id"], unique=False)
    op.create_index("ix_learning_responses_reviewer_role", "learning_responses", ["reviewer_role"], unique=False)
    op.create_index("ix_learning_responses_source_type", "learning_responses", ["source_type"], unique=False)
    op.create_index("ix_learning_responses_source_ref", "learning_responses", ["source_ref"], unique=False)
    op.create_index("ix_learning_responses_topic_id", "learning_responses", ["topic_id"], unique=False)
    op.create_index("ix_learning_responses_test_attempt_id", "learning_responses", ["test_attempt_id"], unique=False)
    op.create_index("ix_learning_responses_exam_attempt_id", "learning_responses", ["exam_attempt_id"], unique=False)
    op.create_index("ix_learning_responses_milestone_attempt_id", "learning_responses", ["milestone_attempt_id"], unique=False)
    op.create_index("ix_learning_responses_chat_id", "learning_responses", ["chat_id"], unique=False)
    op.create_index("ix_learning_responses_audio_file_id", "learning_responses", ["audio_file_id"], unique=False)
    op.create_index("ix_learning_responses_video_file_id", "learning_responses", ["video_file_id"], unique=False)
    op.create_index("ix_learning_responses_status", "learning_responses", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_learning_responses_status", table_name="learning_responses")
    op.drop_index("ix_learning_responses_video_file_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_audio_file_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_chat_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_milestone_attempt_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_exam_attempt_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_test_attempt_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_topic_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_source_ref", table_name="learning_responses")
    op.drop_index("ix_learning_responses_source_type", table_name="learning_responses")
    op.drop_index("ix_learning_responses_reviewer_role", table_name="learning_responses")
    op.drop_index("ix_learning_responses_reviewer_id", table_name="learning_responses")
    op.drop_index("ix_learning_responses_student_id", table_name="learning_responses")
    op.drop_table("learning_responses")

    sa.Enum(name="learningresponsereviewerrole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="learningresponsestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="learningresponsesourcetype").drop(op.get_bind(), checkfirst=True)
