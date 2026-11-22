"""fichiers envoyés stockés en base

Revision ID: a7c3e1f09b21
Revises: 14d5d613dd5e
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c3e1f09b21'
down_revision = '14d5d613dd5e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stored_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('mimetype', sa.String(length=120), nullable=True),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stored_files_owner_id', 'stored_files', ['owner_id'])


def downgrade():
    op.drop_index('ix_stored_files_owner_id', table_name='stored_files')
    op.drop_table('stored_files')
