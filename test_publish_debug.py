#!/usr/bin/env python3
"""Script de débogage pour tester la publication d'un trip"""

from app import app, db
from models import Trip, User
import traceback
import json

def test_publish():
    with app.app_context():
        # Récupérer le trip ID 50 (celui mentionné dans l'erreur)
        trip = Trip.query.get(50)
        
        if not trip:
            print("❌ Trip 50 n'existe pas")
            return
        
        print(f"✅ Trip trouvé: {trip.hotel_name}")
        print(f"   User ID: {trip.user_id}")
        print(f"   Status: {trip.status}")
        
        # Tester l'accès à trip.user
        try:
            user = trip.user
            print(f"✅ User chargé: {user.pseudo if user else 'None'}")
        except Exception as e:
            print(f"❌ Erreur lors du chargement de user: {e}")
            traceback.print_exc()
        
        # Tester la publication
        try:
            from services import PublicationService
            publication_service = PublicationService(app.config)
            
            print("\n🔄 Test de publication...")
            filename = publication_service.publish_public_offer(trip)
            
            if filename:
                print(f"✅ Publication réussie: {filename}")
            else:
                print("❌ Publication échouée")
                
        except Exception as e:
            print(f"❌ Erreur lors de la publication: {e}")
            traceback.print_exc()

if __name__ == '__main__':
    test_publish()
