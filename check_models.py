import os
import google.generativeai as genai

# Récupérer la clé depuis la variable d'environnement
api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    print("❌ ERREUR: La variable d'environnement GOOGLE_API_KEY n'est pas définie")
    print("Exécutez: export GOOGLE_API_KEY='clé Google'")
    exit(1)

try:
    genai.configure(api_key=api_key)  # ← Correction ici
    print("✅ Clé API configurée avec succès\n")
    print("--- Modèles disponibles pour la génération de contenu ---")
    
    models_found = False
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✓ {m.name}")
            models_found = True
    
    if not models_found:
        print("Aucun modèle trouvé")
        
except Exception as e:
    print(f"❌ Une erreur est survenue : {e}")
