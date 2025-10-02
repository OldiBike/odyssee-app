import os
import requests
import json
import re
import base64
from datetime import datetime
import google.generativeai as genai
from bs4 import BeautifulSoup
import unidecode
import traceback

class PublicationService:
    def __init__(self, config):
        self.api_url = 'https://www.voyages-privileges.be/api/upload.php'
        self.download_api_url = 'https://www.voyages-privileges.be/api/download.php' 
        self.api_key = 'SecretUploadKey2025'
        print(f"📡 Configuration Publication: Mode API HTTP")

    def _prepare_payload(self, filename, content, directory, is_binary=False):
        """Prépare le payload JSON incluant la clé API."""
        if is_binary:
            content_base64 = base64.b64encode(content).decode('utf-8')
        else:
            content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        return {
            'api_key': self.api_key, # NOUVELLE FAÇON D'ENVOYER LA CLÉ
            'filename': filename,
            'content': content_base64,
            'directory': directory
        }

    def _upload_via_api(self, filename, content, directory, is_binary=False):
        try:
            print(f"📤 Upload via API: {filename} vers {directory}/")
            payload = self._prepare_payload(filename, content, directory, is_binary)
            
            headers = {'Content-Type': 'application/json'} # Plus besoin de X-Api-Key ici
            
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=45)
            
            print(f"   Réponse HTTP: {response.status_code}")
            if response.status_code == 200 and response.json().get('success'):
                print(f"✅ Upload réussi: {response.json().get('url', '')}")
                return True
            else:
                print(f"❌ Échec de l'upload: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Erreur critique lors de l'upload: {e}")
            traceback.print_exc()
            return False

    def upload_document(self, filename, file_content, trip_id):
        directory = f"documents/{trip_id}"
        return self._upload_via_api(filename, file_content, directory, is_binary=True)

    def download_document(self, filename, trip_id):
        # Le téléchargement nécessite une méthode différente car il utilise GET
        try:
            directory = f"documents/{trip_id}"
            params = {'filename': filename, 'directory': directory}
            headers = {'X-Api-Key': self.api_key} # GET ne peut pas avoir de body, on garde le header ici
            
            response = requests.get(self.download_api_url, params=params, headers=headers, timeout=45)
            
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            print(f"❌ Erreur critique de téléchargement: {e}")
            return None

    def _generate_base_filename(self, trip_data):
        hotel_name = trip_data['form_data']['hotel_name'].split(',')[0].strip()
        date_start = trip_data['form_data']['date_start']
        date_end = trip_data['form_data']['date_end']
        base_name = unidecode.unidecode(hotel_name).lower()
        base_name = re.sub(r'[^a-z0-9]+', '_', base_name).strip('_')
        return f"{base_name}_{date_start}_{date_end}"

    def publish_public_offer(self, trip):
        try:
            full_trip_data = json.loads(trip.full_data_json)
            base_filename = self._generate_base_filename(full_trip_data)
            filename = f"{base_filename}.html"
            html_content = generate_travel_page_html(
                full_trip_data['form_data'],
                full_trip_data['api_data'],
                full_trip_data.get('savings', 0),
                full_trip_data.get('comparison_total', 0)
            )
            if self._upload_via_api(filename, html_content, 'offres'):
                return filename
            return None
        except Exception as e:
            print(f"❌ Erreur dans publish_public_offer: {e}")
            return None

    def publish_client_offer(self, trip):
        try:
            full_trip_data = json.loads(trip.full_data_json)
            base_filename = self._generate_base_filename(full_trip_data)
            raw_name = f"{trip.client_first_name} {trip.client_last_name}"
            slug = unidecode.unidecode(raw_name).lower()
            slug = re.sub(r"[\s']+", '_', slug)
            client_name_slug = re.sub(r'[^a-z0-9_]', '', slug)
            filename = f"{base_filename}_{client_name_slug}.html"
            html_content = generate_travel_page_html(
                full_trip_data['form_data'],
                full_trip_data['api_data'],
                full_trip_data.get('savings', 0),
                full_trip_data.get('comparison_total', 0)
            )
            if self._upload_via_api(filename, html_content, 'clients'):
                return filename
            return None
        except Exception as e:
            print(f"❌ Erreur dans publish_client_offer: {e}")
            return None

    def unpublish(self, filename, is_client_offer=False):
        try:
            directory = 'clients' if is_client_offer else 'offres'
            payload = {
                'api_key': self.api_key, # NOUVELLE FAÇON
                'filename': filename,
                'directory': directory
            }
            headers = {'Content-Type': 'application/json'}
            response = requests.delete(self.api_url, json=payload, headers=headers, timeout=30)
            return response.status_code == 200 and response.json().get('success')
        except Exception as e:
            print(f"❌ Erreur suppression API: {e}")
            return False
    
    def test_connection(self):
        try:
            print("\n🔍 TEST DE CONNEXION API")
            # Le test GET ne fonctionne plus avec la nouvelle authentification,
            # nous faisons un test d'écriture directement.
            test_content = "test"
            test_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            directory = 'offres'
            filename = f'test_{test_timestamp}.html'
            
            print(f"\n📝 Test d'écriture dans {directory}/")
            if self._upload_via_api(filename, test_content, directory):
                print(f"   ✅ Écriture réussie")
                self.unpublish(filename, is_client_offer=False)
                print("\n✅ TEST RÉUSSI !")
                return True
            else:
                print(f"   ❌ Échec d'écriture.")
                return False
        except Exception as e:
            print(f"❌ Erreur test: {e}")
            return False

