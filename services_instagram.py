# services_instagram.py - Générateur de carousel Instagram Voyages Privilèges (Version Finale Corrigée)
import os
from datetime import datetime
import google.generativeai as genai
import urllib.parse
import requests

# --- DÉBUT DES CLASSES UTILITAIRES ---

# Classe pour récupérer les images des attractions
class RealAPIGatherer:
    """Récupère les données réelles depuis les APIs de Google."""
    def __init__(self):
        self.google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not self.google_api_key:
            print("❌ ERREUR CRITIQUE: Variable GOOGLE_API_KEY manquante dans RealAPIGatherer")

    def get_attraction_image(self, attraction_name, destination):
        if not self.google_api_key: return None
        print(f"ℹ️ [Instagram] Recherche d'image pour : {attraction_name}")
        try:
            search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            search_params = {
                'query': f'"{attraction_name}" "{destination}"',
                'key': self.google_api_key,
                'fields': 'photos'
            }
            search_response = requests.get(search_url, params=search_params, timeout=10)
            if search_response.status_code == 200:
                search_data = search_response.json()
                if search_data.get('results') and search_data['results'][0].get('photos'):
                    photo_reference = search_data['results'][0]['photos'][0].get('photo_reference')
                    if photo_reference:
                        return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={photo_reference}&key={self.google_api_key}"
            return None
        except Exception as e:
            print(f"❌ Erreur API Image Attraction (Instagram): {e}")
            return None

# --- FIN DES CLASSES UTILITAIRES ---


