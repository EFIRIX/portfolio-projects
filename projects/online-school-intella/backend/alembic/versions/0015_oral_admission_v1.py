"""oral admission v1

Revision ID: 0015_oral_admission_v1
Revises: 0014_learning_path_parent_v2
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_oral_admission_v1"
down_revision = "0014_learning_path_parent_v2"
branch_labels = None
depends_on = None


def _safe_create_enum(bind, enum_type: sa.Enum) -> None:
    try:
        enum_type.create(bind, checkfirst=True)
    except Exception as exc:
        message = str(exc).lower()
        if bind.dialect.name == "postgresql" and ("already exists" in message or "duplicateobject" in message):
            return
        raise


def upgrade() -> None:
    bind = op.get_bind()

    oral_task_type = sa.Enum("SHORT_Q", "TEXT_TASK", "ORAL_TICKET", name="oraltasktype", create_type=False)
    oral_difficulty = sa.Enum("easy", "standard", "hard", name="oraldifficulty", create_type=False)
    oral_attempt_mode = sa.Enum("training", "exam_sim", name="oralattemptmode", create_type=False)
    oral_response_status = sa.Enum("draft", "submitted", "in_review", "approved", "needs_revision", name="oralresponsestatus", create_type=False)
    oral_reviewer_role = sa.Enum("curator", "methodist", name="oralreviewerrole", create_type=False)
    oral_checkpoint_type = sa.Enum("TEXT_TASK", "ORAL_TICKET", "MIXED", name="oralcheckpointtype", create_type=False)

    _safe_create_enum(bind, oral_task_type)
    _safe_create_enum(bind, oral_difficulty)
    _safe_create_enum(bind, oral_attempt_mode)
    _safe_create_enum(bind, oral_response_status)
    _safe_create_enum(bind, oral_reviewer_role)
    _safe_create_enum(bind, oral_checkpoint_type)

    op.create_table(
        "oral_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("section_order", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oral_topics_id", "oral_topics", ["id"], unique=False)
    op.create_index("ix_oral_topics_title", "oral_topics", ["title"], unique=True)
    op.create_index("ix_oral_topics_section", "oral_topics", ["section"], unique=False)

    op.create_table(
        "oral_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", oral_task_type, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("passage_text", sa.Text(), nullable=True),
        sa.Column("rubric_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("difficulty", oral_difficulty, nullable=False, server_default="standard"),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("oral_topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source", sa.String(length=128), nullable=False, server_default="docx сборник"),
        sa.Column("source_ref", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source", "source_ref", name="uq_oral_tasks_source_ref"),
    )
    op.create_index("ix_oral_tasks_id", "oral_tasks", ["id"], unique=False)
    op.create_index("ix_oral_tasks_type", "oral_tasks", ["type"], unique=False)
    op.create_index("ix_oral_tasks_difficulty", "oral_tasks", ["difficulty"], unique=False)
    op.create_index("ix_oral_tasks_topic_id", "oral_tasks", ["topic_id"], unique=False)
    op.create_index("ix_oral_tasks_source", "oral_tasks", ["source"], unique=False)
    op.create_index("ix_oral_tasks_source_ref", "oral_tasks", ["source_ref"], unique=False)

    op.create_table(
        "oral_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("oral_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("mode", oral_attempt_mode, nullable=False, server_default="training"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("readiness_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score_raw", sa.Float(), nullable=True),
        sa.Column("total_raw", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oral_attempts_id", "oral_attempts", ["id"], unique=False)
    op.create_index("ix_oral_attempts_user_id", "oral_attempts", ["user_id"], unique=False)
    op.create_index("ix_oral_attempts_task_id", "oral_attempts", ["task_id"], unique=False)
    op.create_index("ix_oral_attempts_session_id", "oral_attempts", ["session_id"], unique=False)
    op.create_index("ix_oral_attempts_mode", "oral_attempts", ["mode"], unique=False)

    op.create_table(
        "oral_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("oral_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("oral_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text_answer", sa.Text(), nullable=True),
        sa.Column("audio_url", sa.String(length=512), nullable=True),
        sa.Column("status", oral_response_status, nullable=False, server_default="draft"),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewer_role", oral_reviewer_role, nullable=True),
        sa.Column("reviewer_comment", sa.Text(), nullable=True),
        sa.Column("scores_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("credited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oral_responses_id", "oral_responses", ["id"], unique=False)
    op.create_index("ix_oral_responses_user_id", "oral_responses", ["user_id"], unique=False)
    op.create_index("ix_oral_responses_task_id", "oral_responses", ["task_id"], unique=False)
    op.create_index("ix_oral_responses_attempt_id", "oral_responses", ["attempt_id"], unique=False)
    op.create_index("ix_oral_responses_status", "oral_responses", ["status"], unique=False)
    op.create_index("ix_oral_responses_reviewer_id", "oral_responses", ["reviewer_id"], unique=False)
    op.create_index("ix_oral_responses_reviewer_role", "oral_responses", ["reviewer_role"], unique=False)

    op.create_table(
        "readiness_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("readiness_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("deficits_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("trend_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("recommendations_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_exam_sim_score", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_readiness_profiles_id", "readiness_profiles", ["id"], unique=False)
    op.create_index("ix_readiness_profiles_user_id", "readiness_profiles", ["user_id"], unique=True)

    op.create_table(
        "oral_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkpoint_type", oral_checkpoint_type, nullable=False, server_default="mixed"),
        sa.Column("topic_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("threshold_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("require_facts_nonzero", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oral_checkpoints_id", "oral_checkpoints", ["id"], unique=False)
    op.create_index("ix_oral_checkpoints_checkpoint_type", "oral_checkpoints", ["checkpoint_type"], unique=False)
    op.create_index("ix_oral_checkpoints_is_active", "oral_checkpoints", ["is_active"], unique=False)

    op.create_table(
        "oral_checkpoint_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checkpoint_id", sa.Integer(), sa.ForeignKey("oral_checkpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("oral_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("score_raw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_raw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oral_checkpoint_attempts_id", "oral_checkpoint_attempts", ["id"], unique=False)
    op.create_index("ix_oral_checkpoint_attempts_checkpoint_id", "oral_checkpoint_attempts", ["checkpoint_id"], unique=False)
    op.create_index("ix_oral_checkpoint_attempts_user_id", "oral_checkpoint_attempts", ["user_id"], unique=False)
    op.create_index("ix_oral_checkpoint_attempts_attempt_id", "oral_checkpoint_attempts", ["attempt_id"], unique=False)
    op.create_index("ix_oral_checkpoint_attempts_passed", "oral_checkpoint_attempts", ["passed"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_oral_checkpoint_attempts_passed", table_name="oral_checkpoint_attempts")
    op.drop_index("ix_oral_checkpoint_attempts_attempt_id", table_name="oral_checkpoint_attempts")
    op.drop_index("ix_oral_checkpoint_attempts_user_id", table_name="oral_checkpoint_attempts")
    op.drop_index("ix_oral_checkpoint_attempts_checkpoint_id", table_name="oral_checkpoint_attempts")
    op.drop_index("ix_oral_checkpoint_attempts_id", table_name="oral_checkpoint_attempts")
    op.drop_table("oral_checkpoint_attempts")

    op.drop_index("ix_oral_checkpoints_is_active", table_name="oral_checkpoints")
    op.drop_index("ix_oral_checkpoints_checkpoint_type", table_name="oral_checkpoints")
    op.drop_index("ix_oral_checkpoints_id", table_name="oral_checkpoints")
    op.drop_table("oral_checkpoints")

    op.drop_index("ix_readiness_profiles_user_id", table_name="readiness_profiles")
    op.drop_index("ix_readiness_profiles_id", table_name="readiness_profiles")
    op.drop_table("readiness_profiles")

    op.drop_index("ix_oral_responses_reviewer_role", table_name="oral_responses")
    op.drop_index("ix_oral_responses_reviewer_id", table_name="oral_responses")
    op.drop_index("ix_oral_responses_status", table_name="oral_responses")
    op.drop_index("ix_oral_responses_attempt_id", table_name="oral_responses")
    op.drop_index("ix_oral_responses_task_id", table_name="oral_responses")
    op.drop_index("ix_oral_responses_user_id", table_name="oral_responses")
    op.drop_index("ix_oral_responses_id", table_name="oral_responses")
    op.drop_table("oral_responses")

    op.drop_index("ix_oral_attempts_mode", table_name="oral_attempts")
    op.drop_index("ix_oral_attempts_session_id", table_name="oral_attempts")
    op.drop_index("ix_oral_attempts_task_id", table_name="oral_attempts")
    op.drop_index("ix_oral_attempts_user_id", table_name="oral_attempts")
    op.drop_index("ix_oral_attempts_id", table_name="oral_attempts")
    op.drop_table("oral_attempts")

    op.drop_index("ix_oral_tasks_source_ref", table_name="oral_tasks")
    op.drop_index("ix_oral_tasks_source", table_name="oral_tasks")
    op.drop_index("ix_oral_tasks_topic_id", table_name="oral_tasks")
    op.drop_index("ix_oral_tasks_difficulty", table_name="oral_tasks")
    op.drop_index("ix_oral_tasks_type", table_name="oral_tasks")
    op.drop_index("ix_oral_tasks_id", table_name="oral_tasks")
    op.drop_table("oral_tasks")

    op.drop_index("ix_oral_topics_section", table_name="oral_topics")
    op.drop_index("ix_oral_topics_title", table_name="oral_topics")
    op.drop_index("ix_oral_topics_id", table_name="oral_topics")
    op.drop_table("oral_topics")

    sa.Enum(name="oralcheckpointtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="oralreviewerrole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="oralresponsestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="oralattemptmode").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="oraldifficulty").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="oraltasktype").drop(op.get_bind(), checkfirst=True)