# ... LE RESTE DU FICHIER services.py (RealAPIGatherer, etc.) RESTE IDENTIQUE ...
# Assurez-vous de copier-coller le reste de votre fichier ici.

class RealAPIGatherer:
    def __init__(self):
        self.google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not self.google_api_key:
            print("❌ ERREUR CRITIQUE: Variable GOOGLE_API_KEY manquante")
        else:
            genai.configure(api_key=self.google_api_key)
            print("✅ Clé API Google chargée")

    def generate_whatsapp_catchphrase(self, trip_details):
        if not self.google_api_key:
            return "Une offre à ne pas manquer !"
        try:
            model = genai.GenerativeModel('models/gemini-1.5-pro-latest')
            prompt = (
                f"Crée une très courte phrase marketing (maximum 15 mots) pour une publication WhatsApp concernant un voyage. "
                f"Voici les détails : Hôtel '{trip_details['hotel_name']}' à {trip_details['destination']}. "
                f"Le but est de donner envie de cliquer sur le lien de l'offre. Sois percutant et inspirant. "
                f"Exemples : 'Le paradis vous attend à prix d'ami ! 🌴', 'Évadez-vous sous le soleil de {trip_details['destination']} à un tarif jamais vu !', "
                f"'Saisissez cette chance unique de découvrir {trip_details['hotel_name']} ! ✨'"
            )
            response = model.generate_content(prompt)
            clean_text = response.text.strip().replace('*', '').replace('"', '')
            return clean_text
        except Exception as e:
            print(f"❌ Erreur API Gemini (catchphrase): {e}")
            return "Découvrez notre offre exclusive pour cette destination de rêve !"
            
    def get_real_hotel_photos(self, hotel_name, destination):
        if not self.google_api_key: return []
        try:
            search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            search_params = {'query': f'"{hotel_name}" "{destination}" hotel', 'key': self.google_api_key, 'fields': 'photos,place_id'}
            search_response = requests.get(search_url, params=search_params, timeout=15)
            if search_response.status_code == 200 and (search_data := search_response.json()).get('results'):
                place_id = search_data['results'][0].get('place_id')
                details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                details_params = {'place_id': place_id, 'fields': 'photos', 'key': self.google_api_key}
                details_response = requests.get(details_url, params=details_params, timeout=15)
                if details_response.status_code == 200:
                    photos = details_response.json().get('result', {}).get('photos', [])
                    return [f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={p.get('photo_reference')}&key={self.google_api_key}" for p in photos if p.get('photo_reference')]
            return []
        except Exception as e:
            print(f"❌ Erreur API Photos: {e}")
            return []

    def get_real_hotel_reviews(self, hotel_name, destination):
        if not self.google_api_key: return {'reviews': [], 'rating': 0, 'total_reviews': 0}
        try:
            search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            search_params = {'query': f'"{hotel_name}" "{destination}" hotel', 'key': self.google_api_key}
            search_response = requests.get(search_url, params=search_params, timeout=15)
            if search_response.status_code == 200 and (search_data := search_response.json()).get('results'):
                place_id = search_data['results'][0].get('place_id')
                details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                details_params = {'place_id': place_id, 'fields': 'reviews,rating,user_ratings_total', 'key': self.google_api_key, 'language': 'fr'}
                details_response = requests.get(details_url, params=details_params, timeout=15)

                if details_response.status_code == 200 and (result := details_response.json().get('result', {})):
                    all_reviews = result.get('reviews', [])
                    sorted_reviews = sorted(all_reviews, key=lambda r: (r.get('rating', 0), r.get('time', 0)), reverse=True)
                    formatted_reviews = [
                        {
                            'rating': '⭐' * r.get('rating', 0), 
                            'author': r.get('author_name', 'Anonyme'), 
                            'text': r.get('text', '')[:400] + '...', 
                            'date': r.get('relative_time_description', '')
                        } 
                        for r in sorted_reviews if r.get('rating', 0) >= 4
                    ]
                    total_reviews_count = result.get('user_ratings_total', 0)
                    return {
                        'reviews': formatted_reviews, 
                        'rating': result.get('rating', 0), 
                        'total_reviews': total_reviews_count
                    }
            return {'reviews': [], 'rating': 0, 'total_reviews': 0}
        except Exception as e:
            print(f"❌ Erreur API Reviews: {e}")
            return {'reviews': [], 'rating': 0, 'total_reviews': 0}

    def get_real_youtube_videos(self, hotel_name, destination):
        if not self.google_api_key: return []
        try:
            youtube_url = "https://www.googleapis.com/youtube/v3/search"
            youtube_params = {'part': 'snippet', 'q': f'"{hotel_name}" "{destination}" hotel review tour', 'type': 'video', 'maxResults': 4, 'order': 'relevance', 'key': self.google_api_key}
            youtube_response = requests.get(youtube_url, params=youtube_params, timeout=15)
            if youtube_response.status_code == 200:
                return [{'id': item['id']['videoId'], 'title': item['snippet']['title']} for item in youtube_response.json().get('items', []) if item.get('id', {}).get('videoId')]
            return []
        except Exception as e:
            print(f"❌ Erreur API YouTube: {e}")
            return []

    def get_attraction_image(self, attraction_name, destination):
        if not self.google_api_key: return None
        print(f"ℹ️ Recherche d'une image réelle pour : {attraction_name} à {destination}")
        try:
            search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            search_params = {'query': f'"{attraction_name}" "{destination}"', 'key': self.google_api_key, 'fields': 'photos'}
            search_response = requests.get(search_url, params=search_params, timeout=15)
            if search_response.status_code == 200:
                search_data = search_response.json()
                if search_data.get('results') and search_data['results'][0].get('photos'):
                    photo_reference = search_data['results'][0]['photos'][0].get('photo_reference')
                    if photo_reference:
                        return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={photo_reference}&key={self.google_api_key}"
            return None
        except Exception as e:
            print(f"❌ Erreur API Image Attraction: {e}")
            return None

    def get_real_gemini_attractions_and_restaurants(self, destination):
        if not self.google_api_key:
            return {"attractions": [], "restaurants": []}
        try:
            model = genai.GenerativeModel('models/gemini-1.5-pro-latest')
            prompt = f'Donne-moi 8 points d\'intérêt pour {destination} et une sélection de 3 des meilleurs restaurants. Réponds UNIQUEMENT en JSON: {{"attractions": [{{"name": "Nom", "type": "plage|culture|gastronomie|activite"}}], "restaurants": [{{"name": "Nom du restaurant"}}]}}'
            response = model.generate_content(prompt)
            response_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            parsed_data = json.loads(response_text)
            return parsed_data
        except Exception as e:
            print(f"❌ Erreur API Gemini: {e}")
            return {"attractions": [], "restaurants": []}

    def gather_all_real_data(self, hotel_name, destination):
        gemini_data = self.get_real_gemini_attractions_and_restaurants(destination)
        attractions_list = gemini_data.get("attractions", [])
        restaurants_list = gemini_data.get("restaurants", [])
        
        attractions_by_category = {'plages': [], 'culture': [], 'gastronomie': [], 'activites': []}
        for attr in attractions_list:
            category = attr.get('type', 'activites').replace('activite', 'activites')
            if category in attractions_by_category:
                attractions_by_category[category].append(attr.get('name', ''))

        cultural_attraction_image = None
        if attractions_by_category.get('culture'):
            first_cultural_attraction = attractions_by_category['culture'][0]
            cultural_attraction_image = self.get_attraction_image(first_cultural_attraction, destination)

        reviews_data = self.get_real_hotel_reviews(hotel_name, destination)

        return {
            'photos': self.get_real_hotel_photos(hotel_name, destination),
            'reviews': reviews_data.get('reviews', []),
            'hotel_rating': reviews_data.get('rating', 0),
            'total_reviews': reviews_data.get('total_reviews', 0),
            'videos': self.get_real_youtube_videos(hotel_name, destination),
            'attractions': attractions_by_category,
            'restaurants': restaurants_list,
            'cultural_attraction_image': cultural_attraction_image
        }

def generate_travel_page_html(data, real_data, savings, comparison_total):
    # This function should be copied from your original services.py file
    # It is quite long, so I will add a placeholder.
    # Make sure to copy the entire 'generate_travel_page_html' function here.
    return "<html><body>Page de voyage générée</body></html>"
