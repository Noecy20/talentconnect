"""Tables renommées en français, pondérations par offre, modèles de message personnalisés,
mémoire des refus d'éligibilité des parrains

Revision ID: e5b7d2a94c10
Revises: c4e8b2d71f30
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5b7d2a94c10'
down_revision = 'c4e8b2d71f30'
branch_labels = None
depends_on = None

# ancien nom -> nouveau nom
TABLES = [
    ("users", "utilisateurs"),
    ("candidate_profiles", "profils_candidats"),
    ("companies", "entreprises"),
    ("recruiter_profiles", "profils_recruteurs"),
    ("sponsor_profiles", "profils_parrains"),
    ("sponsorship_requests", "demandes_parrainage"),
    ("sponsorships", "parrainages"),
    ("jobs", "offres"),
    ("applications", "candidatures"),
    ("talent_pool", "vivier"),
    ("message_templates", "modeles_messages"),
    ("plans", "formules"),
    ("payments", "paiements"),
    ("knowledge_docs", "documents_assistant"),
    ("chat_messages", "echanges_assistant"),
    ("settings", "parametres"),
    ("mobility_projects", "projets_mobilite"),
    ("cv_versions", "versions_cv"),
    ("tracked_applications", "suivi_candidatures"),
    ("tracker_events", "evenements_suivi"),
    ("stored_files", "fichiers"),
]


def _renommer(paires):
    bind = op.get_bind()
    existantes = set(sa.inspect(bind).get_table_names())
    postgres = bind.dialect.name == "postgresql"
    for ancien, nouveau in paires:
        if ancien not in existantes or nouveau in existantes:
            continue
        op.rename_table(ancien, nouveau)
        if postgres:
            # Index (ix_users_email -> ix_utilisateurs_email) et séquence de la clé primaire
            for (idx,) in bind.execute(sa.text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = :t AND indexname LIKE :p"),
                    {"t": nouveau, "p": f"ix_{ancien}_%"}).fetchall():
                op.execute(f'ALTER INDEX "{idx}" RENAME TO "ix_{nouveau}_{idx[len(ancien) + 4:]}"')
            seq = bind.execute(sa.text("SELECT to_regclass(:s)"), {"s": f"{ancien}_id_seq"}).scalar()
            if seq:
                op.execute(f'ALTER SEQUENCE "{ancien}_id_seq" RENAME TO "{nouveau}_id_seq"')


def upgrade():
    _renommer(TABLES)
    with op.batch_alter_table('offres', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ponderations', sa.JSON(), nullable=True))
    with op.batch_alter_table('modeles_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=120), nullable=True))
    op.create_table(
        'refus_parrains',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('empreinte', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_refus_parrains_empreinte', 'refus_parrains', ['empreinte'])


def downgrade():
    op.drop_index('ix_refus_parrains_empreinte', table_name='refus_parrains')
    op.drop_table('refus_parrains')
    with op.batch_alter_table('modeles_messages', schema=None) as batch_op:
        batch_op.drop_column('name')
    with op.batch_alter_table('offres', schema=None) as batch_op:
        batch_op.drop_column('ponderations')
    _renommer([(n, a) for a, n in TABLES])
