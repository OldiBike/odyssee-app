# services.py - Version finale, fusionnée et corrigée
import os
import requests
import json
import re
import base64
from datetime import datetime
import google.generativeai as genai
from bs4 import BeautifulSoup
import unidecode

class PublicationService:
    """Gère la publication (upload, suppression) des fiches de voyage."""
    def __init__(self, config):
        self.api_url = config.get('UPLOAD_API_URL') or os.environ.get('UPLOAD_API_URL', 'https://www.voyages-privileges.be/api/upload.php')
        self.api_key = config.get('UPLOAD_API_KEY') or os.environ.get('UPLOAD_API_KEY', 'SecretUploadKey2025')
        
        print(f"📡 Configuration Publication:")
        print(f"   Mode: API HTTP (Railway compatible)")
        print(f"   API URL: {self.api_url}")
        print(f"   API Key: {self.api_key[:10]}... (tronquée pour sécurité)")

    def _upload_via_api(self, filename, content_bytes, directory, max_retries=3):
        """Méthode unifiée pour uploader des fichiers via l'API de publication."""
        import time
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt  # Backoff exponentiel: 2s, 4s, 8s
                    print(f"⏳ Tentative {attempt + 1}/{max_retries} après {wait_time}s de pause...")
                    time.sleep(wait_time)
                else:
                    print(f"📤 Upload via API: {filename} vers {directory}/")
                
                content_base64 = base64.b64encode(content_bytes).decode('utf-8')
                size_kb = len(content_bytes) / 1024
                print(f"   Taille: {size_kb:.2f} KB")
                
                payload = {
                    'filename': filename,
                    'content': content_base64,
                    'directory': directory
                }
                
                headers = {
                    'Content-Type': 'application/json',
                    'X-Api-Key': self.api_key 
                }
                
                response = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=60  # Augmenté à 60s pour les gros fichiers
                )
                
                if response.status_code == 200 and response.json().get('success'):
                    result = response.json()
                    print(f"✅ Upload réussi: {result.get('url', '')}")
                    return True
                elif response.status_code == 508:
                    # Erreur 508 = Ressources insuffisantes, on peut réessayer
                    print(f"⚠️ Serveur surchargé (HTTP 508), tentative {attempt + 1}/{max_retries}")
                    if attempt == max_retries - 1:
                        print(f"❌ Échec après {max_retries} tentatives: Serveur toujours surchargé")
                        return False
                    continue  # Réessayer
                else:
                    print(f"❌ Erreur API (HTTP {response.status_code}): {response.text[:200]}")
                    return False
                    
            except requests.exceptions.Timeout:
                print(f"⚠️ Timeout lors de l'upload (tentative {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    print(f"❌ Échec après {max_retries} tentatives: Timeout")
                    return False
                continue  # Réessayer
            except Exception as e:
                print(f"❌ Erreur critique lors de l'upload: {e}")
                return False
        
        return False

    def upload_document(self, filename, file_content_bytes, trip_id):
        """Téléverse un document (PDF, etc.) dans un sous-dossier spécifique au voyage."""
        directory = f"documents/{trip_id}"
        return self._upload_via_api(filename, file_content_bytes, directory)

    def download_document(self, filename, trip_id):
        """Télécharge un document depuis le serveur."""
        try:
            url = f"https://www.voyages-privileges.be/documents/{trip_id}/{filename}"
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                return response.content
            print(f"❌ Document non trouvé (HTTP {response.status_code}): {url}")
            return None
        except Exception as e:
            print(f"❌ Erreur de téléchargement du document: {e}")
            return None

    def _generate_base_filename(self, trip_data):
        """Génère un nom de fichier standardisé basé sur l'hôtel et les dates."""
        form_data = trip_data.get('form_data', {})
        hotel_name = form_data.get('hotel_name', 'voyage').split(',')[0].strip()
        date_start = form_data.get('date_start', 'nodate')
        date_end = form_data.get('date_end', 'nodate')
        base_name = unidecode.unidecode(hotel_name).lower()
        base_name = re.sub(r'[^a-z0-9]+', '_', base_name).strip('_')
        return f"{base_name}_{date_start}_{date_end}"

    def publish_public_offer(self, trip):
        """Publie une offre dans le dossier public /offres/."""
        try:
            print(f"📤 Publication publique du trip {trip.id}")
            print(f"   Hotel: {trip.hotel_name}")
            print(f"   User ID: {trip.user_id}")
            
            # Vérifier que le user existe
            creator_pseudo = None
            if trip.user:
                creator_pseudo = trip.user.pseudo
                print(f"   Creator pseudo: {creator_pseudo}")
            else:
                print(f"⚠️ ATTENTION: User {trip.user_id} introuvable pour trip {trip.id}, publication sans pseudo")
            
            full_trip_data = json.loads(trip.full_data_json)
            
            # Validation des données requises
            if 'form_data' not in full_trip_data:
                raise ValueError(f"Données manquantes: 'form_data' absent dans full_data_json")
            if 'api_data' not in full_trip_data:
                raise ValueError(f"Données manquantes: 'api_data' absent dans full_data_json")
            
            # Recalculer savings en fonction du mode de tarification
            form_data = full_trip_data['form_data']
            pack_price = int(form_data.get('pack_price') or 0)
            pricing_mode = form_data.get('pricing_mode', 'classic')
            
            if pricing_mode == 'pack':
                comparison_total = int(form_data.get('pack_competitor_price') or 0)
            else:
                hotel_b2c_price = int(form_data.get('hotel_b2c_price') or 0)
                flight_price = int(form_data.get('flight_price') or 0)
                transfer_cost = int(form_data.get('transfer_cost') or 0)
                surcharge_cost = int(form_data.get('surcharge_cost') or 0)
                car_rental_cost = int(form_data.get('car_rental_cost') or 0)
                comparison_total = hotel_b2c_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
            
            savings = comparison_total - pack_price
            
            print(f"   Génération du HTML...")
            html_content = generate_travel_page_html(
                full_trip_data['form_data'],
                full_trip_data['api_data'],
                savings,
                comparison_total,
                creator_pseudo=creator_pseudo
            )
            base_filename = self._generate_base_filename(full_trip_data)
            filename = f"{base_filename}.html"
            
            print(f"   Filename généré: {filename}")
            
            if self._upload_via_api(filename, html_content.encode('utf-8'), 'offres'):
                print(f"✅ Publication publique réussie: {filename}")
                return filename
            else:
                print(f"❌ Échec de l'upload API pour {filename}")
                return None
        except Exception as e:
            print(f"❌ ERREUR dans publish_public_offer: {e}")
            import traceback
            traceback.print_exc()
            return None

    def publish_client_offer(self, trip):
        """Publie une offre privée dans le dossier /clients/."""
        try:
            print(f"📤 Publication client du trip {trip.id}")
            
            # Vérifier que le user existe
            creator_pseudo = None
            if trip.user:
                creator_pseudo = trip.user.pseudo
                print(f"   Creator pseudo: {creator_pseudo}")
            else:
                print(f"⚠️ ATTENTION: User {trip.user_id} introuvable pour trip {trip.id}")
            
            full_trip_data = json.loads(trip.full_data_json)
            base_filename = self._generate_base_filename(full_trip_data)
            
            # Recalculer savings en fonction du mode de tarification
            form_data = full_trip_data['form_data']
            pack_price = int(form_data.get('pack_price') or 0)
            pricing_mode = form_data.get('pricing_mode', 'classic')
            
            if pricing_mode == 'pack':
                comparison_total = int(form_data.get('pack_competitor_price') or 0)
            else:
                hotel_b2c_price = int(form_data.get('hotel_b2c_price') or 0)
                flight_price = int(form_data.get('flight_price') or 0)
                transfer_cost = int(form_data.get('transfer_cost') or 0)
                surcharge_cost = int(form_data.get('surcharge_cost') or 0)
                car_rental_cost = int(form_data.get('car_rental_cost') or 0)
                comparison_total = hotel_b2c_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
            
            savings = comparison_total - pack_price
            
            raw_name = f"{trip.client.first_name} {trip.client.last_name}"
            slug = unidecode.unidecode(raw_name).lower()
            slug = re.sub(r"[\s']+", '_', slug)
            client_name_slug = re.sub(r'[^a-z0-9_]', '', slug)
            filename = f"{base_filename}_{client_name_slug}.html"
            
            html_content = generate_travel_page_html(
                full_trip_data['form_data'],
                full_trip_data['api_data'],
                savings,
                comparison_total,
                creator_pseudo=creator_pseudo
            )
            
            if self._upload_via_api(filename, html_content.encode('utf-8'), 'clients'):
                print(f"✅ Publication client réussie: {filename}")
                return filename
            else:
                print(f"❌ Échec de l'upload API pour {filename}")
                return None
        except Exception as e:
            print(f"❌ ERREUR dans publish_client_offer: {e}")
            import traceback
            traceback.print_exc()
            return None

    def unpublish(self, filename, is_client_offer=False):
        """Supprime un fichier publié via l'API."""
        try:
            directory = 'clients' if is_client_offer else 'offres'
            print(f"🗑️ Suppression via API: {filename} dans {directory}/")
            
            payload = { 'filename': filename, 'directory': directory }
            headers = { 'Content-Type': 'application/json', 'X-Api-Key': self.api_key }
            
            response = requests.delete(self.api_url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200 and response.json().get('success'):
                print(f"✅ Suppression réussie: {filename}")
                return True
            print(f"❌ Erreur suppression (HTTP {response.status_code}): {response.text}")
            return False
        except Exception as e:
            print(f"❌ Erreur critique lors de la suppression: {e}")
            return False
    
    def test_connection(self):
        """Test de connexion à l'API de publication."""
        try:
            print("\n🔍 TEST DE CONNEXION API")
            headers = {'X-Api-Key': self.api_key}
            response = requests.get(self.api_url, headers=headers, timeout=10)
            if response.status_code == 200 and response.json().get('success'):
                result = response.json()
                print(f"✅ API connectée: {result.get('message')}")
                return True
            else:
                print(f"❌ Erreur connexion API (HTTP {response.status_code}): {response.text}")
                return False
        except Exception as e:
            print(f"❌ Erreur critique pendant le test: {e}")
            return False

class RealAPIGatherer:
    """Récupère les données réelles depuis les APIs de Google (Maps, Gemini, YouTube)."""
    def __init__(self):
        self.google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not self.google_api_key:
            print("❌ ERREUR CRITIQUE: Variable GOOGLE_API_KEY manquante")
        else:
            genai.configure(api_key=self.google_api_key)
            print("✅ Clé API Google chargée et configurée")

    def generate_whatsapp_catchphrase(self, trip_details):
        if not self.google_api_key:
            return "Une offre à ne pas manquer !"
        try:
            model = genai.GenerativeModel('models/gemini-2.5-flash')
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
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            prompt = f'Donne-moi 8 points d\'intérêt pour {destination} et une sélection de 3 des meilleurs restaurants. Réponds UNIQUEMENT en JSON: {{"attractions": [{{"name": "Nom", "type": "plage|culture|gastronomie|activite"}}], "restaurants": [{{"name": "Nom du restaurant"}}]}}'
            response = model.generate_content(prompt)
            response_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            parsed_data = json.loads(response_text)
            return parsed_data
        except Exception as e:
            print(f"❌ Erreur API Gemini: {e}")
            return {"attractions": [], "restaurants": []}

    def generate_event_details_with_ai(self, event_description, destination):
        """
        Génère une description d'événement enrichie et trouve des images pertinentes
        en utilisant Gemini et Google Places API.
        """
        if not self.google_api_key:
            return event_description, [] # Fallback if API key is missing

        # 1. Refine description using Gemini
        new_description = event_description
        try:
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            
            # Si pas de description fournie, utiliser la destination
            base_text = event_description if event_description else f"événement à {destination}"
            
            prompt = f"""Tu es un rédacteur marketing spécialisé dans le tourisme. 
            
Ta mission : Transformer cette courte mention d'événement en une description captivante et vendeuse.

Événement d'origine : "{base_text}"
Destination : {destination}

Consignes STRICTES :
1. Crée une NOUVELLE description complètement différente et plus détaillée
2. Ajoute des adjectifs évocateurs (magique, authentique, inoubliable, enchanteur...)
3. Mentionne ce qu'on peut y voir, faire ou ressentir
4. Ajoute 2-3 émojis pertinents
5. Entre 40 et 60 mots
6. Style enthousiaste qui donne envie

IMPORTANT : Ne répète PAS simplement le texte d'origine. Enrichis-le vraiment !

Exemple de transformation :
AVANT : "Marché de Noël de Sofia"
APRÈS : "✨ Plongez dans l'atmosphère féerique du marché de Noël de Sofia ! Dégustez les spécialités bulgares traditionnelles, admirez l'artisanat local et laissez-vous envoûter par les illuminations scintillantes. Une expérience authentique et chaleureuse au cœur de la capitale bulgare ! 🎄"

Maintenant à toi, écris UNIQUEMENT la nouvelle description (sans guillemets, sans astérisques) :"""
            
            response = model.generate_content(prompt)
            raw_text = response.text
            print(f"📝 Prompt envoyé à Gemini:")
            print(f"   Base text: {base_text}")
            print(f"   Destination: {destination}")
            print(f"✅ Gemini raw response: {raw_text}")
            
            # Nettoyage plus agressif de la réponse
            new_description = raw_text.strip()
            new_description = new_description.replace('*', '').replace('**', '')
            new_description = new_description.replace('"', '').replace("'", "'")
            new_description = new_description.replace('```', '')
            new_description = new_description.strip()
            
            print(f"✅ Gemini cleaned response: {new_description}")
            print(f"🔍 Comparaison: '{new_description.lower().strip()}' vs '{base_text.lower().strip()}'")
            
            # Vérifier si la description a vraiment changé (comparaison plus robuste)
            if new_description.lower().strip() == base_text.lower().strip() or len(new_description) < len(base_text) + 10:
                print("⚠️ ATTENTION: Gemini a renvoyé la même description ou une description trop courte, utilisation du fallback")
                new_description = f"✨ Découvrez {base_text} à {destination} ! Une expérience unique et authentique vous attend. Ne manquez pas cette occasion exceptionnelle de vivre des moments inoubliables ! 🎉"
                print(f"✅ Fallback appliqué: {new_description}")
        except Exception as e:
            print(f"❌ Erreur API Gemini (refine event description): {e}")
            # Fallback to original description if AI fails

        # 2. Find images using Google Places API
        image_urls = []
        # Utiliser la description ORIGINALE pour la recherche, pas la version enrichie
        search_query = f"{event_description} {destination}" if event_description else f"événement {destination}"
        try:
            search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            search_params = {
                'query': search_query,
                'key': self.google_api_key,
                'fields': 'photos' # Request photos directly
            }
            search_response = requests.get(search_url, params=search_params, timeout=15)
            if search_response.status_code == 200 and (search_data := search_response.json()).get('results'):
                for result in search_data['results']:
                    if photos := result.get('photos'):
                        for p in photos:
                            if p_ref := p.get('photo_reference'):
                                image_urls.append(f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={p_ref}&key={self.google_api_key}")
                                if len(image_urls) >= 5: break # Limit to 5 images
                    if len(image_urls) >= 5: break
        except Exception as e:
            print(f"❌ Erreur API Photos (event generation): {e}")

        return new_description, image_urls[:5] # Ensure max 5 images

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
             if attractions_by_category['culture']: # S'assurer que la liste n'est pas vide
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

def generate_travel_page_html(data, real_data, savings, comparison_total, creator_pseudo=None):
    """Génère le contenu HTML complet de la page de voyage."""
    
    # Dictionnaire pour traduire les mois en français
    mois_fr = {
        'January': 'janvier', 'February': 'février', 'March': 'mars', 'April': 'avril',
        'May': 'mai', 'June': 'juin', 'July': 'juillet', 'August': 'août',
        'September': 'septembre', 'October': 'octobre', 'November': 'novembre', 'December': 'décembre'
    }
    
    hotel_name_full = data.get('hotel_name', '')
    hotel_name_parts = hotel_name_full.split(',')
    display_hotel_name = hotel_name_parts[0].strip()
    display_hotel_name_js = display_hotel_name.replace("'", "\\'")
    display_address = ', '.join(hotel_name_parts[1:]).strip() if len(hotel_name_parts) > 1 else data.get('destination', '')

    # Formater les dates en français
    date_start_obj = datetime.strptime(data['date_start'], '%Y-%m-%d')
    date_start_en = date_start_obj.strftime('%d %B %Y')
    date_start = date_start_en
    for eng, fr in mois_fr.items():
        date_start = date_start.replace(eng, fr)
    
    date_end_obj = datetime.strptime(data['date_end'], '%Y-%m-%d')
    date_end_en = date_end_obj.strftime('%d %B %Y')
    date_end = date_end_en
    for eng, fr in mois_fr.items():
        date_end = date_end.replace(eng, fr)
    stars = "⭐" * int(data.get('stars') or 0)
    num_people = int(data.get('num_people') or 2)
    num_children = int(data.get('num_children') or 0)
    
    # Construction du texte pour le nombre de personnes/enfants
    if num_children > 0:
        people_text = f"{num_people} personne{'s' if num_people > 1 else ''}"
        children_text = f"{num_children} enfant{'s' if num_children > 1 else ''}"
        price_for_text = f"pour {people_text} + {children_text}"
    else:
        price_for_text = f"pour {num_people} personnes" if num_people > 1 else "pour 1 personne"
    
    your_price = int(data.get('pack_price') or 0)
    # N'afficher le prix par personne que s'il n'y a pas d'enfants
    price_per_person_text = ''
    if num_children == 0 and num_people > 0:
        price_per_person_text = f'<p class="text-sm font-light mt-1">soit {round(your_price / num_people)} € par personne</p>'
    is_ultra_budget = data.get('is_ultra_budget', False)
    cancellation_html = ""
    flight_price = int(data.get('flight_price') or 0)
    
    # Récupérer les détails des vols
    departure_city = data.get('departure_city', '').split(',')[0] if data.get('departure_city') else ''
    arrival_airport = data.get('arrival_airport', '').split(',')[0] if data.get('arrival_airport') else data.get('destination', '').split(',')[0]
    
    # Vol Aller
    outbound_departure = data.get('outbound_departure_time', '09:00')
    outbound_arrival = data.get('outbound_arrival_time', '12:00')
    outbound_has_layover = data.get('outbound_has_layover') == 'on'
    outbound_layover_airport = data.get('outbound_layover_airport', '').split(',')[0] if data.get('outbound_layover_airport') else ''
    outbound_layover_duration = data.get('outbound_layover_duration', '')
    outbound_leg1_dep = data.get('outbound_leg1_departure', '')
    outbound_leg1_arr = data.get('outbound_leg1_arrival', '')
    outbound_leg2_dep = data.get('outbound_leg2_departure', '')
    outbound_leg2_arr = data.get('outbound_leg2_arrival', '')
    
    # Vol Retour
    return_departure = data.get('return_departure_time', '14:00')
    return_arrival = data.get('return_arrival_time', '18:00')
    return_has_layover = data.get('return_has_layover') == 'on'
    return_layover_airport = data.get('return_layover_airport', '').split(',')[0] if data.get('return_layover_airport') else ''
    return_layover_duration = data.get('return_layover_duration', '')
    return_leg1_dep = data.get('return_leg1_departure', '')
    return_leg1_arr = data.get('return_leg1_arrival', '')
    return_leg2_dep = data.get('return_leg2_departure', '')
    return_leg2_arr = data.get('return_leg2_arrival', '')
    
    # Générer le bloc Vos Vols
    flights_block_html = ''
    if departure_city and arrival_airport:
        # Vol Aller
        if outbound_has_layover and outbound_layover_airport:
            outbound_html = f'''<div style="margin-bottom: 15px;"><div style="font-weight: 600; color: #0369a1; margin-bottom: 8px;">📍 ALLER - {date_start}</div><div style="font-size: 14px; color: #475569;"><div style="margin-bottom: 5px;"><strong>{departure_city}</strong> → <strong>{outbound_layover_airport}</strong></div><div style="color: #64748b; font-size: 12px;">{outbound_leg1_dep} → {outbound_leg1_arr}</div><div style="background: #f1f5f9; padding: 5px 10px; margin: 5px 0; border-radius: 4px; font-size: 12px;">⏱️ Escale {outbound_layover_duration} à {outbound_layover_airport}</div><div style="margin-bottom: 5px;"><strong>{outbound_layover_airport}</strong> → <strong>{arrival_airport}</strong></div><div style="color: #64748b; font-size: 12px;">{outbound_leg2_dep} → {outbound_leg2_arr}</div></div></div>'''
        else:
            outbound_html = f'''<div style="margin-bottom: 15px;"><div style="font-weight: 600; color: #0369a1; margin-bottom: 8px;">📍 ALLER - {date_start}</div><div style="display: flex; align-items: center; gap: 10px;"><span style="font-weight: 600;">{departure_city}</span><span style="color: #64748b;">→</span><span style="font-weight: 600;">{arrival_airport}</span></div><div style="color: #64748b; font-size: 13px;">{outbound_departure} → {outbound_arrival}</div></div>'''
        
        # Vol Retour
        if return_has_layover and return_layover_airport:
            return_html = f'''<div><div style="font-weight: 600; color: #b45309; margin-bottom: 8px;">📍 RETOUR - {date_end}</div><div style="font-size: 14px; color: #475569;"><div style="margin-bottom: 5px;"><strong>{arrival_airport}</strong> → <strong>{return_layover_airport}</strong></div><div style="color: #64748b; font-size: 12px;">{return_leg1_dep} → {return_leg1_arr}</div><div style="background: #fef3c7; padding: 5px 10px; margin: 5px 0; border-radius: 4px; font-size: 12px;">⏱️ Escale {return_layover_duration} à {return_layover_airport}</div><div style="margin-bottom: 5px;"><strong>{return_layover_airport}</strong> → <strong>{departure_city}</strong></div><div style="color: #64748b; font-size: 12px;">{return_leg2_dep} → {return_leg2_arr}</div></div></div>'''
        else:
            return_html = f'''<div><div style="font-weight: 600; color: #b45309; margin-bottom: 8px;">📍 RETOUR - {date_end}</div><div style="display: flex; align-items: center; gap: 10px;"><span style="font-weight: 600;">{arrival_airport}</span><span style="color: #64748b;">→</span><span style="font-weight: 600;">{departure_city}</span></div><div style="color: #64748b; font-size: 13px;">{return_departure} → {return_arrival}</div></div>'''
        
        flights_block_html = f'<div class="instagram-card p-6"><h3 class="section-title text-xl mb-4">✈️ Vos Vols</h3>{outbound_html}<hr style="border: none; border-top: 1px solid #e2e8f0; margin: 15px 0;">{return_html}</div>'
    
    # Texte de la route du vol (pour backward compatibility)
    flight_route_text = f'Vol {departure_city} ↔ {arrival_airport}' if departure_city and arrival_airport else ''
    flight_times_description = ""
    if data.get('has_cancellation') == 'on' and data.get('cancellation_date'):
        if flight_price > 0:
            cancellation_html = f"""
            <p class="text-xs font-light mt-1 text-center">✓ Annulation gratuite de l'hôtel jusqu'au {data.get("cancellation_date")}</p>
            <p class="text-xs font-bold text-orange-800 mt-1 text-center">Les vols ({flight_price} €) ne sont pas remboursables.</p>
            """
        else:
            cancellation_html = f'<p class="text-xs font-light mt-1 text-center">✓ Annulation gratuite jusqu\'au {data.get("cancellation_date")}</p>'

    instagram_button_html = ""
    instagram_input = data.get('instagram_handle', '').strip()
    if instagram_input:
        match = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([A-Za-z0-9_.-]+)', instagram_input)
        username = match.group(1) if match else instagram_input.lstrip('@')
        if username:
            instagram_url = f"https://www.instagram.com/{username}"
            instagram_button_html = f'''
            <a href="{instagram_url}" target="_blank" class="block bg-gradient-to-r from-purple-500 via-pink-500 to-red-500 hover:opacity-90 text-white font-bold py-3 px-6 rounded-full text-center" style="display: inline-flex; align-items: center; justify-content: center; gap: 8px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M8 0C5.829 0 5.556.01 4.703.048 3.85.088 3.269.222 2.76.42a3.9 3.9 0 0 0-1.417.923A3.9 3.9 0 0 0 .42 2.76C.222 3.268.087 3.85.048 4.703.01 5.555 0 5.827 0 8s.01 2.444.048 3.297c.04.852.174 1.433.372 1.942.205.526.478.972.923 1.417.444.445.89.719 1.416.923.51.198 1.09.333 1.942.372C5.555 15.99 5.827 16 8 16s2.444-.01 3.297-.048c.852-.04 1.433-.174 1.942-.372.526-.205.972-.478 1.417-.923.445-.444.718-.891.923-1.417.198-.51.333-1.09.372-1.942C15.99 10.445 16 10.173 16 8s-.01-2.444-.048-3.297c-.04-.852-.174-1.433-.372-1.942a3.9 3.9 0 0 0-.923-1.417A3.9 3.9 0 0 0 13.24.42c-.51-.198-1.09-.333-1.942-.372C10.445.01 10.173 0 8 0M8 4.865a3.135 3.135 0 1 0 0 6.27 3.135 3.135 0 0 0 0-6.27m0 5.143a2.008 2.008 0 1 1 0-4.016 2.008 2.008 0 0 1 0 4.016m6.406-4.848a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5"/></svg>
                Voir sur Instagram
            </a>
            '''

    city_name = data.get('destination', '').split(',')[0].strip()
    exclusive_services_html = f'<div class="p-4 mt-4 rounded-lg border-2 border-blue-200 bg-blue-50"><h4 class="font-bold text-blue-800 mb-2">Nos Services additionnels offerts</h4><p class="text-sm text-gray-700">{data.get("exclusive_services", "").strip().replace(chr(10), "<br>")}</p></div>' if data.get('exclusive_services', '').strip() else ""

    flight_text_html = f'<div class="flex justify-between"><span>{flight_route_text}</span><span class="font-semibold">{flight_price}€</span></div>' if flight_price > 0 else ""
    flight_inclusion_html = f'<div class="flex items-center"><div class="feature-icon bg-blue-500"><i class="fas fa-plane"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">{flight_route_text}</h4><p class="text-gray-600 text-xs">Aller-retour inclus{flight_times_description}</p></div></div>' if flight_price > 0 else ""

    baggage_option = data.get('baggage_type', 'bagages 10 kilos')
    baggage_inclusion_html = ''
    if is_ultra_budget and baggage_option == 'Pas de bagages':
        baggage_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-gray-400"><i class="fas fa-suitcase"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Bagages à main uniquement</h4><p class="text-gray-600 text-xs">Pas de bagages cabine</p></div></div>'
    elif baggage_option == 'bagages 10 kilos':
        baggage_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-red-500"><i class="fas fa-suitcase"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Bagage 10 kilos</h4><p class="text-gray-600 text-xs">1 bagage inclus par personne en cabine</p></div></div>'
    elif baggage_option == 'Bagage 20 kilos':
        baggage_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-red-500"><i class="fas fa-suitcase-rolling"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Bagage 20 kilos</h4><p class="text-gray-600 text-xs">1 bagage en soute inclus par personne</p></div></div>'
    elif baggage_option == 'bagages 10 kilos + 1x 20 kilos':
        baggage_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-red-500"><i class="fas fa-suitcase-rolling"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Bagages 10 kilos + 1x 20 kilos</h4><p class="text-gray-600 text-xs">1 bagage 10 kilos inclus par personne en cabine et un bagage 20 kilo en soute</p></div></div>'
    elif baggage_option == 'Pas de bagages':
        baggage_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-gray-400"><i class="fas fa-suitcase"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Pas de bagages</h4><p class="text-gray-600 text-xs">Peuvent être ajouté en option</p></div></div>'

    transfer_cost = int(data.get('transfer_cost') or 0)
    transfer_text_html = f'<div class="flex justify-between"><span>+ Transferts</span><span class="font-semibold">~{transfer_cost}€</span></div>' if transfer_cost > 0 else ""
    transfer_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-green-500"><i class="fas fa-bus"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Transfert aéroport ↔ hôtel</h4><p class="text-gray-600 text-xs">Prise en charge complète</p></div></div>' if transfer_cost > 0 else ""

    surcharge_cost = int(data.get('surcharge_cost') or 0)
    surcharge_text_html = f'<div class="flex justify-between"><span>+ Surcoût {data.get("surcharge_type", "")}</span><span class="font-semibold">~{surcharge_cost}€</span></div>' if surcharge_cost > 0 else ""
    
    pension_html = ''
    if data.get('surcharge_type') != 'Logement seul':
        pension_html = f'<div class="flex items-center"><div class="feature-icon bg-yellow-500"><i class="fas fa-utensils"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">{data.get("surcharge_type", "Pension complète")}</h4><p class="text-gray-600 text-xs">Inclus dans le forfait</p></div></div>'

    car_rental_cost = int(data.get('car_rental_cost') or 0)
    car_rental_text_html = f'<div class="flex justify-between"><span>+ Voiture de location (sans franchise)</span><span class="font-semibold">~{car_rental_cost}€</span></div>' if car_rental_cost > 0 else ""
    
    car_rental_inclusion_html = ''
    if car_rental_cost > 0:
        if is_ultra_budget:
            car_rental_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-gray-500"><i class="fas fa-car"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Voiture de location</h4><p class="text-gray-600 text-xs">Franchise à partir de 1100€</p></div></div>'
        else:
            car_rental_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-gray-500"><i class="fas fa-car"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Voiture de location (sans franchise)</h4><p class="text-gray-600 text-xs">Explorez à votre rythme</p></div></div>'

    pricing_block_html = ''
    pricing_mode = data.get('pricing_mode', 'classic')
    hide_comparison = data.get('hide_comparison', False)
    
    if pricing_mode == 'pack':
        # Mode Pack Combiné
        pack_options = data.get('pack_options', {})
        vp_opts = pack_options.get('vp', {})
        
        # Labels pour l'affichage
        pension_labels = {
            'logement': 'Logement seul',
            'breakfast': 'Petit-déjeuner',
            'half': 'Demi-pension', 
            'full': 'Pension complète',
            'allin': 'All-Inclusive'
        }
        transfer_labels = {
            'none': 'Non inclus',
            'shared': 'Partagé',
            'private': 'Privé'
        }
        
        def get_baggage_text(val):
            if val == '0' or not val:
                return 'Non inclus'
            elif val == '1':
                return '1 bagage (20kg)'
            else:
                return f'{val} bagages (20kg)'
        
        vp_baggage = get_baggage_text(vp_opts.get('baggage', '0'))
        vp_transfer = transfer_labels.get(vp_opts.get('transfer', 'none'), 'Non inclus')
        vp_pension = pension_labels.get(vp_opts.get('pension', 'logement'), 'Logement seul')
        vp_custom = vp_opts.get('custom', '')
        vp_custom_html = f'<li class="flex items-center gap-2"><span class="text-green-600">✓</span> 🎁 {vp_custom}</li>' if vp_custom else ''
        
        # HTML conditionnel pour VP
        vp_baggage_html = f'<li class="flex items-center gap-2 mb-2"><span class="text-green-600">✓</span> 🧳 {vp_baggage}</li>' if vp_baggage != 'Non inclus' else ''
        vp_transfer_html = f'<li class="flex items-center gap-2 mb-2"><span class="text-green-600">✓</span> 🚐 Transfert {vp_transfer}</li>' if vp_transfer != 'Non inclus' else ''
        
        if hide_comparison:
            # Mode Solo Pack: affichage simplifié
            pricing_block_html = f'''
            <div class="instagram-card p-6">
                <h3 class="section-title text-xl mb-4">📦 Notre Pack</h3>
                <div style="background: #ecfdf5; border: 2px solid #10b981; border-radius: 12px; padding: 16px;">
                    <h4 style="font-weight: bold; color: #059669; margin-bottom: 12px; text-align: center;">🌟 Voyages Privilèges</h4>
                    <ul style="list-style: none; padding: 0; margin: 0; font-size: 14px;">
                        <li class="flex items-center gap-2 mb-2"><span class="text-green-600">✓</span> ✈️ Vol + Hôtel</li>
                        {vp_baggage_html}
                        {vp_transfer_html}
                        <li class="flex items-center gap-2 mb-2"><span class="text-green-600">✓</span> 🍽️ {vp_pension}</li>
                        {vp_custom_html}
                    </ul>
                    <div style="text-align: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid #a7f3d0;">
                        <span style="font-size: 24px; font-weight: bold; color: #059669;">{your_price} €</span>
                        <p class="text-sm font-light mt-1">{price_for_text}</p>
                    </div>
                </div>
                {cancellation_html}
            </div>
            '''
        else:
            # Mode Pack avec comparaison
            comp_opts = pack_options.get('comp', {})
            comp_baggage = get_baggage_text(comp_opts.get('baggage', '0'))
            comp_transfer = transfer_labels.get(comp_opts.get('transfer', 'none'), 'Non inclus')
            comp_pension = pension_labels.get(comp_opts.get('pension', 'logement'), 'Logement seul')
            comp_custom = comp_opts.get('custom', '')
            competitor_price = int(data.get('pack_competitor_price') or 0)
            comp_custom_html = f'<li class="flex items-center gap-2 text-gray-400"><span>—</span> {comp_custom}</li>' if comp_custom else ''
            
            # HTML conditionnel pour Concurrent
            comp_baggage_html = f'<li class="flex items-center gap-2 mb-2 text-gray-500"><span>🧳</span> {comp_baggage}</li>' if comp_baggage != 'Non inclus' else ''
            comp_transfer_html = f'<li class="flex items-center gap-2 mb-2 text-gray-500"><span>🚐</span> Transfert {comp_transfer}</li>' if comp_transfer != 'Non inclus' else ''
            
            pricing_block_html = f'''
            <div class="instagram-card p-6">
                <h3 class="section-title text-xl mb-4">🔍 Comparer en un coup d'œil</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <!-- Colonne Concurrent (Ailleurs) -->
                    <div style="background: #fef2f2; border: 2px solid #ef4444; border-radius: 12px; padding: 16px;">
                        <h4 style="font-weight: bold; color: #dc2626; margin-bottom: 12px; text-align: center;">🏢 Ailleurs</h4>
                        <ul style="list-style: none; padding: 0; margin: 0; font-size: 14px;">
                            <li class="flex items-center gap-2 mb-2"><span>✈️</span> Vol + Hôtel</li>
                            {comp_baggage_html}
                            {comp_transfer_html}
                            <li class="flex items-center gap-2 mb-2 text-gray-500"><span>🍽️</span> {comp_pension}</li>
                            {comp_custom_html}
                        </ul>
                        <div style="text-align: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid #fecaca;">
                            <span style="font-size: 24px; font-weight: bold; color: #dc2626;">{competitor_price} €</span>
                        </div>
                    </div>
                    
                    <!-- Colonne VP (Mon Pack) -->
                    <div style="background: #ecfdf5; border: 2px solid #10b981; border-radius: 12px; padding: 16px;">
                        <h4 style="font-weight: bold; color: #059669; margin-bottom: 12px; text-align: center;">🌟 Voyages Privilèges</h4>
                        <ul style="list-style: none; padding: 0; margin: 0; font-size: 14px;">
                            <li class="flex items-center gap-2 mb-2"><span class="text-green-600">✓</span> ✈️ Vol + Hôtel</li>
                            {vp_baggage_html}
                            {vp_transfer_html}
                            <li class="flex items-center gap-2 mb-2"><span class="text-green-600">✓</span> 🍽️ {vp_pension}</li>
                            {vp_custom_html}
                        </ul>
                        <div style="text-align: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid #a7f3d0;">
                            <span style="font-size: 24px; font-weight: bold; color: #059669;">{your_price} €</span>
                        </div>
                    </div>
                </div>
                
                <div class="economy-highlight" style="margin-top: 16px;">
                    💰 Vous économisez {savings} €
                </div>
                {cancellation_html}
            </div>
            '''
    elif is_ultra_budget:
        conditions = []
        if flight_price == 0:
            conditions.append("<li>- Pas de vols inclus</li>")
        else:
            conditions.append("<li>- Pas de bagage cabine</li>")
        
        if car_rental_cost > 0:
            conditions.append("<li>- Caution pour la voiture de location</li>")
        elif transfer_cost == 0:
            conditions.append("<li>- Transfert aéroport non compris</li>")

        if not (data.get('has_cancellation') == 'on' and data.get('cancellation_date')):
            conditions.append("<li>- Hôtel non remboursable</li>")
        else:
            conditions.append(f"<li>- Hôtel remboursable jusqu\'au {data.get('cancellation_date')}</li>")

        conditions.append("<li>- Horaires des vols non optimisés</li>")
        
        conditions_list_html = "".join(conditions)

        ultra_budget_warning_html = f'''
        <div class="mt-4 p-3 rounded-lg border-2 border-red-200 bg-red-50 text-sm">
            <h4 class="font-bold text-red-800 mb-2">⚠️ Tarif minimum avec les conditions suivantes :</h4>
            <ul class="text-xs text-red-700 list-none pl-0">{conditions_list_html}</ul>
            <p class="text-xs text-blue-700 mt-2">💡 Possibilité d'ajouter des services à la carte sur demande.</p>
        </div>
        '''
        pricing_block_html = f"""
        <div class="instagram-card p-6">
            <h3 class="section-title text-xl mb-4">Prix Ultra Budget</h3>
            <div class="p-4 rounded-lg bg-green-600 text-white"><h4 class="font-bold text-center mb-2">Notre Offre</h4><div class="text-center text-2xl font-bold">{your_price} €</div>{cancellation_html}</div>
            {ultra_budget_warning_html}
        </div>
        """
    else:
        # Mode Classique
        if hide_comparison:
            # Mode Solo Classique: affichage simplifié sans comparaison
            pricing_block_html = f"""
            <div class="instagram-card p-6">
                <h3 class="section-title text-xl mb-4">💰 Notre Offre</h3>
                {exclusive_services_html}
                <div class="p-4 rounded-lg bg-green-600 text-white mt-4">
                    <h4 class="font-bold text-center mb-2">Prix de votre séjour</h4>
                    <div class="text-center text-2xl font-bold">{your_price} €</div>
                    <p class="text-sm font-light mt-1 text-center">{price_for_text}</p>
                    {cancellation_html}
                </div>
            </div>
            """
        # Vérifier si l'économie est inférieure à 45€
        elif savings < 45:
            # Si économie < 45€ et qu'il y a des services additionnels, afficher un bloc simplifié
            if data.get('exclusive_services', '').strip():
                pricing_block_html = f"""
                <div class="instagram-card p-6">
                    <h3 class="section-title text-xl mb-4">Nos services exclusifs inclus</h3>
                    {exclusive_services_html}
                    <div class="p-4 rounded-lg bg-green-600 text-white mt-4"><h4 class="font-bold text-center mb-2">Notre Offre</h4><div class="text-center text-2xl font-bold">{your_price} €</div>{cancellation_html}</div>
                </div>
                """
            else:
                # Si économie < 45€ et pas de services additionnels, ne pas afficher le bloc
                pricing_block_html = ""
        else:
            # Économie >= 45€, afficher le bloc complet "Pourquoi nous choisir ?"
            comparison_block = f"""
                <div class="flex justify-between"><span>Hôtel ({data.get('stars')}⭐)</span><span class="font-semibold">{data.get('hotel_b2c_price', 'N/A')} €</span></div>
                {flight_text_html}{transfer_text_html}{car_rental_text_html}{surcharge_text_html}
                <hr class="my-3"><div class="flex justify-between text-base font-bold text-red-600"><span>TOTAL ESTIMÉ</span><span>{comparison_total} €</span></div>
            """
            pricing_block_html = f"""
            <div class="instagram-card p-6">
                <h3 class="section-title text-xl mb-4">Pourquoi nous choisir ?</h3>
                <div class="p-4 rounded-lg border-2 border-red-200 bg-red-50 mb-4"><h4 class="font-bold text-center mb-2">Prix estimé ailleurs</h4><div class="text-sm space-y-1">{comparison_block}</div></div>{exclusive_services_html}
                <div class="p-4 rounded-lg bg-green-600 text-white"><h4 class="font-bold text-center mb-2">Notre Offre</h4><div class="text-center text-2xl font-bold">{your_price} €</div>{cancellation_html}</div>
                <div class="economy-highlight">💰 Vous économisez {savings} € !</div>
            </div>
            """
    
    total_photos = len(real_data['photos']) if real_data.get('photos') else 0
    image_gallery = "".join([f'<div class="image-item"><img src="{url}" alt="Photo de {data["hotel_name"]}"></div>' for url in real_data.get('photos', [])[:6]]) or '<p>Aucune photo disponible.</p>'
    more_photos_button = f'<div class="text-center mt-4"><button id="voirPlusPhotos" class="bg-blue-500 hover:bg-blue-600 text-white font-semibold py-3 px-6 rounded-full transition-colors">📸 Voir plus de photos ({total_photos} au total)</button></div>' if total_photos > 6 else ""
    modal_all_photos = "".join([f'<img src="{url}" alt="Photo {i+1} de {data["hotel_name"]}" class="modal-photo">' for i, url in enumerate(real_data.get('photos', []))])

    video_html_block = ""
    if real_data.get('videos'):
        embed_url = f"https://www.youtube.com/embed/{real_data['videos'][0]['id']}"
        video_title = real_data['videos'][0]['title']
        video_html_block = f"""<div id="video-section-wrapper" class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Vidéo</h3><div><h4 class="font-semibold mb-2">Visite de l'hôtel</h4><div class="video-container aspect-w-16 aspect-h-9"><iframe src="{embed_url}" title="{video_title}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen class="w-full h-full rounded-lg"></iframe></div></div></div>"""

    reviews_section = "".join([f'<div class="bg-gray-50 p-4 rounded-lg"><div><span class="font-semibold">{r["author"]}</span> <span class="text-yellow-500">{r["rating"]}</span> <span class="text-gray-500 text-sm float-right">{r.get("date", "")}</span></div><p class="mt-2 text-gray-700">"{r["text"]}"</p></div>' for r in real_data.get('reviews', [])])

    destination_section = ""
    if real_data.get('cultural_attraction_image'):
        cultural_attraction_name = real_data.get('attractions', {}).get('culture', [''])[0] if real_data.get('attractions', {}).get('culture') else ''
        if cultural_attraction_name:
            destination_section += f'<div class="mb-6 rounded-lg overflow-hidden shadow-lg"><img src="{real_data["cultural_attraction_image"]}" alt="Image de {cultural_attraction_name}" class="w-full h-48 object-cover"><div class="p-4 bg-gray-50"><h4 class="font-bold text-gray-800">Incontournable : {cultural_attraction_name}</h4></div></div>'

    if real_data.get('restaurants'):
        restaurants_list_items = "".join([f'<li class="flex items-center"><i class="fas fa-utensils text-yellow-500 mr-3"></i><span>{resto.get("name")}</span></li>' for resto in real_data['restaurants']])
        destination_section += f'<div class="mb-6"><h4 class="font-semibold text-lg mb-3 text-gray-800">🍴 Top 3 Restaurants</h4><ul class="space-y-2 text-gray-700">{restaurants_list_items}</ul></div>'

    icons = {'plages': 'fa-water', 'culture': 'fa-monument', 'gastronomie': 'fa-utensils', 'activites': 'fa-map-signs'}
    colors = {'plages': 'bg-blue-500', 'culture': 'bg-purple-500', 'gastronomie': 'bg-green-500', 'activites': 'bg-orange-500'}
    categories = {'plages': 'Plages & Nature', 'culture': 'Culture & Histoire', 'gastronomie': 'Gastronomie Locale', 'activites': 'Activités & Loisirs'}
    
    flat_attractions = []
    for category, attractions in real_data.get('attractions', {}).items():
        start_index = 1 if category == 'culture' and real_data.get('cultural_attraction_image') else 0
        for attraction_name in attractions[start_index:]:
            flat_attractions.append({'name': attraction_name, 'category': category})

    if flat_attractions:
        other_attractions_items = "".join([f'<div class="flex items-start space-x-3"><div class="feature-icon {colors.get(attr["category"], "bg-gray-500")}" style="width: 35px; height: 35px; font-size: 16px; flex-shrink: 0;"><i class="fas {icons.get(attr["category"], "fa-question")}"></i></div><div><h5 class="font-semibold text-sm text-gray-800">{attr["name"]}</h5><p class="text-gray-500 text-xs">{categories.get(attr["category"])}</p></div></div>' for attr in flat_attractions[:4]])
        destination_section += f'<div><h4 class="font-semibold text-lg mb-3 text-gray-800">À explorer également</h4><div class="space-y-4">{other_attractions_items}</div></div>'

    creator_html = f'<p class="text-sm mt-3">Voyage proposé par <strong>{creator_pseudo}</strong></p>' if creator_pseudo else ""

    footer_html = f"""
        <div class="instagram-card p-6 bg-blue-500 text-white text-center">
            <h3 class="text-2xl font-bold mb-2">🌟 Réservez votre évasion !</h3>
            <p>Les places sont très limitées pour cette offre exclusive. Pour garantir votre place :</p>
            {creator_html}
            <div class="mt-4 flex flex-col sm:flex-row justify-center gap-4">
                <a href="tel:+32488433344" class="block w-full sm:w-auto bg-red-500 hover:bg-red-600 text-white font-bold py-3 px-6 rounded-full">📞 Appeler maintenant</a>
                <a href="mailto:infos@voyages-privileges.be" class="block w-full sm:w-auto bg-white hover:bg-gray-100 text-blue-500 font-bold py-3 px-6 rounded-full">✉️ Envoyer un email</a>
            </div>
        </div>
        <div class="instagram-card p-6 text-center">
             <h3 class="text-xl font-semibold mb-2">🗓️ Voyagez à vos dates</h3>
             <p class="text-gray-700">Les dates ou la durée de ce séjour ne vous conviennent pas ? Contactez-nous ! Nous pouvons vous créer une offre sur mesure.</p>
             <p class="text-sm text-gray-500 mt-2">Notez que le tarif concurrentiel de cette offre est spécifique à ces dates et conditions.</p>
        </div>
        
        <div class="instagram-card p-6 text-center">
            <a href="https://www.voyages-privileges.be" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-8 rounded-full transition-colors" style="display: inline-block;">
                Toutes nos offres
            </a>
        </div>

        <div class="instagram-card p-6 text-center">
            <h3 class="text-xl font-semibold mb-4">🌐 Partager cette offre</h3>
            <p class="text-gray-700 mb-4">Faites découvrir cette offre à vos proches !</p>
            <div class="flex justify-center gap-4 flex-wrap">
                <a href="#" 
                   id="shareWhatsApp"
                   class="flex items-center gap-2 bg-green-500 hover:bg-green-600 text-white font-semibold py-3 px-6 rounded-full transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M13.601 2.326A7.854 7.854 0 0 0 7.994 0C3.627 0 .068 3.558.064 7.926c0 1.399.366 2.76 1.057 3.965L0 16l4.204-1.102a7.933 7.933 0 0 0 3.79.965h.004c4.368 0 7.926-3.558 7.93-7.93A7.898 7.898 0 0 0 13.6 2.326zM7.994 14.521a6.573 6.573 0 0 1-3.356-.92l-.24-.144-2.494.654.666-2.433-.156-.251a6.56 6.56 0 0 1-1.007-3.505c0-3.626 2.957-6.584 6.591-6.584a6.56 6.56 0 0 1 4.66 1.931 6.557 6.557 0 0 1 1.928 4.66c-.004 3.639-2.961 6.592-6.592 6.592zm3.615-4.934c-.197-.099-1.17-.578-1.353-.646-.182-.065-.315-.099-.445.099-.133.197-.513.646-.627.775-.114.133-.232.148-.43.05-.197-.1-.836-.308-1.592-.985-.59-.525-.985-1.175-1.103-1.372-.114-.198-.011-.304.088-.403.087-.088.197-.232.296-.346.1-.114.133-.198.198-.33.065-.134.034-.248-.015-.347-.05-.099-.445-1.076-.612-1.47-.16-.389-.323-.335-.445-.34-.114-.007-.247-.007-.38-.007a.729.729 0 0 0-.529.247c-.182.198-.691.677-.691 1.654 0 .977.71 1.916.81 2.049.098.133 1.394 2.132 3.383 2.992.47.205.84.326 1.129.418.475.152.904.129 1.246.08.38-.058 1.171-.48 1.338-.943.164-.464.164-.86.114-.943-.049-.084-.182-.133-.38-.232z"/>
                    </svg>
                    WhatsApp
                </a>
                <a href="#" 
                   id="shareFacebook"
                   class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-full transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M16 8.049c0-4.446-3.582-8.05-8-8.05C3.58 0-.002 3.603-.002 8.05c0 4.017 2.926 7.347 6.75 7.951v-5.625h-2.03V8.05H6.75V6.275c0-2.017 1.195-3.131 3.022-3.131.876 0 1.791.157 1.791.157v1.98h-1.009c-.993 0-1.303.621-1.303 1.258v1.51h2.218l-.354 2.326H9.25V16c3.824-.604 6.75-3.934 6.75-7.951z"/>
                    </svg>
                    Facebook
                </a>
                <button 
                   id="copyLink"
                   class="flex items-center gap-2 bg-gradient-to-r from-purple-500 via-pink-500 to-red-500 hover:opacity-90 text-white font-semibold py-3 px-6 rounded-full transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M4.715 6.542 3.343 7.914a3 3 0 1 0 4.243 4.243l1.828-1.829A3 3 0 0 0 8.586 5.5L8 6.086a1.002 1.002 0 0 0-.154.199 2 2 0 0 1 .861 3.337L6.88 11.45a2 2 0 1 1-2.83-2.83l.793-.792a4.018 4.018 0 0 1-.128-1.287z"/>
                        <path d="M6.586 4.672A3 3 0 0 0 7.414 9.5l.775-.776a2 2 0 0 1-.896-3.346L9.12 3.55a2 2 0 1 1 2.83 2.83l-.793.792c.112.42.155.855.128 1.287l1.372-1.372a3 3 0 1 0-4.243-4.243L6.586 4.672z"/>
                    </svg>
                    Copier le lien
                </button>
            </div>
            <p id="copyMessage" class="text-sm text-green-600 mt-2 hidden">✓ Lien copié dans le presse-papier !</p>
        </div>

        <div class="instagram-card p-6 text-center">
            <h3 class="text-xl font-semibold mb-4">📞 Contact & Infos</h3>
            <img src="https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png" alt="Logo Voyages Privilèges" class="h-12 mx-auto mb-4">
            <p class="text-gray-800">📍 Rue Philippe Monnoyer 21, 6180 Courcelles</p>
            <p class="text-gray-800 my-2">📞 <a href="tel:+32488433344" class="text-blue-600">+32 488 43 33 44</a></p>
            <p class="text-gray-800">✉️ <a href="mailto:infos@voyages-privileges.be" class="text-blue-600">infos@voyages-privileges.be</a></p>
            <hr class="my-4">
            <p class="text-xs text-gray-500">SRL RIDEA (OldiBike)<br>Numéro de société : 1024.916.054 - RC Exploitation : 99730451</p>
        </div>
    """
    story_card_style = "background: linear-gradient(135deg, #FECACA 0%, #F87171 100%);" if is_ultra_budget else "background: linear-gradient(135deg, #3B82F6 0%, #60A5FA 100%);"
    cancellation_html = ""
    if data.get('has_cancellation') == 'on' and data.get('cancellation_date'):
        if flight_price > 0:
            cancellation_html = f"""
            <p class="text-xs font-light mt-1 text-center">✓ Annulation gratuite de l'hôtel jusqu'au {data.get("cancellation_date")}</p>
            <p class="text-xs font-bold text-orange-800 mt-1 text-center">Les vols ({flight_price} €) ne sont pas remboursables.</p>
            """
        else:
            cancellation_html = f'<p class="text-xs font-light mt-1 text-center">✓ Annulation gratuite jusqu\'au {data.get("cancellation_date")}</p>'

    # --- NOUVEAU : Bloc Événement ---
    event_block_html = ""
    event_images = data.get('event_images', [])
    event_description = data.get('event_description', '').strip()

    if event_images and event_description:
        carousel_items_html = "".join([
            f'<div class="event-carousel-item"><img src="{img_src}" alt="Photo événement"></div>'
            for img_src in event_images
        ])

        event_block_html = f"""
        <div class="instagram-card p-6">
            <h3 class="section-title text-xl mb-4">À faire sur place</h3>
            
            <div class="event-carousel-container">
                <div class="event-carousel-wrapper">
                    {carousel_items_html}
                </div>
                <button class="event-carousel-prev">❮</button>
                <button class="event-carousel-next">❯</button>
            </div>

            <p class="text-gray-700 mt-4">{event_description.replace(chr(10), "<br>")}</p>
        </div>
        """
    # --- FIN NOUVEAU ---

    html_template = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Voyages Privilèges - {display_hotel_name}</title>
    <link href="https://cdn.tailwindcss.com/2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Poppins:wght@300;400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com?plugins=aspect-ratio"></script>
    <style>
        body {{ font-family: 'Poppins', sans-serif; }} .section-title {{ font-family: 'Playfair Display', serif; }}
        .main-container {{ max-width: 600px; margin: auto; padding: 10px; }}
        .instagram-card {{ background: white; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; margin-top: 20px; }}
        .story-card {{ {story_card_style} border-radius: 25px; padding: 25px; color: white; text-align: center; box-shadow: 0 10px 30px rgba(59, 130, 246, 0.3); margin-top: 0; }}
        .image-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }}
        .image-item img {{ width: 100%; height: 200px; object-fit: cover; transition: transform 0.3s ease; border-radius: 15px; cursor: pointer; }}
        .reviews-grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
        .economy-highlight {{ background: linear-gradient(45deg, #ffd700, #ffb347); color: #333; padding: 15px; border-radius: 15px; text-align: center; margin-top: 20px; font-weight: bold;}}
        .feature-icon {{ width: 45px; height: 45px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0; }}
        .modal-photos {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 1000; overflow-y: auto; padding: 20px; }}
        .modal-photos-content {{ max-width: 800px; margin: 0 auto; padding-top: 60px; }}
        .close-photos {{ position: fixed; top: 20px; right: 30px; font-size: 40px; color: white; cursor: pointer; z-index: 1001; font-weight: bold; width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.5); border-radius: 50%; }}
        .close-photos:hover {{ background: rgba(255,255,255,0.2); }}
        .modal-photo {{ width: 100%; margin-bottom: 20px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }}
        .photo-counter {{ position: fixed; top: 20px; left: 30px; color: white; background: rgba(0,0,0,0.5); padding: 10px 15px; border-radius: 20px; font-weight: bold; z-index: 1001; }}

        /* Styles pour le carrousel d'événement */
        .event-carousel-container {{ 
            position: relative; 
            overflow: hidden; 
            border-radius: 15px;
            max-width: 250px;
            margin: 0 auto;
        }}
        .event-carousel-wrapper {{ display: flex; transition: transform 0.5s ease-in-out; }}
        .event-carousel-item {{ min-width: 100%; box-sizing: border-box; }}
        .event-carousel-item img {{
            width: 100%;
            height: 200px;
            object-fit: cover;
            display: block;
            border-radius: 15px;
        }}
        .event-carousel-prev, .event-carousel-next {{
            cursor: pointer; position: absolute; top: 50%; transform: translateY(-50%);
            width: auto; padding: 16px; color: white; font-weight: bold; font-size: 20px;
            background-color: rgba(0,0,0,0.4); border: none; user-select: none;
            border-radius: 0 3px 3px 0;
        }}
        .event-carousel-next {{ right: 0; border-radius: 3px 0 0 3px; }}
        .event-carousel-prev:hover, .event-carousel-next:hover {{ background-color: rgba(0,0,0,0.7); }}
        
        /* Tablette (640px - 1023px) */
        @media (min-width: 640px) and (max-width: 1023px) {{
            .main-container {{ max-width: 900px; padding: 20px; }}
        }}
        
        /* PC (1024px et plus) - Optimisation large écran */
        @media (min-width: 1024px) {{
            .main-container {{ max-width: 1200px; padding: 30px; }}
            .image-grid {{ grid-template-columns: repeat(3, 1fr); gap: 20px; }}
            .image-item img {{ height: 250px; }}
            
            /* Transformer le carousel en grille sur PC */
            .event-carousel-container {{ 
                max-width: 100%;
                overflow: visible;
            }}
            .event-carousel-wrapper {{ 
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                transform: none !important;
            }}
            .event-carousel-item {{ 
                min-width: auto;
            }}
            .event-carousel-item img {{ 
                height: 250px;
            }}
            .event-carousel-prev, .event-carousel-next {{
                display: none;
            }}
            
            .reviews-grid {{ grid-template-columns: repeat(2, 1fr); gap: 20px; }}
            .story-card {{ padding: 40px; }}
            .instagram-card {{ padding: 30px !important; }}
        }}
        
        @media (max-width: 768px) {{ .close-photos {{ top: 15px; right: 15px; font-size: 30px; width: 40px; height: 40px; }} .photo-counter {{ top: 15px; left: 15px; padding: 8px 12px; font-size: 14px; }} .modal-photos-content {{ padding-top: 80px; padding-left: 10px; padding-right: 10px; }} }}
    </style>
</head>
<body>
    <div class="main-container">
        <div style="text-align: center; padding-top: 20px; padding-bottom: 10px;">
            <img src="https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png" alt="Logo Voyages Privilèges" style="max-height: 50px; margin: auto;">
        </div>
        <div class="story-card">
            <img src="{real_data.get('photos', [''])[0]}" alt="{data['hotel_name']}" style="width: 100%; height: 256px; object-fit: cover; border-radius: 8px; margin-bottom: 1rem;">
            <h2 class="text-2xl font-bold">{display_hotel_name} {stars}</h2>
            <p>📍 {display_address}</p>
            <p class="mt-4">🗓️ Du {date_start} au {date_end}</p>
            <div class="text-4xl font-bold mt-2">{your_price} €</div>
            <p>{price_for_text}</p>{price_per_person_text}
            {f'<p class="text-sm mt-2">Note Google: {real_data["hotel_rating"]}/5 ({real_data["total_reviews"]} avis)</p>' if real_data.get("hotel_rating", 0) > 0 else ""}
            <div class="mt-4">{instagram_button_html}</div>
        </div>
        {flights_block_html}
        {'<div class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Inclus dans votre séjour</h3><div class="space-y-5">' + flight_inclusion_html + transfer_inclusion_html + car_rental_inclusion_html + '<div class="flex items-center"><div class="feature-icon bg-purple-500"><i class="fas fa-hotel"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Hôtel ' + stars + ' ' + display_hotel_name + '</h4><p class="text-gray-600 text-xs">Style traditionnel</p></div></div>' + pension_html + baggage_inclusion_html + '</div></div>' if pricing_mode != 'pack' else ''}
        {pricing_block_html}
        {event_block_html}
        <div class="instagram-card p-6" id="gallery-section"><h3 class="section-title text-xl mb-4">Galerie de photos</h3><div class="image-grid">{image_gallery}</div>{more_photos_button}</div>
        <div id="photosModal" class="modal-photos"><span class="close-photos" id="closePhotos">×</span><div class="photo-counter" id="photoCounter">Photo 1 sur {total_photos}</div><div class="modal-photos-content">{modal_all_photos}</div></div>
        {video_html_block}
        <div class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Avis des clients</h3><div class="reviews-grid">{reviews_section}</div></div>
        <div class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Découvrir {city_name}</h3>{destination_section}</div>
        {footer_html}
    </div>
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        // Gestion de la galerie photos
        const voirPlusBtn = document.getElementById('voirPlusPhotos');
        const modal = document.getElementById('photosModal');
        const closeBtn = document.getElementById('closePhotos');
        const photoCounter = document.getElementById('photoCounter');
        const modalPhotos = document.querySelectorAll('.modal-photo');
        if (voirPlusBtn) {{ voirPlusBtn.addEventListener('click', function() {{ if (modal) modal.style.display = 'block'; document.body.style.overflow = 'hidden'; }}); }}
        document.querySelectorAll('.image-item img').forEach(function(img) {{ img.addEventListener('click', function() {{ if (modal) modal.style.display = 'block'; document.body.style.overflow = 'hidden'; }}); }});
        function closeModal() {{ if (modal) modal.style.display = 'none'; document.body.style.overflow = 'auto'; }}
        if (closeBtn) {{ closeBtn.addEventListener('click', closeModal); }}
        if (modal) {{ modal.addEventListener('click', function(e) {{ if (e.target === modal) {{ closeModal(); }} }}); }}
        document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape' && modal && modal.style.display === 'block') {{ closeModal(); }} }});
        if (modalPhotos.length > 0) {{
            const observer = new IntersectionObserver(function(entries) {{
                entries.forEach(function(entry) {{
                    if (entry.isIntersecting) {{
                        const index = Array.from(modalPhotos).indexOf(entry.target) + 1;
                        if (photoCounter) {{ photoCounter.textContent = `Photo ${{index}} sur ${{modalPhotos.length}}`; }}
                    }}
                }});
            }}, {{ threshold: 0.5 }});
            modalPhotos.forEach(function(photo) {{ observer.observe(photo); }});
        }}

        // Gestion du partage sur les réseaux sociaux
        const currentUrl = window.location.href;
        const shareText = 'Découvrez cette superbe offre de voyage : {display_hotel_name_js} à partir de {your_price}€ ! ';
        
        // Bouton WhatsApp
        const shareWhatsApp = document.getElementById('shareWhatsApp');
        if (shareWhatsApp) {{
            shareWhatsApp.addEventListener('click', function(e) {{
                e.preventDefault();
                const whatsappUrl = `https://wa.me/?text=${{encodeURIComponent(shareText + currentUrl)}}`;
                window.open(whatsappUrl, '_blank');
            }});
        }}
        
        // Bouton Facebook
        const shareFacebook = document.getElementById('shareFacebook');
        if (shareFacebook) {{
            shareFacebook.addEventListener('click', function(e) {{
                e.preventDefault();
                const facebookUrl = `https://www.facebook.com/sharer/sharer.php?u=${{encodeURIComponent(currentUrl)}}`;
                window.open(facebookUrl, '_blank');
            }});
        }}
        
        // Bouton Copier le lien
        const copyLink = document.getElementById('copyLink');
        const copyMessage = document.getElementById('copyMessage');
        if (copyLink) {{
            copyLink.addEventListener('click', function() {{
                navigator.clipboard.writeText(currentUrl).then(function() {{
                    if (copyMessage) {{
                        copyMessage.classList.remove('hidden');
                        setTimeout(function() {{
                            copyMessage.classList.add('hidden');
                        }}, 3000);
                    }}
                }}).catch(function(err) {{
                    console.error('Erreur lors de la copie:', err);
                }});
            }});
        }}

        // Gestion du carrousel d'événement
        const eventCarousel = document.querySelector('.event-carousel-wrapper');
        if (eventCarousel) {{
            let currentIndex = 0;
            const items = document.querySelectorAll('.event-carousel-item');
            const totalItems = items.length;
            
            document.querySelector('.event-carousel-next').addEventListener('click', () => {{
                currentIndex = (currentIndex + 1) % totalItems;
                eventCarousel.style.transform = `translateX(-${{currentIndex * 100}}%)`;
            }});

            document.querySelector('.event-carousel-prev').addEventListener('click', () => {{
                currentIndex = (currentIndex - 1 + totalItems) % totalItems;
                eventCarousel.style.transform = `translateX(-${{currentIndex * 100}}%)`;
            }});
        }}
    }});
    </script>
