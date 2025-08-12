# services.py
import os
import requests
import json
import re
from datetime import datetime
import google.generativeai as genai
from bs4 import BeautifulSoup
import ftplib
import ssl
from io import BytesIO
import unidecode

class PublicationService:
    def __init__(self, config):
        self.hostname = config.get('FTP_HOSTNAME')
        self.username = config.get('FTP_USERNAME')
        self.password = config.get('FTP_PASSWORD')
        # Le chemin de base est maintenant le dossier parent
        self.base_remote_path = config.get('FTP_REMOTE_PATH', 'domains/voyages-privileges.be/public_html/')
        self.port = int(config.get('FTP_PORT', 21))
        
        print(f"📡 Configuration FTP:")
        print(f"   Serveur: {self.hostname}:{self.port}")
        print(f"   Utilisateur: {self.username}")
        print(f"   Chemin de base: {self.base_remote_path}")
        
    def _connect_ftp(self):
        # ... (Le reste de la fonction ne change pas)
        try:
            print(f"📡 Connexion FTP à {self.hostname}:{self.port}...")
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            ftp = ftplib.FTP_TLS(context=context)
            ftp.connect(self.hostname, self.port, timeout=30)
            print(f"✅ Connecté, authentification avec {self.username}...")
            ftp.login(self.username, self.password)
            ftp.prot_p()
            print("✅ Protection des données activée (FTPS)")
            ftp.set_pasv(True)
            return ftp
        except Exception as e:
            print(f"⚠️ FTPS a échoué ({e}), tentative en FTP simple...")
            try:
                ftp = ftplib.FTP()
                ftp.connect(self.hostname, self.port, timeout=30)
                ftp.login(self.username, self.password)
                print("✅ Connecté via FTP simple")
                ftp.set_pasv(True)
                return ftp
            except Exception as final_e:
                print(f"❌ Erreur de connexion FTP finale : {final_e}")
                raise

    def _navigate_to_path(self, ftp, full_path):
        """Navigue vers le répertoire de publication, le crée si nécessaire"""
        try:
            ftp.cwd(full_path)
            print(f"✅ Répertoire {full_path} trouvé")
        except:
            print(f"📁 Création du chemin {full_path}...")
            try:
                ftp.cwd('/')
            except:
                pass
            
            dirs = full_path.strip('/').split('/')
            for d in dirs:
                if d:
                    try:
                        ftp.cwd(d)
                    except:
                        try:
                            ftp.mkd(d)
                            print(f"📁 Dossier créé : {d}")
                            ftp.cwd(d)
                        except Exception as e:
                            print(f"⚠️ Impossible de créer/accéder à {d}: {e}")

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
        remote_dir = os.path.join(self.base_remote_path, 'offres/')
        
        return self._upload_file(trip, filename, remote_dir)

    def publish_client_offer(self, trip):
        """Publie une offre privée dans le dossier /clients/"""
        full_trip_data = json.loads(trip.full_data_json)
        base_filename = self._generate_base_filename(full_trip_data)
        
        # --- LIGNE CORRIGÉE POUR NETTOYER LE NOM DU CLIENT ---
        raw_name = f"{trip.client_first_name} {trip.client_last_name}"
        # Translitère les accents (ex: é -> e) et passe en minuscules
        slug = unidecode.unidecode(raw_name).lower()
        # Remplace les espaces, apostrophes et autres caractères non désirés par un underscore
        slug = re.sub(r"[\s']+", '_', slug)
        # Supprime tout caractère qui n'est pas une lettre, un chiffre ou un underscore
        client_name_slug = re.sub(r'[^a-z0-9_]', '', slug)
        
        filename = f"{base_filename}_{client_name_slug}.html"
        remote_dir = os.path.join(self.base_remote_path, 'clients/')
        
        return self._upload_file(trip, filename, remote_dir)

    def _upload_file(self, trip, filename, remote_dir):
        ftp = None
        try:
            full_trip_data = json.loads(trip.full_data_json)
            html_content = generate_travel_page_html(
                full_trip_data['form_data'],
                full_trip_data['api_data'],
                full_trip_data.get('savings', 0),
                full_trip_data.get('comparison_total', 0)
            )
            
            print(f"📤 Publication de {filename} dans {remote_dir}...")
            ftp = self._connect_ftp()
            self._navigate_to_path(ftp, remote_dir)
            
            html_bytes = BytesIO(html_content.encode('utf-8'))
            
            print(f"📤 Upload en cours...")
            ftp.storbinary(f'STOR {filename}', html_bytes)
            
            print(f"✅ Publié avec succès")
            return filename
            
        except Exception as e:
            print(f"❌ Erreur de publication : {e}")
            return None
        finally:
            if ftp:
                try:
                    ftp.quit()
                    print("📡 Connexion FTP fermée")
                except:
                    pass

    def unpublish(self, filename, is_client_offer=False):
        ftp = None
        try:
            remote_dir = os.path.join(self.base_remote_path, 'clients/' if is_client_offer else 'offres/')
            full_path = os.path.join(remote_dir, filename)
            
            print(f"🗑️ Suppression de {full_path}...")
            ftp = self._connect_ftp()
            self._navigate_to_path(ftp, remote_dir)
            ftp.delete(filename)
            print(f"✅ Fichier {filename} supprimé")
            return True
            
        except Exception as e:
            print(f"❌ Erreur de suppression : {e}")
            return False
        finally:
            if ftp:
                try:
                    ftp.quit()
                except:
                    pass
    
    # ... (Le reste du fichier RealAPIGatherer et generate_travel_page_html ne change pas)
    def test_connection(self):
        ftp = None
        try:
            print(f"\n🔍 TEST DE CONNEXION FTP")
            print(f"="*50)
            
            ftp = self._connect_ftp()
            
            print(f"\n📁 Contenu du répertoire {self.base_remote_path}:")
            self._navigate_to_path(ftp, self.base_remote_path)
            files = ftp.nlst()
            
            if files:
                for f in files:
                    print(f"   - {f}")
                print(f"\n✅ {len(files)} fichier(s) trouvé(s)")
            else:
                print("   (Répertoire vide)")
            
            test_filename = "test_connexion.txt"
            test_content = BytesIO(b"Test de connexion FTP reussi")
            
            print(f"\n📤 Test d'upload de {test_filename}...")
            ftp.storbinary(f'STOR {test_filename}', test_content)
            
            files_after = ftp.nlst()
            
            if test_filename in files_after:
                print(f"✅ Upload réussi")
                ftp.delete(test_filename)
                print(f"✅ Suppression réussie")
            
            print(f"\n✅ TOUS LES TESTS RÉUSSIS !")
            return True
            
        except Exception as e:
            print(f"\n❌ Échec du test : {e}")
            return False
            
        finally:
            if ftp:
                try:
                    ftp.quit()
                except:
                    pass