class InstagramCarouselVP:
    """Génère un carousel Instagram avec l'identité visuelle Voyages Privilèges"""
    
    def __init__(self):
        self.slide_width = 1080
        self.slide_height = 1080
        
        self.colors = {
            'bleu_principal': '#3B82F6',
            'bleu_secondaire': '#60A5FA',
            'bleu_pastel': '#A7C7E7',
            'bleu_tres_clair': '#DBEAFE',
            'or': '#FFD700',
            'blanc': '#FFFFFF',
            'gris_clair': '#F8FAFC',
            'texte_fonce': '#1E293B',
            'rouge_budget': '#EF4444'
        }
    
    def generate_dynamic_title(self, destination, date_start, date_end):
        """Génère un titre dynamique pour le slide de la galerie."""
        try:
            google_api_key = os.environ.get('GOOGLE_API_KEY')
            if not google_api_key: return "Un Aperçu du Séjour"

            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            
            start = datetime.strptime(date_start, '%Y-%m-%d')
            end = datetime.strptime(date_end, '%Y-%m-%d')
            duration = (end - start).days
            
            prompt = f"""
Crée un titre très court (4 mots maximum) et inspirant pour une galerie de photos de voyage.
Le voyage est à destination de "{destination}" et dure {duration} jours.
Adapte le style du titre au contexte. Par exemple, "Échappée Belle à Rome" pour un court city-trip, ou "Le Paradis des Maldives" pour un long séjour sur une île.
Sois créatif et percutant. N'ajoute pas d'émojis.
Réponds UNIQUEMENT avec le titre.
"""
            response = model.generate_content(prompt)
            return response.text.strip().replace('"', '')
        except Exception as e:
            print(f"⚠️ Erreur Gemini (titre dynamique), utilisation du titre par défaut: {e}")
            return "Un Aperçu du Séjour"

    def generate_caption_and_hashtags(self, trip_data):
        # Le code pour la légende et les hashtags reste inchangé
        try:
            google_api_key = os.environ.get('GOOGLE_API_KEY')
            if not google_api_key:
                return self._get_fallback_caption(trip_data), self._get_fallback_hashtags(trip_data)
            
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            
            hotel_name = trip_data.get('hotel_name', 'Hôtel').split(',')[0].strip()
            destination = trip_data.get('destination', 'Destination')
            price = int(trip_data.get('pack_price', 0))
            num_people = int(trip_data.get('num_people', 2))
            date_start_str = datetime.strptime(trip_data['date_start'], '%Y-%m-%d').strftime('%d %B')
            date_end_str = datetime.strptime(trip_data['date_end'], '%Y-%m-%d').strftime('%d %B %Y')
            
            inclusions = []
            if int(trip_data.get('flight_price', 0)) > 0: inclusions.append('Vols A/R')
            if int(trip_data.get('transfer_cost', 0)) > 0: inclusions.append('Transferts aéroport')
            inclusions.append(trip_data.get('surcharge_type', 'Pension complète'))
            
            caption_prompt = f"Crée une légende Instagram captivante (max 120 mots, 3-4 emojis) pour une offre à l'hôtel {hotel_name} ({trip_data.get('stars', 4)}⭐) à {destination}, du {date_start_str} au {date_end_str} pour {price}€ pour {num_people} personnes. Inclus : {', '.join(inclusions)}. Termine par 'Places limitées' et les coordonnées 📞 +32 488 43 33 44. NE PAS inclure de hashtags."
            
            caption_response = model.generate_content(caption_prompt)
            caption = caption_response.text.strip()
            
            hashtags_prompt = f"Génère 12 hashtags Instagram (français/anglais, niches) pour un voyage à {destination}. Inclure #VoyagesPrivileges. Réponds UNIQUEMENT avec les hashtags espacés."
            
            hashtags_response = model.generate_content(hashtags_prompt)
            hashtags = hashtags_response.text.strip()
            
            return caption, hashtags
            
        except Exception as e:
            print(f"⚠️ Erreur Gemini, utilisation des textes par défaut: {e}")
            return self._get_fallback_caption(trip_data), self._get_fallback_hashtags(trip_data)

    def _get_fallback_caption(self, trip_data):
        hotel_name = trip_data.get('hotel_name', 'Hôtel').split(',')[0].strip()
        destination = trip_data.get('destination', 'Destination')
        price = int(trip_data.get('pack_price', 0))
        num_people = int(trip_data.get('num_people', 2))
        return f"🌴 Évadez-vous à {hotel_name} !\n✨ Offre exclusive {destination}\n💰 Seulement {price}€ pour {num_people} personne{'s' if num_people > 1 else ''}\n\n✅ Vols inclus\n✅ Transferts inclus\n✅ Formule tout compris\n\n📆 Places limitées !\n📞 Réservez maintenant : +32 488 43 33 44\n✉️ infos@voyages-privileges.be"

    def _get_fallback_hashtags(self, trip_data):
        destination = trip_data.get('destination', 'Destination').split(',')[0].strip()
        return f"#VoyagesPrivileges #{destination.replace(' ', '')} #VoyageDeReve #TravelDeals #VacancesExclusives #OffreVoyage #EvasionParfaite #TravelGram #Wanderlust #VoyagePasCher #BonPlanVoyage #AgenceDeVoyages"
    
    def generate_carousel_html(self, trip_data, api_data):
        """Génère le HTML des 5 slides du carousel"""
        
        hotel_name = trip_data.get('hotel_name', 'Hôtel').split(',')[0].strip()
        destination = trip_data.get('destination', 'Destination')
        price = int(trip_data.get('pack_price', 0))
        num_people = int(trip_data.get('num_people', 2))
        stars = "⭐" * int(trip_data.get('stars', 4))
        date_start = datetime.strptime(trip_data['date_start'], '%Y-%m-%d').strftime('%d %b')
        date_end = datetime.strptime(trip_data['date_end'], '%Y-%m-%d').strftime('%d %b %Y')
        is_ultra_budget = trip_data.get('is_ultra_budget', False)
        
        photos = api_data.get('photos', [])
        proxied_photos = [f'/api/image-proxy?url={urllib.parse.quote(p)}' for p in photos]
        logo_url = "https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png"
        proxied_logo_url = f'/api/image-proxy?url={urllib.parse.quote(logo_url)}'
        
        inclusions_html = []
        if int(trip_data.get('flight_price', 0)) > 0: inclusions_html.append('<div class="inclusion-item"><div class="icon">✈️</div><div class="text">Vols A/R inclus</div></div>')
        if int(trip_data.get('transfer_cost', 0)) > 0: inclusions_html.append('<div class="inclusion-item"><div class="icon">🚐</div><div class="text">Transferts aéroport</div></div>')
        if int(trip_data.get('car_rental_cost', 0)) > 0: inclusions_html.append('<div class="inclusion-item"><div class="icon">🚗</div><div class="text">Location de voiture</div></div>')
        inclusions_html.append(f'<div class="inclusion-item"><div class="icon">🍽️</div><div class="text">{trip_data.get("surcharge_type", "Pension complète")}</div></div>')
        
        attractions_html = []
        gatherer = RealAPIGatherer()
        all_attractions = [attr for cat in api_data.get('attractions', {}).values() for attr in cat]
        for attr_name in all_attractions[:4]:
            image_url = gatherer.get_attraction_image(attr_name, destination)
            if image_url:
                proxied_image_url = f'/api/image-proxy?url={urllib.parse.quote(image_url)}'
                attractions_html.append(f'<div class="attraction-card" style="background-image: url(\'{proxied_image_url}\');"><div class="attraction-overlay"></div><div class="name">{attr_name}</div></div>')

        ultra_budget_badge = '<div class="ultra-budget-badge">⚠️ ULTRA BUDGET</div>' if is_ultra_budget else ''
        dynamic_title = self.generate_dynamic_title(destination, trip_data['date_start'], trip_data['date_end'])
        
        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Poppins', sans-serif; }}
        .slide {{ width: {self.slide_width}px; height: {self.slide_height}px; position: relative; overflow: hidden; background: {self.colors['blanc']}; }}
        
        .slide-1 h1 {{ font-size: 52px; font-weight: 700; margin-bottom: 15px; line-height: 1.2; }}
        .slide-1 .hero-image {{ width: 100%; height: 100%; object-fit: cover; }}
        .slide-1 .overlay {{ position: absolute; bottom: 0; width: 100%; height: 50%; background: linear-gradient(to top, rgba(0,0,0,0.85), transparent); padding: 50px; color: {self.colors['blanc']}; display: flex; flex-direction: column; justify-content: flex-end; }}
        .slide-1 .logo-top {{ position: absolute; top: 30px; left: 30px; max-width: 180px; filter: brightness(0) invert(1); }}
        .slide-1 .location, .slide-1 .dates, .slide-1 .price, .slide-1 .price-label {{ text-shadow: 0 2px 8px rgba(0,0,0,0.5); }}
        .slide-1 .location {{ font-size: 28px; margin-bottom: 25px; font-weight: 300; }}
        .slide-1 .dates {{ font-size: 22px; margin-bottom: 20px; opacity: 0.9; }}
        .slide-1 .price {{ font-size: 72px; font-weight: 700; color: {self.colors['or']}; line-height: 1; }}
        .slide-1 .price-label {{ font-size: 20px; opacity: 0.85; margin-top: 8px; }}
        .ultra-budget-badge {{ position: absolute; top: 30px; right: 30px; background: {self.colors['rouge_budget']}; color: white; padding: 8px 16px; border-radius: 8px; font-size: 14px; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}

        .slide-2 {{ position: relative; background-size: cover; background-position: center; }}
        .slide-2::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(248, 250, 252, 0.85); z-index: 1; }}
        .slide-2 > * {{ position: relative; z-index: 2; }}
        .slide-2-content {{ padding: 70px 60px; display: flex; flex-direction: column; height: 100%; }}
        .slide-2 h2 {{ font-size: 48px; font-weight: 700; color: {self.colors['bleu_principal']}; text-align: center; margin-bottom: 50px; }}
        .slide-2 .hotel-card {{ background: {self.colors['blanc']}; padding: 30px; border-radius: 20px; margin-bottom: 30px; box-shadow: 0 4px 20px rgba(59, 130, 246, 0.1); text-align: center; }}
        .slide-2 .hotel-card .stars {{ font-size: 32px; margin-bottom: 10px; }}
        .slide-2 .hotel-card .name {{ font-size: 28px; font-weight: 600; color: {self.colors['texte_fonce']}; }}
        .inclusion-item {{ background: {self.colors['blanc']}; padding: 20px 30px; margin-bottom: 15px; border-radius: 15px; display: flex; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        .inclusion-item .icon {{ font-size: 36px; margin-right: 20px; width: 50px; text-align: center; }}
        .inclusion-item .text {{ font-size: 22px; font-weight: 500; color: {self.colors['texte_fonce']}; }}
        .slide-2 .logo-bottom {{ margin-top: auto; text-align: center; }}
        .slide-2 .logo-bottom img {{ max-width: 160px; opacity: 0.6; }}

        .slide-3 {{ position: relative; background-size: cover; background-position: center; }}
        .slide-3::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255, 255, 255, 0.9); z-index: 1; }}
        .slide-3-content {{ position: relative; z-index: 2; padding: 60px; display: flex; flex-direction: column; height: 100%; }}
        .slide-3 .header {{ text-align: center; margin-bottom: 40px; }}
        .slide-3 .header h2 {{ font-size: 48px; font-weight: 700; color: {self.colors['bleu_principal']}; }}
        .slide-3 .gallery-grid {{ flex: 1; display: grid; grid-template-columns: 5fr 4fr; grid-template-rows: 1fr 1fr; gap: 20px; height: 720px; }}
        .gallery-item {{ border-radius: 20px; overflow: hidden; background-size: cover; background-position: center; }}
        .item-1 {{ grid-column: 1 / 2; grid-row: 1 / 3; }}
        .item-2 {{ grid-column: 2 / 3; grid-row: 1 / 2; }}
        .item-3 {{ grid-column: 2 / 3; grid-row: 2 / 3; }}
        .slide-3 .logo-bottom {{ margin-top: 30px; text-align: center; }}
        .slide-3 .logo-bottom img {{ max-width: 160px; opacity: 0.6; }}
        
        .slide-4 {{ position: relative; background-size: cover; background-position: center; }}
        .slide-4::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255, 255, 255, 0.9); z-index: 1; }}
        .slide-4-content {{ position: relative; z-index: 2; padding: 70px 60px; display: flex; flex-direction: column; height: 100%; }}
        .slide-4 h2 {{ font-size: 48px; font-weight: 700; color: {self.colors['bleu_principal']}; text-align: center; margin-bottom: 50px; }}
        .attractions-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 25px; flex: 1; }}
        .attraction-card {{ position: relative; border-radius: 20px; overflow: hidden; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.1); background-size: cover; background-position: center; color: {self.colors['blanc']}; display: flex; align-items: flex-end; padding: 25px; }}
        .attraction-overlay {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(to top, rgba(0,0,0,0.7), transparent 60%); }}
        .attraction-card .name {{ font-size: 22px; font-weight: 600; line-height: 1.3; position: relative; z-index: 2; }}
        .slide-4 .logo-bottom {{ margin-top: 30px; text-align: center; }}
        .slide-4 .logo-bottom img {{ max-width: 160px; opacity: 0.6; }}

        .slide-5 {{ background: {self.colors['bleu_pastel']}; padding: 80px 60px; display: flex; flex-direction: column; justify-content: center; align-items: center; color: {self.colors['texte_fonce']}; text-align: center; }}
        .slide-5 h2, .slide-5 .urgency, .slide-5 .contact-info, .slide-5 .website {{ letter-spacing: normal; }}
        .slide-5 h2 {{ font-size: 56px; font-weight: 700; margin-bottom: 30px; text-shadow: none; }}
        .slide-5 .urgency {{ font-size: 32px; margin-bottom: 50px; background: rgba(255, 255, 255, 0.4); padding: 18px 40px; border-radius: 50px; font-weight: 500; }}
        .slide-5 .logo-main {{ max-width: 300px; margin-bottom: 60px; }}
        .slide-5 .contact-info {{ font-size: 28px; line-height: 1.6; font-weight: 400; }}
        .slide-5 .contact-info strong {{ font-weight: 600; }}
        .slide-5 .website {{ margin-top: 40px; font-size: 24px; color: {self.colors['texte_fonce']}; font-weight: 600; text-decoration: none; opacity: 0.8; }}
    </style>
