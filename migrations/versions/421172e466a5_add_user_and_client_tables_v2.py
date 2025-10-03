"""add_user_and_client_tables_v2

Revision ID: 421172e466a5
Revises: aa220b5ebf49
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa
from datetime import date
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '421172e466a5'
down_revision = 'aa220b5ebf49'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Créer la table user seulement si elle n'existe pas
    if 'user' not in existing_tables:
        op.create_table('user',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('username', sa.String(length=80), nullable=False),
            sa.Column('password', sa.String(length=120), nullable=False),
            sa.Column('pseudo', sa.String(length=80), nullable=False),
            sa.Column('email', sa.String(length=120), nullable=False),
            sa.Column('phone', sa.String(length=50), nullable=True),
            sa.Column('role', sa.String(length=20), nullable=False),
            sa.Column('margin_percentage', sa.Integer(), nullable=True),
            sa.Column('generation_count', sa.Integer(), nullable=True),
            sa.Column('last_generation_date', sa.Date(), nullable=True),
            sa.Column('daily_generation_limit', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('email'),
            sa.UniqueConstraint('username')
        )

    # Créer la table client seulement si elle n'existe pas
    if 'client' not in existing_tables:
        op.create_table('client',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('first_name', sa.String(length=100), nullable=False),
            sa.Column('last_name', sa.String(length=100), nullable=False),
            sa.Column('email', sa.String(length=120), nullable=True),
            sa.Column('phone', sa.String(length=50), nullable=True),
            sa.Column('address', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('email')
        )

    # Vérifier si un utilisateur par défaut existe
    result = conn.execute(sa.text("SELECT COUNT(*) FROM user WHERE username = 'default_user'"))
    if result.fetchone()[0] == 0:
        conn.execute(sa.text("""
            INSERT INTO user (username, password, pseudo, email, role, margin_percentage, generation_count, last_generation_date, daily_generation_limit)
            VALUES ('default_user', 'temp_password', 'Utilisateur par défaut', 'default@temp.com', 'admin', 80, 0, :today, 5)
        """), {"today": date.today()})
    
    # Récupérer l'ID de l'utilisateur par défaut
    result = conn.execute(sa.text("SELECT id FROM user WHERE username = 'default_user'"))
    default_user_id = result.fetchone()[0]

    # Vérifier si les colonnes user_id et client_id existent déjà dans trip
    trip_columns = [col['name'] for col in inspector.get_columns('trip')]
    
    # Ajouter les nouvelles colonnes seulement si elles n'existent pas
    with op.batch_alter_table('trip', schema=None) as batch_op:
        if 'user_id' not in trip_columns:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        if 'client_id' not in trip_columns:
            batch_op.add_column(sa.Column('client_id', sa.Integer(), nullable=True))
    
    # Remplir user_id pour tous les trips existants
    conn.execute(sa.text(f"UPDATE trip SET user_id = {default_user_id} WHERE user_id IS NULL"))
    
    # Maintenant rendre user_id NOT NULL, ajouter les foreign keys et supprimer les anciennes colonnes
    with op.batch_alter_table('trip', schema=None) as batch_op:
        batch_op.alter_column('user_id', nullable=False)
        
        # Vérifier si les foreign keys n'existent pas déjà
        existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('trip')]
        if 'fk_trip_client_id' not in existing_fks:
            batch_op.create_foreign_key('fk_trip_client_id', 'client', ['client_id'], ['id'])
        if 'fk_trip_user_id' not in existing_fks:
            batch_op.create_foreign_key('fk_trip_user_id', 'user', ['user_id'], ['id'])
        
        # Supprimer les anciennes colonnes seulement si elles existent
        if 'client_email' in trip_columns:
            batch_op.drop_column('client_email')
        if 'client_phone' in trip_columns:
            batch_op.drop_column('client_phone')
        if 'client_last_name' in trip_columns:
            batch_op.drop_column('client_last_name')
        if 'client_first_name' in trip_columns:
            batch_op.drop_column('client_first_name')


def downgrade():
    with op.batch_alter_table('trip', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_first_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('client_last_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('client_phone', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('client_email', sa.String(length=120), nullable=True))
        batch_op.drop_constraint('fk_trip_user_id', type_='foreignkey')
        batch_op.drop_constraint('fk_trip_client_id', type_='foreignkey')
        batch_op.drop_column('client_id')
        batch_op.drop_column('user_id')

    op.drop_table('client')
    op.drop_table('user')