class RealAPIGatherer:
    def __init__(self):
        self.google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not self.google_api_key:
            print("❌ ERREUR CRITIQUE: Variable GOOGLE_API_KEY manquante")
        else:
            genai.configure(api_key=self.google_api_key)
            print("✅ Clé API Google chargée")

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
    stars = "⭐" * int(data['stars'])
    num_people = int(data.get('num_people', 2))
    price_for_text = f"pour {num_people} personnes" if num_people > 1 else "pour 1 personne"
    your_price = int(data.get('price', 0))
    price_per_person_text = f'<p class="text-sm font-light mt-1">soit {round(your_price / num_people)} € par personne</p>' if num_people > 0 else ""
    
    cancellation_html = f'<p class="text-xs font-light mt-1 text-center">✓ Annulation gratuite jusqu\'au {data.get("cancellation_date")}</p>' if data.get('has_cancellation') == 'on' and data.get('cancellation_date') else ""
    
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
    
    flight_price = int(data.get('flight_price', 0))
    flight_text_html = f'<div class="flex justify-between"><span>Vol {data.get("departure_city", "").split(",")[0]} ↔ {data.get("arrival_airport", data["destination"]).split(",")[0]}</span><span class="font-semibold">{flight_price}€</span></div>' if flight_price > 0 else ""
    flight_inclusion_html = f'<div class="flex items-center"><div class="feature-icon bg-blue-500"><i class="fas fa-plane"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Vol {data.get("departure_city", "").split(",")[0]} ↔ {data.get("arrival_airport", data["destination"]).split(",")[0]}</h4><p class="text-gray-600 text-xs">Aller-retour inclus</p></div></div>' if flight_price > 0 else ""
    baggage_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-red-500"><i class="fas fa-suitcase"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Bagages 10kg</h4><p class="text-gray-600 text-xs">Bagage cabine inclus</p></div></div>' if flight_price > 0 else ""

    transfer_cost = int(data.get('transfer_cost', 0))
    transfer_text_html = f'<div class="flex justify-between"><span>+ Transferts</span><span class="font-semibold">~{transfer_cost}€</span></div>' if transfer_cost > 0 else ""
    transfer_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-green-500"><i class="fas fa-bus"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Transfert aéroport ↔ hôtel</h4><p class="text-gray-600 text-xs">Prise en charge complète</p></div></div>' if transfer_cost > 0 else ""

    surcharge_cost = int(data.get('surcharge_cost', 0))
    surcharge_text_html = f'<div class="flex justify-between"><span>+ Surcoût {data.get("surcharge_type", "")}</span><span class="font-semibold">~{surcharge_cost}€</span></div>' if surcharge_cost > 0 else ""

    car_rental_cost = int(data.get('car_rental_cost', 0))
    car_rental_text_html = f'<div class="flex justify-between"><span>+ Voiture de location (sans franchise)</span><span class="font-semibold">~{car_rental_cost}€</span></div>' if car_rental_cost > 0 else ""
    car_rental_inclusion_html = '<div class="flex items-center"><div class="feature-icon bg-gray-500"><i class="fas fa-car"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Voiture de location (sans franchise)</h4><p class="text-gray-600 text-xs">Explorez à votre rythme</p></div></div>' if car_rental_cost > 0 else ""

    comparison_block = f"""
        <div class="flex justify-between"><span>Hôtel ({data.get('stars')}⭐)</span><span class="font-semibold">{data.get('booking_price', 'N/A')} €</span></div>
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
        video_html_block = f'<div id="video-section-wrapper" class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Vidéo</h3><div><h4 class="font-semibold mb-2">Visite de l\'hôtel</h4><div class="video-container aspect-w-16 aspect-h-9"><iframe src="{embed_url}" title="{video_title}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen class="w-full h-full rounded-lg"></iframe></div></div></div>'

    reviews_section = "".join([f'<div class="bg-gray-50 p-4 rounded-lg"><div><span class="font-semibold">{r["author"]}</span> <span class="text-yellow-500">{r["rating"]}</span> <span class="text-gray-500 text-sm float-right">{r.get("date", "")}</span></div><p class="mt-2 text-gray-700">"{r["text"]}"</p></div>' for r in real_data.get('reviews', [])])

    destination_section = ""
    if real_data.get('cultural_attraction_image'):
        cultural_attraction_name = real_data.get('attractions', {}).get('culture', [''])[0]
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

    footer_html = f"""
        <div class="instagram-card p-6 bg-blue-500 text-white text-center">
            <h3 class="text-2xl font-bold mb-2">🌟 Réservez votre évasion !</h3>
            <p>Les places sont très limitées pour cette offre exclusive. Pour garantir votre place :</p>
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
            <h3 class="text-xl font-semibold mb-4">📞 Contact & Infos</h3>
            <img src="https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png" alt="Logo Voyages Privilèges" class="h-12 mx-auto mb-4">
            <p class="text-gray-800">📍 Rue Winston Churchill 38, 6180 Courcelles</p>
            <p class="text-gray-800 my-2">📞 <a href="tel:+32488433344" class="text-blue-600">+32 488 43 33 44</a></p>
            <p class="text-gray-800">✉️ <a href="mailto:infos@voyages-privileges.be" class="text-blue-600">infos@voyages-privileges.be</a></p>
            <hr class="my-4">
            <p class="text-xs text-gray-500">SRL RIDEA (OldiBike)<br>Numéro de société : 1024.916.054 - RC Exploitation : 99730451</p>
        </div>
    """

    html_template = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Voyages Privilèges - {display_hotel_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Poppins:wght@300;400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com?plugins=aspect-ratio"></script>
    <style>
        body {{ font-family: 'Poppins', sans-serif; }} .section-title {{ font-family: 'Playfair Display', serif; }}
        .instagram-card {{ background: white; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; }}
        .story-card, .instagram-card + .instagram-card {{ margin-top: 20px; }}
        .story-card {{ background: linear-gradient(135deg, #3B82F6 0%, #60A5FA 100%); border-radius: 25px; padding: 25px; color: white; text-align: center; box-shadow: 0 10px 30px rgba(59, 130, 246, 0.3); margin-top: 0; }}
        .image-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }}
        .image-item img {{ width: 100%; height: 200px; object-fit: cover; transition: transform 0.3s ease; border-radius: 15px;}}
        .economy-highlight {{ background: linear-gradient(45deg, #ffd700, #ffb347); color: #333; padding: 15px; border-radius: 15px; text-align: center; margin-top: 20px; font-weight: bold;}}
        .feature-icon {{ width: 45px; height: 45px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0; }}
        .modal-photos {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 1000; overflow-y: auto; padding: 20px; }}
        .modal-photos-content {{ max-width: 800px; margin: 0 auto; padding-top: 60px; }}
        .close-photos {{ position: fixed; top: 20px; right: 30px; font-size: 40px; color: white; cursor: pointer; z-index: 1001; font-weight: bold; width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.5); border-radius: 50%; }}
        .close-photos:hover {{ background: rgba(255,255,255,0.2); }}
        .modal-photo {{ width: 100%; margin-bottom: 20px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }}
        .photo-counter {{ position: fixed; top: 20px; left: 30px; color: white; background: rgba(0,0,0,0.5); padding: 10px 15px; border-radius: 20px; font-weight: bold; z-index: 1001; }}
        @media (max-width: 768px) {{ .close-photos {{ top: 15px; right: 15px; font-size: 30px; width: 40px; height: 40px; }} .photo-counter {{ top: 15px; left: 15px; padding: 8px 12px; font-size: 14px; }} .modal-photos-content {{ padding-top: 80px; padding-left: 10px; padding-right: 10px; }} }}
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: auto; padding: 10px;">
        <div style="text-align: center; padding-top: 20px; padding-bottom: 10px;">
            <img src="https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png" alt="Logo Voyages Privilèges" style="max-height: 50px; margin: auto;">
        </div>
        <div class="story-card">
            <img src="{real_data['photos'][0] if real_data['photos'] else ''}" alt="{data['hotel_name']}" style="width: 100%; height: 256px; object-fit: cover; border-radius: 8px; margin-bottom: 1rem;">
            <h2 class="text-2xl font-bold">{display_hotel_name} {stars}</h2>
            <p>📍 {display_address}</p>
            <p class="mt-4">🗓️ Du {date_start} au {date_end}</p>
            <div class="text-4xl font-bold mt-2">{data['price']} €</div>
            <p>{price_for_text}</p>{price_per_person_text}
            {f'<p class="text-sm mt-2">Note Google: {real_data["hotel_rating"]}/5 ({real_data["total_reviews"]} avis)</p>' if real_data.get("hotel_rating", 0) > 0 else ""}
            <div class="mt-4">{instagram_button_html}</div>
        </div>
        <div class="instagram-card p-6">
            <h3 class="section-title text-xl mb-4">Inclus dans votre séjour</h3>
            <div class="space-y-5">{flight_inclusion_html}{transfer_inclusion_html}{car_rental_inclusion_html}
                <div class="flex items-center"><div class="feature-icon bg-purple-500"><i class="fas fa-hotel"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">Hôtel {stars} {display_hotel_name}</h4><p class="text-gray-600 text-xs">Style traditionnel</p></div></div>
                <div class="flex items-center"><div class="feature-icon bg-yellow-500"><i class="fas fa-utensils"></i></div><div class="ml-4"><h4 class="font-semibold text-sm">{data.get('surcharge_type', 'Pension complète')}</h4><p class="text-gray-600 text-xs">Inclus dans le forfait</p></div></div>
                {baggage_inclusion_html}
            </div>
        </div>
        <div class="instagram-card p-6">
            <h3 class="section-title text-xl mb-4">Pourquoi nous choisir ?</h3>
            <div class="p-4 rounded-lg border-2 border-red-200 bg-red-50 mb-4"><h4 class="font-bold text-center mb-2">Prix estimé ailleurs</h4><div class="text-sm space-y-1">{comparison_block}</div></div>{exclusive_services_html}
            <div class="p-4 rounded-lg bg-green-600 text-white"><h4 class="font-bold text-center mb-2">Notre Offre</h4><div class="text-center text-2xl font-bold">{data['price']} €</div>{cancellation_html}</div>
            <div class="economy-highlight">💰 Vous économisez {savings} € !</div>
        </div>
        <div class="instagram-card p-6" id="gallery-section"><h3 class="section-title text-xl mb-4">Galerie de photos</h3><div class="image-grid">{image_gallery}</div>{more_photos_button}</div>
        <div id="photosModal" class="modal-photos"><span class="close-photos" id="closePhotos">×</span><div class="photo-counter" id="photoCounter">Photo 1 sur {total_photos}</div><div class="modal-photos-content">{modal_all_photos}</div></div>
        {video_html_block}
        <div class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Avis des clients</h3><div class="space-y-4">{reviews_section}</div></div>
        <div class="instagram-card p-6"><h3 class="section-title text-xl mb-4">Découvrir {city_name}</h3>{destination_section}</div>
        {footer_html}
    </div>
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const voirPlusBtn = document.getElementById('voirPlusPhotos');
        const modal = document.getElementById('photosModal');
        const closeBtn = document.getElementById('closePhotos');
        const photoCounter = document.getElementById('photoCounter');
        const modalPhotos = document.querySelectorAll('.modal-photo');
        if (voirPlusBtn) {{ voirPlusBtn.addEventListener('click', function() {{ if (modal) modal.style.display = 'block'; document.body.style.overflow = 'hidden'; }}); }}
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
    }});
    </script>
</body>
</html>"""
    return html_template
