"""add usuarios y scores_historicos

Revision ID: a1b2c3d4e5f6
Revises: d31792657c5f
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "d31792657c5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("email", sa.String(200), unique=True, nullable=False),
        sa.Column("tier", sa.String(20), default="inversor"),
        sa.Column("tenant_id", sa.String(200), nullable=False, default="default"),
        sa.Column("hashed_password", sa.String(200)),
        sa.Column("activo", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_table(
        "scores_historicos",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("score_tecnico", sa.Float),
        sa.Column("score_fundamental", sa.Float),
        sa.Column("score_total", sa.Float),
    )


def downgrade() -> None:
    op.drop_table("scores_historicos")
    op.drop_table("usuarios")