</head>
<body>

<div class="slide slide-1">
    <img src="{proxied_photos[0] if proxied_photos else ''}" alt="{hotel_name}" class="hero-image" crossorigin="anonymous">
    <img src="{proxied_logo_url}" alt="Logo VP" class="logo-top" crossorigin="anonymous">
    {ultra_budget_badge}
    <div class="overlay">
        <h1>{hotel_name}</h1>
        <div class="location">📍 {destination}</div>
        <div class="dates">{date_start} - {date_end}</div>
        <div class="price">{price}€</div>
        <div class="price-label">pour {num_people} personne{'s' if num_people > 1 else ''}</div>
    </div>
</div>

<div class="slide slide-2" style="background-image: url('{proxied_photos[1] if len(proxied_photos) > 1 else ''}');">
    <div class="slide-2-content">
        <h2>✨ Ce qui est compris</h2>
        <div class="hotel-card">
            <div class="stars">{stars}</div>
            <div class="name">{hotel_name}</div>
        </div>
        {''.join(inclusions_html)}
        <div class="logo-bottom"><img src="{proxied_logo_url}" alt="Logo VP" crossorigin="anonymous"></div>
    </div>
</div>

<div class="slide slide-3" style="background-image: url('{proxied_photos[4] if len(proxied_photos) > 4 else (proxied_photos[0] if proxied_photos else '')}');">
    <div class="slide-3-content">
        <div class="header">
            <h2>{dynamic_title}</h2>
        </div>
        <div class="gallery-grid">
            <div class="gallery-item item-1" style="background-image: url('{proxied_photos[2] if len(proxied_photos) > 2 else ''}');"></div>
            <div class="gallery-item item-2" style="background-image: url('{proxied_photos[3] if len(proxied_photos) > 3 else ''}');"></div>
            <div class="gallery-item item-3" style="background-image: url('{f"/api/image-proxy?url={urllib.parse.quote(api_data.get('cultural_attraction_image'))}" if api_data.get('cultural_attraction_image') else (proxied_photos[5] if len(proxied_photos) > 5 else '')}');"></div>
        </div>
        <div class="logo-bottom"><img src="{proxied_logo_url}" alt="Logo VP" crossorigin="anonymous"></div>
    </div>
