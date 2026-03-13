"""add_portal_token_to_client

Revision ID: 98415662e024
Revises: b1f2a3c4d5e6
Create Date: 2026-03-13 19:41:19.765568

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '98415662e024'
down_revision = 'b1f2a3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('client', schema=None) as batch_op:
        batch_op.add_column(sa.Column('portal_token', sa.String(length=36), nullable=True))
        batch_op.create_unique_constraint('uq_client_portal_token', ['portal_token'])


def downgrade():
    with op.batch_alter_table('client', schema=None) as batch_op:
        batch_op.drop_constraint('uq_client_portal_token', type_='unique')
        batch_op.drop_column('portal_token')
