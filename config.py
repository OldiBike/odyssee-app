# config.py
import os

class Config:
    """Configuration de l'application Flask."""
    
    # Clé secrète pour la sécurité des sessions
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'une-cle-secrete-par-defaut-vraiment-pas-sure'
    
    # --- LIGNES MODIFIÉES ---
    # Utilise la base de données de Railway et s'assure que l'URL est compatible.
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_url or 'sqlite:///app.db'
    # --- FIN DES MODIFICATIONS ---

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Clé API Google
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

    # Configuration pour l'envoi d'emails
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_SSL = str(os.environ.get('MAIL_PORT')) == '465'
    MAIL_USE_TLS = not MAIL_USE_SSL
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
