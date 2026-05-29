"""make chatbot user nullable

Revision ID: 9a7c4f1b2d3e
Revises: 
Create Date: 2026-05-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9a7c4f1b2d3e'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Make user_id nullable so anonymous sessions are allowed
    op.alter_column('chatbot_sessions', 'user_id', existing_type=sa.UUID(), nullable=True)


def downgrade():
    # Revert: make user_id NOT NULL again. WARNING: this will fail if any rows have NULL user_id.
    # Ensure you fill NULL user_id rows before running downgrade, or change this logic to set a guest id.
    op.alter_column('chatbot_sessions', 'user_id', existing_type=sa.UUID(), nullable=False)
