# services_instagram.py - Générateur de carousel Instagram Voyages Privilèges (CORRIGÉ)
import os
from datetime import datetime
import google.generativeai as genai
import urllib.parse

class InstagramCarouselVP:
    """Génère un carousel Instagram avec l'identité visuelle Voyages Privilèges"""
    
    def __init__(self):
        self.slide_width = 1080
        self.slide_height = 1080
        
        # Charte graphique Voyages Privilèges
        self.colors = {
            'bleu_principal': '#3B82F6',
            'bleu_secondaire': '#60A5FA',
            'bleu_tres_clair': '#DBEAFE',
            'or': '#FFD700',
            'blanc': '#FFFFFF',
            'gris_clair': '#F8FAFC',
            'texte_fonce': '#1E293B',
            'rouge_budget': '#EF4444'
        }
    
    def generate_caption_and_hashtags(self, trip_data):
        """Génère la légende Instagram et les hashtags avec Gemini"""
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
            date_start = datetime.strptime(trip_data['date_start'], '%Y-%m-%d').strftime('%d %B')
            date_end = datetime.strptime(trip_data['date_end'], '%Y-%m-%d').strftime('%d %B %Y')
            
            inclusions = []
            if int(trip_data.get('flight_price', 0)) > 0:
                inclusions.append('Vols A/R')
            if int(trip_data.get('transfer_cost', 0)) > 0:
                inclusions.append('Transferts aéroport')
            inclusions.append(trip_data.get('surcharge_type', 'Pension complète'))
            
            caption_prompt = f"""
Crée une légende Instagram captivante et professionnelle pour cette offre de voyage :

INFORMATIONS :
- Hôtel : {hotel_name} ({trip_data.get('stars', 4)}⭐)
- Destination : {destination}
- Prix : {price}€ pour {num_people} personne{'s' if num_people > 1 else ''}
- Dates : Du {date_start} au {date_end}
- Inclus : {', '.join(inclusions)}

CONSIGNES :
- Ton enthousiaste mais professionnel (agence de voyages)
- Maximum 120 mots
- Utiliser 3-4 émojis pertinents (pas trop)
- Inclure un appel à l'action clair
- Mentionner "Places limitées"
- Finir par les coordonnées : 📞 +32 488 43 33 44

NE PAS inclure de hashtags dans la légende.
"""
            
            caption_response = model.generate_content(caption_prompt)
            caption = caption_response.text.strip()
            
            hashtags_prompt = f"""
Génère une liste de 12 hashtags Instagram optimisés pour cette offre de voyage vers {destination}.
CONSIGNES :
- Mix de hashtags populaires et niches
- En français ET en anglais
- Inclure : #VoyagesPrivileges
- Format : liste avec # devant chaque mot
- Pas de hashtags trop génériques (#travel #voyage)
- Focus sur la destination, le type de voyage

Réponds UNIQUEMENT avec la liste de hashtags séparés par des espaces.
"""
            
            hashtags_response = model.generate_content(hashtags_prompt)
            hashtags = hashtags_response.text.strip()
            
            return caption, hashtags
            
        except Exception as e:
            print(f"⚠️ Erreur Gemini, utilisation des textes par défaut: {e}")
            return self._get_fallback_caption(trip_data), self._get_fallback_hashtags(trip_data)
    
    def _get_fallback_caption(self, trip_data):
        """Légende de secours si Gemini ne fonctionne pas"""
        hotel_name = trip_data.get('hotel_name', 'Hôtel').split(',')[0].strip()
        destination = trip_data.get('destination', 'Destination')
        price = int(trip_data.get('pack_price', 0))
        num_people = int(trip_data.get('num_people', 2))
        
        return f"""🌴 Évadez-vous à {hotel_name} !
✨ Offre exclusive {destination}
💰 Seulement {price}€ pour {num_people} personne{'s' if num_people > 1 else ''}

✅ Vols inclus
✅ Transferts inclus
✅ Formule tout compris

📆 Places limitées !
📞 Réservez maintenant : +32 488 43 33 44
✉️ infos@voyages-privileges.be"""
    
    def _get_fallback_hashtags(self, trip_data):
        """Hashtags de secours"""
        destination = trip_data.get('destination', 'Destination').split(',')[0].strip()
        return f"#VoyagesPrivileges #{destination.replace(' ', '')} #VoyageDeReve #TravelDeals #VacancesExclusives #OffreVoyage #EvasionParfaite #TravelGram #Wanderlust #VoyagePasCher #BonPlanVoyage #AgenceDeVoyages"
    
    def generate_carousel_html(self, trip_data, api_data):
        """Génère le HTML des 4 slides du carousel"""
        
        hotel_name_full = trip_data.get('hotel_name', 'Hôtel')
        hotel_name = hotel_name_full.split(',')[0].strip()
        destination = trip_data.get('destination', 'Destination')
        price = int(trip_data.get('pack_price', 0))
        num_people = int(trip_data.get('num_people', 2))
        stars = "⭐" * int(trip_data.get('stars', 4))
        
        date_start = datetime.strptime(trip_data['date_start'], '%Y-%m-%d').strftime('%d %b')
        date_end = datetime.strptime(trip_data['date_end'], '%Y-%m-%d').strftime('%d %b %Y')
        
        is_ultra_budget = trip_data.get('is_ultra_budget', False)
        
        # Préparer PLUSIEURS images via le proxy
        photos = api_data.get('photos', [])
        
        raw_main_photo = photos[0] if photos else 'https://images.unsplash.com/photo-1566073771259-6a8506099945'
        main_photo = f'/api/image-proxy?url={urllib.parse.quote(raw_main_photo)}'
        
        raw_second_photo = photos[1] if len(photos) > 1 else photos[0] if photos else ''
        second_photo = f'/api/image-proxy?url={urllib.parse.quote(raw_second_photo)}' if raw_second_photo else ''
        
        raw_third_photo = photos[2] if len(photos) > 2 else photos[0] if photos else ''
        third_photo = f'/api/image-proxy?url={urllib.parse.quote(raw_third_photo)}' if raw_third_photo else ''
        
        logo_url = "https://static.wixstatic.com/media/5ca515_449af35c8bea462986caf4fd28e02398~mv2.png"
        proxied_logo_url = f'/api/image-proxy?url={urllib.parse.quote(logo_url)}'
        
        # Inclusions
        inclusions_html = []
        flight_price = int(trip_data.get('flight_price', 0))
        if flight_price > 0:
            inclusions_html.append('<div class="inclusion-item"><div class="icon">✈️</div><div class="text">Vols A/R inclus</div></div>')
        
        if int(trip_data.get('transfer_cost', 0)) > 0:
            inclusions_html.append('<div class="inclusion-item"><div class="icon">🚐</div><div class="text">Transferts aéroport</div></div>')
        
        if int(trip_data.get('car_rental_cost', 0)) > 0:
            inclusions_html.append('<div class="inclusion-item"><div class="icon">🚗</div><div class="text">Location de voiture</div></div>')
        
        pension_type = trip_data.get('surcharge_type', 'Pension complète')
        inclusions_html.append(f'<div class="inclusion-item"><div class="icon">🍽️</div><div class="text">{pension_type}</div></div>')
        
        # Attractions
        all_attractions = []
        for category, attractions in api_data.get('attractions', {}).items():
            for attr in attractions[:2]:
                all_attractions.append({'name': attr, 'category': category})
        
        icons_map = {'plages': '🏖️', 'culture': '🏛️', 'gastronomie': '🍴', 'activites': '⛰️'}
        
        attractions_html = []
        for attr in all_attractions[:4]:
            icon = icons_map.get(attr['category'], '📍')
            attractions_html.append(f'<div class="attraction-card"><div class="icon">{icon}</div><div class="name">{attr["name"]}</div></div>')
        
        ultra_budget_badge = '<div class="ultra-budget-badge">⚠️ ULTRA BUDGET</div>' if is_ultra_budget else ''
        
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
        
        .slide-1 {{ position: relative; }}
        .slide-1 .hero-image {{ width: 100%; height: 100%; object-fit: cover; }}
        .slide-1 .overlay {{ position: absolute; bottom: 0; width: 100%; height: 50%; background: linear-gradient(to top, rgba(0,0,0,0.85), transparent); padding: 50px; color: {self.colors['blanc']}; display: flex; flex-direction: column; justify-content: flex-end; }}
        .slide-1 .logo-top {{ position: absolute; top: 30px; left: 30px; max-width: 180px; filter: brightness(0) invert(1); }}
        .slide-1 h1 {{ font-size: 52px; font-weight: 700; margin-bottom: 15px; line-height: 1.2; }}
        .slide-1 .location {{ font-size: 28px; margin-bottom: 25px; font-weight: 300; }}
        .slide-1 .dates {{ font-size: 22px; margin-bottom: 20px; opacity: 0.9; }}
        .slide-1 .price {{ font-size: 72px; font-weight: 700; color: {self.colors['or']}; line-height: 1; }}
        .slide-1 .price-label {{ font-size: 20px; opacity: 0.85; margin-top: 8px; }}
        .ultra-budget-badge {{ position: absolute; top: 30px; right: 30px; background: {self.colors['rouge_budget']}; color: white; padding: 8px 16px; border-radius: 8px; font-size: 14px; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
        
        .slide-2 {{ position: relative; background-size: cover; background-position: center; }}
        .slide-2::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(248, 250, 252, 0.92); z-index: 1; }}
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
        .slide-3::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(135deg, rgba(219, 234, 254, 0.95) 0%, rgba(255, 255, 255, 0.92) 100%); z-index: 1; }}
        .slide-3 > * {{ position: relative; z-index: 2; }}
        .slide-3-content {{ padding: 70px 60px; display: flex; flex-direction: column; height: 100%; }}
        .slide-3 h2 {{ font-size: 48px; font-weight: 700; color: {self.colors['bleu_principal']}; text-align: center; margin-bottom: 50px; }}
        .attractions-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 25px; flex: 1; }}
        .attraction-card {{ background: {self.colors['blanc']}; padding: 35px 25px; border-radius: 20px; text-align: center; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.1); display: flex; flex-direction: column; justify-content: center; align-items: center; }}
        .attraction-card .icon {{ font-size: 56px; margin-bottom: 15px; }}
        .attraction-card .name {{ font-size: 20px; font-weight: 600; color: {self.colors['texte_fonce']}; line-height: 1.3; }}
        .slide-3 .logo-bottom {{ margin-top: 30px; text-align: center; }}
        .slide-3 .logo-bottom img {{ max-width: 160px; opacity: 0.6; }}
        
        .slide-4 {{ background: {self.colors['bleu_principal']}; padding: 80px 60px; display: flex; flex-direction: column; justify-content: center; align-items: center; color: {self.colors['blanc']}; text-align: center; }}
        .slide-4 h2 {{ font-size: 56px; font-weight: 700; margin-bottom: 30px; }}
        .slide-4 .urgency {{ font-size: 32px; margin-bottom: 50px; background: rgba(255, 255, 255, 0.15); padding: 18px 40px; border-radius: 50px; backdrop-filter: blur(10px); font-weight: 500; }}
        .slide-4 .logo-main {{ max-width: 350px; margin-bottom: 60px; filter: brightness(0) invert(1); }}
        .slide-4 .contact-info {{ font-size: 28px; line-height: 1.8; font-weight: 400; }}
        .slide-4 .contact-info strong {{ font-weight: 600; }}
        .slide-4 .website {{ margin-top: 40px; font-size: 24px; color: {self.colors['or']}; font-weight: 600; }}
    </style>
</head>
<body>

<div class="slide slide-1">
    <img src="{main_photo}" alt="{hotel_name}" class="hero-image" crossorigin="anonymous">
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

<div class="slide slide-2" style="background-image: url('{second_photo}');">
    <div class="slide-2-content">
        <h2>✨ Tout Inclus</h2>
        <div class="hotel-card">
            <div class="stars">{stars}</div>
            <div class="name">{hotel_name}</div>
        </div>
        {''.join(inclusions_html)}
        <div class="logo-bottom">
            <img src="{proxied_logo_url}" alt="Logo VP" crossorigin="anonymous">
        </div>
    </div>
</div>

<div class="slide slide-3" style="background-image: url('{third_photo}');">
    <div class="slide-3-content">
        <h2>🌴 À Découvrir</h2>
        <div class="attractions-grid">
            {''.join(attractions_html)}
        </div>
        <div class="logo-bottom">
            <img src="{proxied_logo_url}" alt="Logo VP" crossorigin="anonymous">
        </div>
    </div>
</div>

<div class="slide slide-4">
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
