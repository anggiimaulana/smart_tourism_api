"""add chatbot cache table

Revision ID: 2c4f7a9b6d10
Revises: 9a7c4f1b2d3e
Create Date: 2026-05-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c4f7a9b6d10'
down_revision = '9a7c4f1b2d3e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'chatbot_cache',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('query_hash', sa.String(length=128), nullable=False),
        sa.Column('query_normalized', sa.Text(), nullable=False),
        sa.Column('answer', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('query_hash', name='uq_chatbot_cache_query_hash'),
    )
    op.create_index('ix_chatbot_cache_query_hash', 'chatbot_cache', ['query_hash'], unique=True)


def downgrade():
    op.drop_index('ix_chatbot_cache_query_hash', table_name='chatbot_cache')
    op.drop_table('chatbot_cache')