</div>

<div class="slide slide-4" style="background-image: url('{proxied_photos[1] if len(proxied_photos) > 1 else ''}');">
    <div class="slide-4-content">
        <h2>🌴 À Découvrir</h2>
        <div class="attractions-grid">{''.join(attractions_html)}</div>
        <div class="logo-bottom"><img src="{proxied_logo_url}" alt="Logo VP" crossorigin="anonymous"></div>
    </div>
</div>

<div class="slide slide-5">
    <h2>🌟 Réservez Maintenant !</h2>
    <div class="urgency">Places limitées</div>
    <img src="{proxied_logo_url}" alt="Logo VP" class="logo-main" crossorigin="anonymous">
    <div class="contact-info">
        📞 <strong>+32 488 43 33 44</strong><br>
        ✉️ infos@voyages-privileges.be
    </div>
    <div class="website">www.voyages-privileges.be</div>
</div>

</body>
</html>"""
        
        return html

def generate_instagram_carousel(trip_data, api_data):
    """Fonction principale pour générer le carousel Instagram complet"""
    generator = InstagramCarouselVP()
    html = generator.generate_carousel_html(trip_data, api_data)
    caption, hashtags = generator.generate_caption_and_hashtags(trip_data)
    
    return {
        'html': html,
        'caption': caption,
        'hashtags': hashtags
    }
