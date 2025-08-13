#!/usr/bin/env python
"""
Script d'initialisation de la base de données
À exécuter une seule fois après le déploiement sur Railway
"""
from app import create_app
from models import db

app = create_app()

with app.app_context():
    # Créer toutes les tables
    db.create_all()
    print("✅ Base de données initialisée avec succès!")
    
    # Afficher les tables créées
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"📊 Tables créées: {', '.join(tables)}")
