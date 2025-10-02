#!/usr/bin/env python3
"""
Script de test direct pour la publication
À exécuter depuis votre Mac pour tester l'API
"""

import requests
import base64
import json
from datetime import datetime

# Configuration
API_URL = 'https://www.voyages-privileges.be/api/upload.php'
API_KEY = 'SecretUploadKey2025'

def test_connection():
    """Test de connexion basique"""
    print("=" * 50)
    print("TEST 1: Connexion à l'API")
    print("=" * 50)
    
    try:
        response = requests.get(
            API_URL,
            headers={'X-Api-Key': API_KEY},
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Connexion réussie!")
            return True
        else:
            print("❌ Erreur de connexion")
            return False
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def test_upload():
    """Test d'upload de fichier"""
    print("\n" + "=" * 50)
    print("TEST 2: Upload d'un fichier test")
    print("=" * 50)
    
    # Préparer le contenu HTML
    html_content = f"""
    <html>
    <head><title>Test Upload</title></head>
    <body>
        <h1>Test de publication</h1>
        <p>Généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body>
    </html>
    """
    
    # Encoder en base64
    content_base64 = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    
    # Préparer le payload
    payload = {
        'api_key': API_KEY,
        'filename': f'test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html',
        'content': content_base64,
        'directory': 'offres'
    }
    
    print(f"Filename: {payload['filename']}")
    print(f"Directory: {payload['directory']}")
    print(f"Content size: {len(html_content)} caractères")
    
    try:
        response = requests.post(
            API_URL,
            json=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Api-Key': API_KEY
            },
            timeout=30
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ Upload réussi!")
                print(f"URL: {data.get('url')}")
                return data.get('filename')
            else:
                print(f"❌ Upload échoué: {data.get('message')}")
                return None
        else:
            print("❌ Erreur HTTP")
            return None
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None

def test_delete(filename):
    """Test de suppression de fichier"""
    print("\n" + "=" * 50)
    print("TEST 3: Suppression du fichier test")
    print("=" * 50)
    
    if not filename:
        print("⚠️ Pas de fichier à supprimer")
        return False
    
    payload = {
        'api_key': API_KEY,
        'filename': filename,
        'directory': 'offres'
    }
    
    print(f"Suppression de: {filename}")
    
    try:
        response = requests.delete(
            API_URL,
            json=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Api-Key': API_KEY
            },
            timeout=30
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Suppression réussie!")
                return True
            else:
                print(f"❌ Suppression échouée: {data.get('message')}")
                return False
        else:
            print("❌ Erreur HTTP")
            return False
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def test_from_railway():
    """Test depuis l'application Railway"""
    print("\n" + "=" * 50)
    print("TEST 4: Test depuis Railway (si déployé)")
    print("=" * 50)
    
    # Remplacez par votre URL Railway
    railway_url = input("Entrez l'URL de votre app Railway (ex: https://odyssee.up.railway.app): ").strip()
    
    if not railway_url:
        print("⚠️ Test annulé")
        return
    
    try:
        # Test de connexion FTP depuis Railway
        response = requests.get(
            f"{railway_url}/test-ftp",
            timeout=30
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    print("🔧 TEST DE L'API DE PUBLICATION")
    print("================================\n")
    
    # Test 1: Connexion
    if test_connection():
        
        # Test 2: Upload
        filename = test_upload()
        
        if filename:
            # Test 3: Delete
            input("\n⏸️  Appuyez sur Entrée pour supprimer le fichier test...")
            test_delete(filename)
    
    # Test 4: Railway (optionnel)
    print("\n" + "=" * 50)
    test_railway = input("\nVoulez-vous tester depuis Railway? (o/n): ").lower()
    if test_railway == 'o':
        test_from_railway()
    
    print("\n✅ Tests terminés!")