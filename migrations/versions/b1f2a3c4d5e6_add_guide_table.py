"""Add Guide table

Revision ID: b1f2a3c4d5e6
Revises: aa220b5ebf49
Create Date: 2026-02-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1f2a3c4d5e6'
down_revision = 'aa220b5ebf49'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('guide',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('city', sa.String(length=200), nullable=False),
    sa.Column('hotel_name', sa.String(length=300), nullable=False),
    sa.Column('hotel_lat', sa.Float(), nullable=False),
    sa.Column('hotel_lng', sa.Float(), nullable=False),
    sa.Column('date_start', sa.Date(), nullable=False),
    sa.Column('date_end', sa.Date(), nullable=False),
    sa.Column('num_days', sa.Integer(), nullable=False),
    sa.Column('flight_arrival', sa.String(length=10), nullable=True),
    sa.Column('flight_departure', sa.String(length=10), nullable=True),
    sa.Column('poi_data_json', sa.Text(), nullable=False),
    sa.Column('published_filename', sa.String(length=255), nullable=True),
    sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('guide')
