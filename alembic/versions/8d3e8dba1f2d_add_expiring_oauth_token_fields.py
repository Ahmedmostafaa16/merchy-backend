"""add expiring oauth token fields

Revision ID: 8d3e8dba1f2d
Revises: 4b41ae9b3c9f
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d3e8dba1f2d'
down_revision: Union[str, Sequence[str], None] = '4b41ae9b3c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('shops', sa.Column('access_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shops', sa.Column('refresh_token', sa.String(), nullable=True))
    op.add_column('shops', sa.Column('refresh_token_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('shops', 'refresh_token_expires_at')
    op.drop_column('shops', 'refresh_token')
    op.drop_column('shops', 'access_token_expires_at')
