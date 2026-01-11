import smtplib
import os
from dotenv import load_dotenv

# Charger les variables du fichier .env
load_dotenv()

MAIL_SERVER = os.environ.get('MAIL_SERVER')
MAIL_PORT = int(os.environ.get('MAIL_PORT'))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

# Email de test
sender_email = MAIL_USERNAME
receiver_email = "damicosamuel@gmail.com" # Mettez votre propre email ici pour tester
message = """\
Subject: Test SMTP depuis Python

Ceci est un test de connexion au serveur SMTP de Hostinger."""

print(f"Tentative de connexion à {MAIL_SERVER} sur le port {MAIL_PORT}...")

try:
    if MAIL_PORT == 465:
        # Connexion SSL
        with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT) as server:
            server.set_debuglevel(1) # Affiche les logs détaillés
            print("Connexion SSL établie. Authentification...")
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            print("Authentification réussie. Envoi de l'email...")
            server.sendmail(sender_email, receiver_email, message)
            print("✅ Email de test envoyé avec succès !")
    else:
        # Connexion TLS
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.set_debuglevel(1) # Affiche les logs détaillés
            print("Connexion établie. Démarrage de TLS...")
            server.starttls()
            print("TLS démarré. Authentification...")
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            print("Authentification réussie. Envoi de l'email...")
            server.sendmail(sender_email, receiver_email, message)
            print("✅ Email de test envoyé avec succès !")

except Exception as e:
    print("\n❌ UNE ERREUR EST SURVENUE :")
    print(e) # Affiche l'erreur exacte