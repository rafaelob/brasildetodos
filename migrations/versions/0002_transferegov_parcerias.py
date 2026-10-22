"""Add the raw Transferegov Parcerias header table.

Revision ID: 0002_transferegov_parcerias
Revises: 0001_baseline
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0002_transferegov_parcerias'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'transferegov_parcerias',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('cd_parceria', sa.BigInteger(), nullable=True),
        sa.Column('id_proposta', sa.String(length=80), nullable=True),
        sa.Column('situacao', sa.String(length=80), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('source', sa.JSON(), nullable=False),
    )
    op.create_index('ix_transferegov_parcerias_cd_parceria',
                    'transferegov_parcerias', ['cd_parceria'])
    op.create_index('ix_transferegov_parcerias_id_proposta',
                    'transferegov_parcerias', ['id_proposta'])


def downgrade() -> None:
    op.drop_index('ix_transferegov_parcerias_id_proposta',
                  table_name='transferegov_parcerias')
    op.drop_index('ix_transferegov_parcerias_cd_parceria',
                  table_name='transferegov_parcerias')
    op.drop_table('transferegov_parcerias')
