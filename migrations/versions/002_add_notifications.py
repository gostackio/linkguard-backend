"""Add notification settings and weekly reports

Revision ID: 002
Revises: 001
Create Date: 2023-11-21 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create user_notification_settings table
    op.create_table(
        'user_notification_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('broken_links', sa.Boolean(), nullable=False, default=True),
        sa.Column('status_changes', sa.Boolean(), nullable=False, default=True),
        sa.Column('weekly_report', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_user_notification_settings_id'), 'user_notification_settings', ['id'], unique=False)

    # Create weekly_reports table
    op.create_table(
        'weekly_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('total_links', sa.Integer(), nullable=False),
        sa.Column('healthy_links', sa.Integer(), nullable=False),
        sa.Column('broken_links', sa.Integer(), nullable=False),
        sa.Column('new_issues', sa.Integer(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_weekly_reports_id'), 'weekly_reports', ['id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_weekly_reports_id'), table_name='weekly_reports')
    op.drop_table('weekly_reports')
    op.drop_index(op.f('ix_user_notification_settings_id'), table_name='user_notification_settings')
    op.drop_table('user_notification_settings')