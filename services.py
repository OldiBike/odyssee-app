# services.py
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
    def __init__(self, config):
        # Configuration API
        self.api_url = 'https://www.voyages-privileges.be/api/upload.php'
        self.api_key = 'SecretUploadKey2025'
        
        print(f"📡 Configuration Publication:")
        print(f"   Mode: API HTTP (Railway compatible)")
        print(f"   API URL: {self.api_url}")
        
    def _upload_via_api(self, filename, html_content, directory):
        """Upload via l'API PHP sur Hostinger"""
        try:
            print(f"📤 Upload via API: {filename} vers {directory}/")
            
            payload = {
                'filename': filename,
                'content': base64.b64encode(html_content.encode('utf-8')).decode('utf-8'),
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
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Upload réussi: {result.get('url', '')}")
                return True
            else:
                print(f"❌ Erreur API: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Erreur upload API: {e}")
            return False
    
    def _generate_base_filename(self, trip_data):
        hotel_name = trip_data['form_data']['hotel_name'].split(',')[0].strip()
        date_start = trip_data['form_data']['date_start']
        date_end = trip_data['form_data']['date_end']
        
        base_name = unidecode.unidecode(hotel_name).lower()
        base_name = re.sub(r'[^a-z0-9]+', '_', base_name).strip('_')
        
        return f"{base_name}_{date_start}_{date_end}"

    def publish_public_offer(self, trip):
        """Publie une offre dans le dossier public /offres/"""
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

    def publish_client_offer(self, trip):
        """Publie une offre privée dans le dossier /clients/"""
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

    def unpublish(self, filename, is_client_offer=False):
        """Supprime un fichier publié via l'API"""
        try:
            directory = 'clients' if is_client_offer else 'offres'
            print(f"🗑️ Suppression via API: {filename} dans {directory}/")
            
            payload = {
                'filename': filename,
                'directory': directory
            }
            
            headers = {
                'Content-Type': 'application/json',
                'X-Api-Key': self.api_key
            }
            
            response = requests.delete(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            print(f"🔍 Réponse API DELETE: Status={response.status_code}, Body={response.text}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"✅ Suppression réussie: {filename}")
                    return True
            
            print(f"❌ Erreur suppression: {response.status_code}")
            return False
                
        except Exception as e:
            print(f"❌ Erreur suppression API: {e}")
            return False
    
    def test_connection(self):
        """Test de connexion à l'API"""
        try:
            print("\n🔍 TEST DE CONNEXION API")
            print("="*50)
            
            headers = {'X-Api-Key': self.api_key}
            response = requests.get(self.api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"✅ API connectée: {result.get('message')}")
                    print(f"   PHP Version: {result.get('php_version')}")
                    print(f"   Timestamp: {result.get('timestamp')}")
                    return True
            
            print(f"❌ Erreur connexion API: {response.status_code}")
            return False
                
        except Exception as e:
            print(f"❌ Erreur test: {e}")
            return False

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
    hotel_name_full = data.get('hotel_name', '')
    hotel_name_parts = hotel_name_full.split(',')
    display_hotel_name = hotel_name_parts[0].strip()
    display_address = ', '.join(hotel_name_parts[1:]).strip() if len(hotel_name_parts) > 1 else data.get('destination', '')

    date_start = datetime.strptime(data['date_start'], '%Y-%m-%d').strftime('%d %B %Y')
    date_end = datetime.strptime(data['date_end'], '%Y-%m-%d').strftime('%d %B %Y')
    stars = "⭐" * int(data.get('stars', 0))
    num_people = int(data.get('num_people') or 2)
    price_for_text = f"pour {num_people} personnes" if num_people > 1 else "pour 1 personne"
    
    your_price = int(data.get('pack_price') or 0)
    price_per_person_text = f'<p class="text-sm font-light mt-1">soit {round(your_price / num_people)} € par personne</p>' if num_people > 0 else ""
    
    is_ultra_budget = data.get('is_ultra_budget', False)

    cancellation_html = ""
    flight_price = int(data.get('flight_price') or 0)
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
    
    flight_text_html = f'<div class="flex justify-between"><span>Vol {data.get("departure_city", "").split(",")[0]} ↔ {data.get("arrival_airport", data["destination"]).split(",")[0]}</span><span class="font-semibold">{flight_price}€</span></div>' if flight_price > 0 else ""
    flight_inclusion_html = f'<div class="flex items-center"><div class="feature-icon bg-blue-500"><i class="fas fa-plane"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Vol {data.get("departure_city", "").split(",")[0]} ↔ {data.get("arrival_airport", data["destination"]).split(",")[0]}</h4><p class="text-gray-600 text-xs">Aller-retour inclus</p></div></div>' if flight_price > 0 else ""
    
    baggage_option = data.get('baggage_type', 'bagages 10 kilos')
    baggage_inclusion_html = ''
    if baggage_option == 'bagages 10 kilos':
        baggage_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-red-500"><i class="fas fa-suitcase"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Bagage 10 kilos</h4><p class="text-gray-600 text-xs">1 bagage inclus par personne en cabine</p></div></div>'
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

    ultra_budget_warning_html = ''
    if is_ultra_budget:
        ultra_budget_warning_html = '''
        <div class="mt-4 p-3 rounded-lg border-2 border-red-200 bg-red-50 text-sm">
            <h4 class="font-bold text-red-800 mb-2">⚠️ Offre Ultra Budget</h4>
            <p class="text-xs text-red-700">Tarif minimum avec conditions (pas de bagage cabine, caution voiture élevée, hôtel non remboursable, horaires de vols non optimisés).</p>
            <p class="text-xs text-blue-700 mt-2">💡 Possibilité d’ajouter des services à la carte sur demande.</p>
        </div>
        '''

    car_rental_cost = int(data.get('car_rental_cost') or 0)
    car_rental_text_html = f'<div class="flex justify-between"><span>+ Voiture de location (sans franchise)</span><span class="font-semibold">~{car_rental_cost}€</span></div>' if car_rental_cost > 0 else ""
    car_rental_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-gray-500"><i class="fas fa-car"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Voiture de location (sans franchise)</h4><p class="text-gray-600 text-xs">Explorez à votre rythme</p></div></div>' if car_rental_cost > 0 else ""

    comparison_block = f"""
        <div class="flex justify-between"><span>Hôtel ({data.get('stars')}⭐)</span><span class="font-semibold">{data.get('hotel_b2c_price', 'N/A')} €</span></div>
        {flight_text_html}{transfer_text_html}{car_rental_text_html}{surcharge_text_html}
        <hr class="my-3"><div class="flex justify-between text-base font-bold text-red-600"><span>TOTAL ESTIMÉ</span><span>{comparison_total} €</span></div>
    """
    
    total_photos = len(real_data['photos'])
    image_gallery = "".join([f'<div class="image-item"><img src="{url}" alt="Photo de {data["hotel_name"]}"></div>' for url in real_data['photos'][:6]]) or '<p>Aucune photo disponible.</p>'
    more_photos_button = f'<div class="text-center mt-4"><button id="voirPlusPhotos" class="bg-blue-500 hover:bg-blue-600 text-white font-semibold py-3 px-6 rounded-full transition-colors">📸 Voir plus de photos ({total_photos} au total)</button></div>' if total_photos > 6 else ""
    modal_all_photos = "".join([f'<img src="{url}" alt="Photo {i+1} de {data["hotel_name"]}" class="modal-photo">' for i, url in enumerate(real_data['photos'])])

    video_html_block = ""
    if real_data.get('videos'):
        embed_url = f"https://www.youtube.com/embed/{real_data['videos'][0]['id']}"
        video_title = real_data['videos'][0]['title']
        video_html_block = f"""<div id="video-section-wrapper" class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Vidéo</h3><div><h4 class="font-semibold mb-2">Visite de l'hôtel</h4><div class="video-container aspect-w-16 aspect-h-9"><iframe src="{embed_url}" title="{video_title}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen class="w-full h-full rounded-lg"></iframe></div></div></div>"""

    reviews_section = "".join([f'<div class="bg-gray-50 p-4 rounded-lg"><div><span class="font-semibold">{r["author"]}</span> <span class="text-yellow-500">{r["rating"]}</span> <span class="text-gray-500 text-sm float-right">{r.get("date", "")}</span></div><p class="mt-2 text-gray-700">"{r["text"]}"</p></div>' for r in real_data.get('reviews', [])])

    destination_section = ""
