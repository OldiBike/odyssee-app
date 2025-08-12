# config.py
import os
# La ligne "from dotenv import load_dotenv" a été déplacée dans app.py
# La ligne "load_dotenv()" a été déplacée dans app.py

class Config:
    """Configuration de l'application Flask."""
    
    # Clé secrète pour la sécurité des sessions
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'une-cle-secrete-par-defaut-vraiment-pas-sure'
    
    # --- LIGNE MODIFIÉE ---
    # Utilise la base de données de Railway (PostgreSQL) si la variable DATABASE_URL existe,
    # sinon, utilise la base de données locale (SQLite) pour le développement.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Clé API Google
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

    # Configuration pour l'envoi d'emails
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')

    # Configuration Stripe
    STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

    # Configuration SFTP pour la publication
    FTP_HOSTNAME = os.environ.get('FTP_HOSTNAME')
    FTP_USERNAME = os.environ.get('FTP_USERNAME')
    FTP_PASSWORD = os.environ.get('FTP_PASSWORD')
    FTP_REMOTE_PATH = os.environ.get('FTP_REMOTE_PATH')
    
    # URLs
    SITE_PUBLIC_URL = os.environ.get('SITE_PUBLIC_URL')
    N8N_WHATSAPP_WEBHOOK = os.environ.get('N8N_WHATSAPP_WEBHOOK')
