"""Add additional link status fields

Revision ID: 003
Revises: 002
Create Date: 2023-11-21 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add new columns to link_status table
    op.add_column('link_status', sa.Column('content_type', sa.String(), nullable=True))
    op.add_column('link_status', sa.Column('final_url', sa.String(), nullable=True))
    op.add_column('link_status', sa.Column('redirect_count', sa.Integer(), server_default='0'))
    op.add_column('link_status', sa.Column('error_message', sa.String(), nullable=True))
    op.add_column('link_status', sa.Column('check_method', sa.String(), server_default='HEAD'))

def downgrade() -> None:
    # Remove new columns from link_status table
    op.drop_column('link_status', 'check_method')
    op.drop_column('link_status', 'error_message')
    op.drop_column('link_status', 'redirect_count')
    op.drop_column('link_status', 'final_url')
    op.drop_column('link_status', 'content_type')