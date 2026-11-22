"""test de personnalité (Ennéagramme) : résultat enregistré sur le profil candidat

Revision ID: c4e8b2d71f30
Revises: a7c3e1f09b21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4e8b2d71f30'
down_revision = 'a7c3e1f09b21'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('candidate_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('personnalite', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('candidate_profiles', schema=None) as batch_op:
        batch_op.drop_column('personnalite')
