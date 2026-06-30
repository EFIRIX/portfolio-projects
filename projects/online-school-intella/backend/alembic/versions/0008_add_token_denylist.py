"""add token denylist table

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('token_denylist',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('jti', sa.String(length=255), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_type', sa.String(length=50), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_token_denylist_id'), 'token_denylist', ['id'], unique=False)
    op.create_index(op.f('ix_token_denylist_jti'), 'token_denylist', ['jti'], unique=True)
    op.create_index(op.f('ix_token_denylist_user_id'), 'token_denylist', ['user_id'], unique=False)
    op.create_index(op.f('ix_token_denylist_expires_at'), 'token_denylist', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_token_denylist_expires_at'), table_name='token_denylist')
    op.drop_index(op.f('ix_token_denylist_user_id'), table_name='token_denylist')
    op.drop_index(op.f('ix_token_denylist_jti'), table_name='token_denylist')
    op.drop_index(op.f('ix_token_denylist_id'), table_name='token_denylist')
    op.drop_table('token_denylist')
