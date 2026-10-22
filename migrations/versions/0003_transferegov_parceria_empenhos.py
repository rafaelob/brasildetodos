"""Add raw Transferegov Parcerias budget commitments.

Revision ID: 0003_transferegov_parceria_empenhos
Revises: 0002_transferegov_parcerias
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0003_transferegov_parceria_empenhos'
down_revision = '0002_transferegov_parcerias'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'transferegov_parceria_empenhos',
        sa.Column('key', sa.String(length=64), primary_key=True, nullable=False),
        sa.Column('id_empenho_parceria', sa.String(length=80), nullable=False),
        sa.Column('id_parceria', sa.String(length=80), nullable=False),
        sa.Column('nr_empenho', sa.Integer(), nullable=True),
        sa.Column('aa_empenho', sa.Integer(), nullable=True),
        sa.Column('data_emissao', sa.String(length=40), nullable=True),
        sa.Column('situacao_siafi', sa.String(length=200), nullable=True),
        sa.Column('favorecido_nome', sa.String(length=300), nullable=True),
        sa.Column('favorecido_id', sa.String(length=30), nullable=True),
        sa.Column('valor_empenho', sa.Float(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('source', sa.JSON(), nullable=False),
    )
    op.create_index('ix_transferegov_parceria_empenhos_id_empenho_parceria',
                    'transferegov_parceria_empenhos', ['id_empenho_parceria'])
    op.create_index('ix_transferegov_parceria_empenhos_id_parceria',
                    'transferegov_parceria_empenhos', ['id_parceria'])


def downgrade() -> None:
    op.drop_index('ix_transferegov_parceria_empenhos_id_parceria',
                  table_name='transferegov_parceria_empenhos')
    op.drop_index('ix_transferegov_parceria_empenhos_id_empenho_parceria',
                  table_name='transferegov_parceria_empenhos')
    op.drop_table('transferegov_parceria_empenhos')
