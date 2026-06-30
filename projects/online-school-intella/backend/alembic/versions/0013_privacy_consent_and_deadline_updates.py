"""privacy consent and deadline updates

Revision ID: 0013_privacy_consent
Revises: 0012_learning_responses
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_privacy_consent"
down_revision = "0012_learning_responses"
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
                        WHERE t.typname = 'deadlinetype'
                          AND e.enumlabel = 'learning_response'
                    ) THEN
                        ALTER TYPE deadlinetype ADD VALUE 'learning_response';
                    END IF;
                END
                $$;
                """
            )
        )

    consent_type = sa.Enum("personal_data", name="consenttype", create_type=False)
    consent_type.create(bind, checkfirst=True)

    op.create_table(
        "user_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consent_type", consent_type, nullable=False, server_default="personal_data"),
        sa.Column("document_version", sa.String(length=32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "consent_type", "document_version", name="uq_user_consents_user_type_version"),
    )
    op.create_index("ix_user_consents_user_id", "user_consents", ["user_id"], unique=False)
    op.create_index("ix_user_consents_consent_type", "user_consents", ["consent_type"], unique=False)
    op.create_index("ix_user_consents_document_version", "user_consents", ["document_version"], unique=False)
    op.create_index("ix_user_consents_accepted_at", "user_consents", ["accepted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_consents_accepted_at", table_name="user_consents")
    op.drop_index("ix_user_consents_document_version", table_name="user_consents")
    op.drop_index("ix_user_consents_consent_type", table_name="user_consents")
    op.drop_index("ix_user_consents_user_id", table_name="user_consents")
    op.drop_table("user_consents")
    sa.Enum(name="consenttype").drop(op.get_bind(), checkfirst=True)
