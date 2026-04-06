"""add_tenant_id_to_clientes_y_objetivos

Revision ID: d31792657c5f
Revises: 9a07ccdca3aa
Create Date: 2026-03-19

Agrega tenant_id a clientes y objetivos_inversion para multi-tenant SaaS.
server_default='default' preserva todos los registros existentes sin pérdida de datos.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd31792657c5f'
down_revision = '9a07ccdca3aa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tabla clientes
    op.add_column('clientes',
        sa.Column('tenant_id', sa.String(200),
                  nullable=False, server_default='default'))
    op.create_index('ix_clientes_tenant_id', 'clientes', ['tenant_id'])

    # Tabla objetivos_inversion
    op.add_column('objetivos_inversion',
        sa.Column('tenant_id', sa.String(200),
                  nullable=False, server_default='default'))
    op.create_index('ix_objetivos_tenant_id', 'objetivos_inversion', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_objetivos_tenant_id', table_name='objetivos_inversion')
    op.drop_column('objetivos_inversion', 'tenant_id')
    op.drop_index('ix_clientes_tenant_id', table_name='clientes')
    op.drop_column('clientes', 'tenant_id')