</body>
</html>"""
    return html_template
    baggage_option = data.get('baggage_type', 'bagages 10 kilos')
    baggage_inclusion_html = ''


# ============================================================
# GUIDE ITINÉRAIRE INTERACTIF
# ============================================================

class GuideService:
    """Génère des guides itinéraires interactifs (HTML standalone avec Leaflet.js)."""

    DAY_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f97316']

    def __init__(self):
        self.google_api_key = os.environ.get('GOOGLE_API_KEY')
        if self.google_api_key:
            genai.configure(api_key=self.google_api_key)

    def get_hotel_coordinates(self, place_id):
        """Récupère lat/lng et nom depuis un place_id Google."""
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            'place_id': place_id,
            'fields': 'geometry,name,formatted_address',
            'key': self.google_api_key
        }
        try:
            response = requests.get(url, params=params, timeout=15)
            result = response.json().get('result', {})
            location = result.get('geometry', {}).get('location', {})
            return {
                'lat': location.get('lat'),
                'lng': location.get('lng'),
                'name': result.get('name', ''),
                'address': result.get('formatted_address', '')
            }
        except Exception as e:
            print(f"Erreur get_hotel_coordinates: {e}")
            return None

    def discover_pois(self, lat, lng, radius=15000):
        """Découvre les POI autour de l'hôtel via Google Places Nearby Search."""
        categories = ['tourist_attraction', 'restaurant', 'museum', 'park']
        all_pois = []
        seen_place_ids = set()
        print(f"\n🔍 [GUIDE] discover_pois: lat={lat}, lng={lng}, radius={radius}")

        for category in categories:
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                'location': f'{lat},{lng}',
                'radius': radius,
                'type': category,
                'key': self.google_api_key,
                'language': 'fr'
            }
            try:
                response = requests.get(url, params=params, timeout=15)
                resp_json = response.json()
                results = resp_json.get('results', [])
                print(f"   📍 {category}: {len(results)} résultats (status: {resp_json.get('status', '?')})")

                for place in results:
                    pid = place.get('place_id')
                    rating = place.get('rating', 0)
                    if pid in seen_place_ids or rating < 4.0:
                        continue
                    seen_place_ids.add(pid)

                    photo_url = None
                    if place.get('photos'):
                        ref = place['photos'][0].get('photo_reference')
                        if ref:
                            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={ref}&key={self.google_api_key}"

                    loc = place.get('geometry', {}).get('location', {})
                    all_pois.append({
                        'place_id': pid,
                        'name': place.get('name', ''),
                        'address': place.get('vicinity', ''),
                        'lat': loc.get('lat'),
                        'lng': loc.get('lng'),
                        'rating': rating,
                        'user_ratings_total': place.get('user_ratings_total', 0),
                        'types': place.get('types', []),
                        'photo_url': photo_url
                    })
            except Exception as e:
                print(f"Erreur discover_pois ({category}): {e}")

        all_pois.sort(key=lambda x: (-x['rating'], -x.get('user_ratings_total', 0)))
        print(f"   ✅ Total POIs retenus (rating>=4): {len(all_pois)}, envoi des top {min(30, len(all_pois))}")
        for p in all_pois[:5]:
            print(f"      - {p['name']} (★{p['rating']}, {p.get('user_ratings_total',0)} avis)")
        return all_pois[:30]

    def organize_pois_with_gemini(self, pois, hotel_coords, num_days, date_start, flight_arrival=None, flight_departure=None, airport_info=None):
        """Utilise Gemini AI pour organiser les POI en itinéraire jour par jour."""
        import re as _re
        model = genai.GenerativeModel('models/gemini-2.5-flash')

        # Index photo par nom pour ré-association après réponse Gemini
        photo_map = {}
        for p in pois:
            if p.get('photo_url'):
                photo_map[p['name'].lower().strip()] = p['photo_url']

        # Limiter à 20 POIs pour Gemini (les 30 restent dispo pour remplacement)
        pois_for_gemini = pois[:20]

        airport_text = ""
        if airport_info:
            airport_text = f'Aéroport: lat={airport_info["lat"]}, lng={airport_info["lng"]}, name="{airport_info["name"]}"'
        else:
            airport_text = "Aéroport: non renseigné"

        def build_prompt(poi_list):
            pois_for_prompt = [
                {'name': p['name'], 'address': p['address'], 'lat': p['lat'], 'lng': p['lng'], 'rating': p['rating']}
                for p in poi_list
            ]
            pois_text = json.dumps(pois_for_prompt, ensure_ascii=False, indent=2)
            return f"""Tu es un expert en planification de voyages. Organise ces POIs en un itinéraire de {num_days} jours.

Hôtel: lat={hotel_coords['lat']}, lng={hotel_coords['lng']}, name="{hotel_coords['name']}"
{airport_text}
Date de début: {date_start}
{"Arrivée vol: " + flight_arrival if flight_arrival else "Pas de contrainte d'arrivée"}
{"Départ vol: " + flight_departure if flight_departure else "Pas de contrainte de départ"}

POIs disponibles:
{pois_text}

CONSIGNES STRICTES:
1. Sélectionne 2 à 4 POIs par jour (pas plus).
2. Organise-les par PROXIMITÉ GÉOGRAPHIQUE pour minimiser les trajets dans une même journée.
3. Le premier POI de chaque jour part de l'hôtel.
4. Jour 1: si heure d'arrivée vol renseignée, commence les activités APRÈS l'arrivée + 1h de transfert.
5. Dernier jour: si heure de départ vol renseignée, le DERNIER POI DOIT ÊTRE "Transfert Aéroport" avec les coordonnées de l'aéroport, prévoir 2h de marge avant le vol. Utilise les vraies coordonnées de l'aéroport pour le champ "pos".
6. Alterne restaurants et visites logiquement (déjeuner ~12h-13h, dîner ~19h-20h30).
7. Estime le budget en monnaie locale du pays.
8. Estime le type de trajet: "walk" si < 20 min à pied, sinon "car".
9. Donne un conseil pratique pour chaque trajet (tip).
10. Ajoute un label "⚠️ RÉSERVER" pour les lieux qui nécessitent une réservation (restaurants gastronomiques, spas, spectacles).
11. IMPORTANT - COHÉRENCE TEMPORELLE: estime la durée de chaque activité (champ "duration"). L'heure du POI suivant = heure actuelle + durée activité + durée trajet. Exemple: visite à 10:00 dure 1h30 + trajet 15 min → prochain POI à 11:45. Restaurant = 1h à 1h30. Visite/musée = 1h à 2h. Parc/plage = 1h30 à 2h30. Shopping = 1h. Transfert aéroport = 30 min.

Réponds UNIQUEMENT avec un JSON valide (pas de commentaire, pas de markdown):
[
  {{
    "id": "identifiant_slug_unique",
    "day": 1,
    "from": "Nom du lieu précédent ou nom de l'hôtel",
    "time": "HH:MM",
    "duration": "1h30",
    "name": "Nom du POI (exact comme dans la liste)",
    "pos": [lat, lng],
    "address": "adresse complète",
    "budget": "estimation (ex: 350 MAD, Gratuit, Shopping)",
    "travel": "emoji + durée estimée (ex: 🚶 12 min à pied, 🚕 15 min)",
    "travelType": "walk ou car",
    "tip": "conseil pratique pour le trajet",
    "desc": "description courte engageante (max 10 mots)",
    "label": "⚠️ RÉSERVER si nécessaire, sinon ne pas inclure ce champ"
  }}
]"""

        def call_gemini(poi_list, attempt=1):
            prompt = build_prompt(poi_list)
            print(f"\n🤖 [GUIDE] Appel Gemini (tentative {attempt}): {num_days} jours, {len(poi_list)} POIs")
            print(f"   📏 Taille prompt: {len(prompt)} chars")
            response = model.generate_content(prompt)
            text = response.text.strip()
            print(f"   📝 Gemini réponse ({len(text)} chars): {text[:300]}...")
            return text

        # Tentative avec 20 POIs, puis retry avec 12 si timeout
        for attempt, poi_count in [(1, 20), (2, 12)]:
            poi_subset = pois_for_gemini[:poi_count]
            text = ""
            try:
                text = call_gemini(poi_subset, attempt)

                # Parsing JSON avec fallback regex
                organized = None
                try:
                    organized = json.loads(text)
                except json.JSONDecodeError:
                    print(f"   ⚠️ JSON direct échoué, extraction regex...")
                    cleaned = text.replace("```json", "").replace("```", "").strip()
                    match = _re.search(r'\[[\s\S]*\]', cleaned)
                    if match:
                        organized = json.loads(match.group())
                    else:
                        print(f"   ❌ Aucun JSON array trouvé")
                        print(f"   📝 Texte: {text[:500]}")
                        continue

                if not isinstance(organized, list) or len(organized) == 0:
                    print(f"   ❌ Résultat vide ou invalide")
                    continue

                print(f"   ✅ Gemini a organisé {len(organized)} POIs")

                # Ré-associer les photos depuis les POI originaux
                for poi in organized:
                    poi_name_lower = poi.get('name', '').lower().strip()
                    if poi_name_lower in photo_map:
                        poi['img'] = photo_map[poi_name_lower]
                    else:
                        matched = False
                        for orig_name, photo_url in photo_map.items():
                            if orig_name in poi_name_lower or poi_name_lower in orig_name:
                                poi['img'] = photo_url
                                matched = True
                                break
                        if not matched:
                            poi['img'] = ''

                for p in organized[:3]:
                    print(f"      - Jour {p.get('day')}: {p.get('name')} à {p.get('time')} (img: {'✅' if p.get('img') else '❌'})")
                return organized

            except Exception as e:
                print(f"   ❌ Erreur Gemini (tentative {attempt}): {type(e).__name__}: {e}")
                if attempt == 2:
                    import traceback
                    traceback.print_exc()

        print("   ❌ Toutes les tentatives ont échoué")
        return []

    def calculate_distances(self, organized_pois, hotel_coords):
        """Calcule les temps de trajet réels via Google Distance Matrix API."""
        print(f"\n🚗 [GUIDE] calculate_distances: {len(organized_pois)} POIs à traiter")
        if not organized_pois:
            print("   ⚠️ Aucun POI, skip Distance Matrix")
            return organized_pois
        days = {}
        for poi in organized_pois:
            d = poi['day']
            if d not in days:
                days[d] = []
            days[d].append(poi)

        for day_num, day_pois in days.items():
            for i, poi in enumerate(day_pois):
                if i == 0:
                    origin = f"{hotel_coords['lat']},{hotel_coords['lng']}"
                else:
                    prev = day_pois[i - 1]
                    origin = f"{prev['pos'][0]},{prev['pos'][1]}"
                dest = f"{poi['pos'][0]},{poi['pos'][1]}"

                mode = 'walking' if poi.get('travelType') == 'walk' else 'driving'
                url = "https://maps.googleapis.com/maps/api/distancematrix/json"
                params = {
                    'origins': origin,
                    'destinations': dest,
                    'mode': mode,
                    'key': self.google_api_key,
                    'language': 'fr'
                }

                try:
                    resp = requests.get(url, params=params, timeout=10)
                    data = resp.json()
                    element = data['rows'][0]['elements'][0]
                    if element['status'] == 'OK':
                        duration_text = element['duration']['text']
                        emoji = '🚶' if poi.get('travelType') == 'walk' else '🚕'
                        poi['travel'] = f"{emoji} {duration_text}"
                except Exception as e:
                    print(f"Distance Matrix error ({poi.get('name', '?')}): {e}")

        return organized_pois

    def get_top_unused_pois(self, all_pois, used_pois, limit=3):
        """Retourne les meilleurs POI non utilisés (note > 4.5) pour la section 'À faire aussi'."""
        used_names = {p.get('name', '').lower() for p in used_pois}
        unused = [p for p in all_pois if p['name'].lower() not in used_names and p['rating'] >= 4.5]
        unused.sort(key=lambda x: (-x['rating'], -x.get('user_ratings_total', 0)))
        return unused[:limit]

    def generate_guide_html(self, city, hotel_name, hotel_lat, hotel_lng,
                            date_start, date_end, num_days, poi_data,
                            flight_arrival=None, flight_departure=None,
                            extra_pois=None):
        """Génère le HTML standalone du guide (structure identique à Marrakech.html)."""
        from datetime import timedelta

        day_names_fr = ['Lun.', 'Mar.', 'Mer.', 'Jeu.', 'Ven.', 'Sam.', 'Dim.']
        start = datetime.strptime(date_start, '%Y-%m-%d')
        year = start.year

        # Calculer les noms de jours et onglets
        day_tabs = []
        day_labels = []
        for i in range(num_days):
            d = start + timedelta(days=i)
            color = self.DAY_COLORS[i % len(self.DAY_COLORS)]
            day_name = day_names_fr[d.weekday()]
            day_num = d.day
            day_tabs.append({'day': i + 1, 'label': f"{day_name} {day_num}", 'color': color})
            day_labels.append(f"{day_name} {day_num}")

        # Assigner les couleurs aux POI
        for poi in poi_data:
            poi['color'] = self.DAY_COLORS[(poi['day'] - 1) % len(self.DAY_COLORS)]

        # Générer les onglets HTML
        color_tw_map = {
            '#ef4444': 'red',
            '#3b82f6': 'blue',
            '#22c55e': 'green',
            '#f97316': 'orange',
        }
        tabs_html = ''
        for tab in day_tabs:
            tw = color_tw_map.get(tab['color'], 'stone')
            tabs_html += f'        <a href="#day{tab["day"]}" class="flex-shrink-0 px-4 py-1.5 bg-{tw}-50 text-{tw}-600 rounded-full text-[10px] font-bold uppercase border border-{tw}-100">{tab["label"]}</a>\n'

        # Checklist depuis les POI avec label
        checklist_items = [
            f'{poi["name"]} ({poi.get("time", "")})'
            for poi in poi_data if poi.get('label')
        ]
        checklist_html = ''
        for item in checklist_items:
            checklist_html += f'                <div class="checkbox-row"><input type="checkbox" class="custom-cb"><span class="text-[11px] font-light">{item}</span></div>\n'

        # Section "À faire aussi"
        extra_pois_html = ''
        if extra_pois:
            extra_cards = ''
            for ep in extra_pois[:3]:
                img_url = ep.get('photo_url', '')
                extra_cards += f'''
            <div class="bg-white rounded-2xl overflow-hidden border border-stone-100 shadow-sm">
                <div class="h-32 bg-stone-100">{"<img src=&quot;" + img_url + "&quot; class=&quot;w-full h-full object-cover&quot; alt=&quot;" + ep['name'] + "&quot;>" if img_url else ""}</div>
                <div class="p-3">
                    <h4 class="font-bold text-sm">{ep['name']}</h4>
                    <p class="text-[10px] text-stone-500 mt-1">{ep.get('address', '')}</p>
                    <div class="flex items-center gap-1 mt-2">
                        <span class="text-[10px] font-bold text-amber-600">★ {ep['rating']}</span>
                        <span class="text-[9px] text-stone-400">({ep.get('user_ratings_total', 0)} avis)</span>
                    </div>
                </div>
            </div>'''
            extra_pois_html = f'''
        <div class="mt-8 mb-4 px-4">
            <h2 class="text-xl font-bold text-stone-800 mb-4 border-l-4 border-amber-400 pl-3">À faire aussi</h2>
            <div class="grid grid-cols-1 gap-3">
                {extra_cards}
            </div>
        </div>'''

        poi_json = json.dumps(poi_data, ensure_ascii=False)
        day_labels_json = json.dumps(day_labels, ensure_ascii=False)

        html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{city} {year} - Guide Interactif</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        :root {{ --ocre: #D4A373; --terracotta: #C1666B; --majorelle: #4A7C9E; --gold: #D4AF37; }}
        body {{ font-family: 'Inter', sans-serif; background-color: #fdfbf7; color: #1a1a1a; scroll-behavior: smooth; }}
        h1, h2, h3, h4 {{ font-family: 'Playfair Display', serif; }}
        #interactive-map {{ height: 350px; width: 100%; z-index: 10; border-radius: 1.5rem; }}
        .day-section {{ padding: 25px 16px; border-bottom: 1px solid #eee; }}
        .item-card {{ background: white; border-radius: 1.25rem; overflow: hidden; border: 1px solid #f0f0f0; margin-bottom: 12px; display: flex; flex-direction: column; transition: transform 0.2s; }}
        .item-main {{ display: flex; min-height: 110px; }}
        .item-img {{ width: 110px; flex-shrink: 0; background-color: #f3f3f3; }}
        .item-img img {{ width: 100%; height: 100%; object-fit: cover; }}
        .item-content {{ padding: 12px; flex-grow: 1; display: flex; flex-direction: column; }}
        .item-actions {{ display: grid; grid-template-columns: 1fr 1fr 1fr; border-top: 1px solid #f9f9f9; padding: 8px 12px; gap: 6px; background: #fafafa; }}
        .action-btn {{ display: flex; align-items: center; justify-content: center; gap: 4px; font-size: 9px; font-weight: 600; color: #666; padding: 6px 10px; border-radius: 8px; background: white; border: 1px solid #eee; }}
        .sticky-header {{ position: sticky; top: 0; z-index: 50; background: rgba(253, 251, 247, 0.95); backdrop-filter: blur(8px); border-bottom: 1px solid #eee; }}
        .no-scrollbar::-webkit-scrollbar {{ display: none; }}
        #poi-modal, #transfer-modal {{ display: none; position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.5); backdrop-filter: blur(4px); align-items: center; justify-content: center; padding: 20px; }}
        .modal-content {{ background: white; border-radius: 1.5rem; width: 100%; max-width: 320px; padding: 24px; position: relative; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); }}
        .custom-cb {{ width: 18px; height: 18px; accent-color: var(--gold); cursor: pointer; }}
        .creator-logo {{ max-width: 100px; height: auto; }}
        .logo-wrapper {{ background: white; padding: 8px 16px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: inline-block; margin-top: 8px; }}
    </style>
</head>
<body class="antialiased text-sm">

    <div id="poi-modal" onclick="closeModal('poi-modal')">
        <div class="modal-content" onclick="event.stopPropagation()">
            <button onclick="closeModal('poi-modal')" class="absolute top-4 right-4 text-stone-400"><i data-lucide="x" size="20"></i></button>
            <div id="modal-icon" class="w-12 h-12 rounded-full mb-4 flex items-center justify-center"></div>
            <h3 id="modal-title" class="text-xl font-bold mb-2"></h3>
            <p id="modal-address" class="text-stone-500 text-xs mb-6 leading-relaxed"></p>
            <a id="modal-link" href="#" target="_blank" class="w-full bg-stone-900 text-white py-3 rounded-xl font-bold flex items-center justify-center gap-2">
                <i data-lucide="map-pin" size="16"></i> Ouvrir Google Maps
            </a>
        </div>
    </div>

    <div id="transfer-modal" onclick="closeModal('transfer-modal')">
        <div class="modal-content text-center" onclick="event.stopPropagation()">
            <button onclick="closeModal('transfer-modal')" class="absolute top-4 right-4 text-stone-400"><i data-lucide="x" size="20"></i></button>
            <div class="w-16 h-16 bg-stone-100 rounded-full mx-auto mb-4 flex items-center justify-center text-stone-600">
                <i id="transfer-icon" data-lucide="arrow-right-left" size="32"></i>
            </div>
            <h3 class="text-xs font-bold uppercase tracking-widest text-stone-400 mb-2">L'Enchaînement</h3>
            <div class="flex flex-col gap-1 mb-4">
                <p id="transfer-from" class="text-[10px] font-bold text-stone-400"></p>
                <i data-lucide="chevron-down" size="14" class="mx-auto text-gold"></i>
                <p id="transfer-to" class="text-sm font-bold text-stone-800"></p>
            </div>
            <div class="bg-stone-50 p-4 rounded-xl">
                <p id="transfer-text" class="text-gold font-bold text-sm mb-1"></p>
                <p id="transfer-tip" class="text-[10px] text-stone-500 italic leading-relaxed"></p>
            </div>
        </div>
    </div>

    <header class="sticky-header px-4 py-3 flex justify-between items-center">
        <div class="flex items-center gap-3">
            <img src="https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png" alt="Logo" style="height:28px;">
            <h1 class="text-lg font-bold text-stone-800 italic">{city} <span class="text-terracotta">{year}</span></h1>
        </div>
        <div class="flex gap-4 text-stone-500">
            <a href="#interactive-map" class="bg-stone-100 p-2 rounded-full"><i data-lucide="map" size="18"></i></a>
            <a href="#info" class="bg-stone-100 p-2 rounded-full"><i data-lucide="info" size="18"></i></a>
        </div>
    </header>

    <section class="p-4" id="map-container">
        <div id="interactive-map" class="shadow-xl border border-white"></div>
    </section>

    <div class="flex overflow-x-auto no-scrollbar gap-2 px-4 py-2 bg-white sticky top-[53px] z-40 border-b">
{tabs_html}    </div>

    <main id="schedule-container"></main>

{extra_pois_html}

    <section id="info" class="bg-stone-900 text-white px-6 py-10 pb-16 rounded-t-[2.5rem] text-center border-t border-white/5 mt-8">
        <h2 class="text-gold text-lg font-bold mb-6 italic">Mémo Voyage</h2>
        <div class="text-left mb-10 bg-white/5 p-5 rounded-2xl border border-white/10 shadow-inner">
            <h3 class="text-gold text-xs font-bold mb-4 uppercase tracking-[0.2em] border-b border-white/10 pb-2">Checklist Réservations</h3>
            <div class="space-y-1">
{checklist_html}            </div>
        </div>
        <div class="pt-8 flex flex-col items-center">
            <div class="logo-wrapper"><img src="https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png" alt="Logo" class="creator-logo"></div>
        </div>
    </section>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const hotelPos = [{hotel_lat}, {hotel_lng}];
        const hotelName = {json.dumps(hotel_name, ensure_ascii=False)};
        const poiData = {poi_json};
        const dayNames = {day_labels_json};
        const numDays = {num_days};

        const map = L.map('interactive-map', {{ zoomControl: false }}).setView(hotelPos, 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);

        L.marker(hotelPos, {{
            icon: L.divIcon({{
                className: 'hotel-marker',
                html: '<div style="background-color: #a855f7; width: 18px; height: 18px; border: 3px solid white; border-radius: 4px; box-shadow: 0 0 10px rgba(168,85,247,0.5);"></div>',
                iconSize: [18, 18], iconAnchor: [9, 9]
            }})
        }}).addTo(map).bindPopup("<b>🏠 " + hotelName + "</b>");

        const markers = {{}};
        poiData.forEach(p => {{
            const m = L.marker(p.pos, {{
                icon: L.divIcon({{
                    className: 'custom-icon',
                    html: '<div style="background-color: ' + p.color + '; width: 14px; height: 14px; border: 2px solid white; border-radius: 50%;"></div>',
                    iconSize: [14, 14], iconAnchor: [7, 7]
                }})
            }}).addTo(map).bindPopup('<div style="font-size:11px"><b>' + p.name + '</b><br>' + p.time + '</div>');
            markers[p.id] = m;
        }});

        const container = document.getElementById('schedule-container');
        for (let d = 1; d <= numDays; d++) {{
            const section = document.createElement('section');
            section.id = 'day' + d;
            section.className = 'day-section';
            section.innerHTML = '<h2 class="text-xl mb-4 border-l-4 border-stone-800 pl-3 font-bold uppercase">' + dayNames[d - 1] + '</h2>';
            poiData.filter(p => p.day === d).forEach(p => {{
                section.innerHTML += `
                    <div class="item-card shadow-sm">
                        <div class="item-main">
                            <div class="item-img"><img src="${{p.img}}" alt="${{p.name}}" onerror="this.parentElement.innerHTML='<div style=\\'display:flex;align-items:center;justify-content:center;height:100%;color:#ccc\\'>📍</div>'"></div>
                            <div class="item-content">
                                <div class="flex justify-between items-start">
                                    <h3 class="font-bold text-sm leading-tight">${{p.name}}</h3>
                                    <span class="text-[9px] bg-stone-100 px-1.5 py-0.5 rounded font-bold">${{p.time}}</span>
                                    ${{p.duration ? '<span class="text-[9px] bg-stone-50 px-1.5 py-0.5 rounded text-stone-400">⏱ ' + p.duration + '</span>' : ''}}
                                </div>
                                <p class="text-[10px] text-gray-500 mt-1 leading-tight">${{p.desc}}</p>
                                <p class="mt-auto text-[10px] font-extrabold text-stone-900">${{p.budget}}</p>
                                ${{p.label ? '<p class="text-[8px] font-bold text-red-600 uppercase mt-1">' + p.label + '</p>' : ''}}
                            </div>
                        </div>
                        <div class="item-actions">
                            <button onclick="openAddressModal('${{p.id}}')" class="action-btn"><i data-lucide="map-pin" size="12"></i> Adresse</button>
                            <button onclick="openTransferModal('${{p.id}}')" class="action-btn" style="background:#fffbeb;"><i data-lucide="map" size="12"></i> Trajet</button>
                            <button onclick="focusOnMap('${{p.id}}')" class="action-btn"><i data-lucide="maximize-2" size="12"></i> Carte</button>
                        </div>
                    </div>`;
            }});
            container.appendChild(section);
        }}

        lucide.createIcons();

        function openAddressModal(id) {{
            const p = poiData.find(x => x.id === id);
            document.getElementById('modal-title').innerText = p.name;
            document.getElementById('modal-address').innerText = p.address;
            document.getElementById('modal-link').href = 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(p.name + ' ' + p.address);
            document.getElementById('modal-icon').style.backgroundColor = p.color + '20';
            document.getElementById('modal-icon').innerHTML = '<i data-lucide="map-pin" style="color:' + p.color + '"></i>';
            document.getElementById('poi-modal').style.display = 'flex';
            lucide.createIcons();
        }}

        function openTransferModal(id) {{
            const p = poiData.find(x => x.id === id);
            document.getElementById('transfer-from').innerText = 'Depuis : ' + p.from;
            document.getElementById('transfer-to').innerText = 'Destination : ' + p.name;
            document.getElementById('transfer-text').innerText = p.travel;
            document.getElementById('transfer-tip').innerText = p.tip;
            document.getElementById('transfer-icon').setAttribute('data-lucide', p.travelType === 'walk' ? 'footprints' : 'car');
            document.getElementById('transfer-modal').style.display = 'flex';
            lucide.createIcons();
        }}

        function closeModal(mId) {{ document.getElementById(mId).style.display = 'none'; }}

        function focusOnMap(id) {{
            const p = poiData.find(x => x.id === id);
            document.getElementById('map-container').scrollIntoView({{ behavior: 'smooth' }});
            setTimeout(() => {{ map.setView(p.pos, 16, {{ animate: true }}); markers[id].openPopup(); }}, 500);
        }}
    </script>
</body>
</html>'''
        return html
