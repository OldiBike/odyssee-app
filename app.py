# app.py
import os
import json
import requests
from datetime import datetime, date
import traceback

from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print("✅ Fichier .env chargé explicitement.")
else:
    print("⚠️ Fichier .env introuvable au chemin:", dotenv_path)


from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from flask_migrate import Migrate
from flask_mail import Mail, Message
from flask_cors import CORS

from config import Config
from models import db, Trip
from services import RealAPIGatherer, generate_travel_page_html, PublicationService
import stripe

mail = Mail()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app, resources={r"/api/*": {"origins": ["https://voyages-privileges.be", "https://www.voyages-privileges.be"]}})

    print(f"🔑 Clé API Google chargée : {'Oui' if app.config.get('GOOGLE_API_KEY') else 'Non'}")
    print(f"🔑 Clé API Stripe chargée : {'Oui' if app.config.get('STRIPE_API_KEY') else 'Non'}")


    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    
    if app.config['STRIPE_API_KEY']:
        stripe.api_key = app.config['STRIPE_API_KEY']

    publication_service = PublicationService(app.config)

    USERS = {
        os.environ.get('USER1_NAME', 'Sam'): os.environ.get('USER1_PASS', 'samuel1205'),
        os.environ.get('USER2_NAME', 'Constantin'): os.environ.get('USER2_PASS', 'standard01')
    }

    def check_auth():
        return session.get('authenticated', False)

    @app.before_request
    def require_login():
        if not check_auth() and request.endpoint not in ['login', 'static', 'stripe_webhook', 'published_trips']:
            return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if username in USERS and USERS[username] == password:
                session['authenticated'] = True
                session['username'] = username
                return redirect(url_for('generation_tool'))
            else:
                return render_template('login.html', error="Identifiants incorrects")
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/')
    def home():
        return redirect(url_for('generation_tool'))

    @app.route('/api/published-trips')
    def published_trips():
        trips = Trip.query.filter_by(is_published=True).order_by(Trip.created_at.desc()).all()
        trips_data = []
        for trip in trips:
            trip_dict = trip.to_dict()
            full_data = json.loads(trip.full_data_json)
            image_url = full_data.get('api_data', {}).get('photos', [None])[0]
            savings = full_data.get('savings', 0)
            hotel_name_only = trip.hotel_name.split(',')[0].strip()
            
            num_people = full_data.get('form_data', {}).get('num_people', 2)
            
            duration_days = 0
            if trip_dict.get('date_start') and trip_dict.get('date_end'):
                try:
                    date_start = datetime.strptime(trip_dict['date_start'], '%Y-%m-%d')
                    date_end = datetime.strptime(trip_dict['date_end'], '%Y-%m-%d')
                    duration_days = (date_end - date_start).days
                except (ValueError, TypeError):
                    duration_days = 0

            trips_data.append({
                'hotel_name': hotel_name_only,
                'destination': trip.destination,
                'price': trip.price,
                'image_url': image_url,
                'offer_url': f"{app.config['SITE_PUBLIC_URL']}/offres/{trip.published_filename}",
                'savings': savings,
                'num_people': num_people,
                'is_ultra_budget': trip.is_ultra_budget,
                'duration': duration_days
            })
        return jsonify(trips_data)

    @app.route('/generation')
    def generation_tool():
        return render_template('generation.html', 
                               username=session.get('username'), 
                               google_api_key=app.config['GOOGLE_API_KEY'])

    @app.route('/dashboard')
    def dashboard():
        view_mode = request.args.get('view', 'proposed')
        return render_template('dashboard.html', 
                               username=session.get('username'), 
                               view_mode=view_mode,
                               site_public_url=app.config.get('SITE_PUBLIC_URL', ''),
                               google_api_key=app.config['GOOGLE_API_KEY'])
                               
    @app.route('/test-ftp')
    def test_ftp():
        if not check_auth():
            return "Non autorisé", 403
        
        success = publication_service.test_connection()
        if success:
            return "✅ Connexion API réussie !"
        else:
            return "❌ Échec de connexion API - Vérifiez les logs du terminal pour plus de détails."

    @app.route('/api/generate-preview', methods=['POST'])
    def generate_preview():
        try:
            gatherer = RealAPIGatherer()
            data = request.get_json()
            
            required_fields = ['hotel_name', 'destination', 'date_start', 'date_end', 'hotel_b2b_price', 'hotel_b2c_price', 'pack_price']
            if not all(field in data and data[field] for field in required_fields):
                return jsonify({'success': False, 'error': 'Tous les champs requis ne sont pas remplis.'}), 400

            real_data = gatherer.gather_all_real_data(data['hotel_name'], data['destination'])
            
            try:
                hotel_b2b_price = int(data.get('hotel_b2b_price') or 0)
                hotel_b2c_price = int(data.get('hotel_b2c_price') or 0)
                pack_price = int(data.get('pack_price') or 0)
                flight_price = int(data.get('flight_price') or 0)
                transfer_cost = int(data.get('transfer_cost') or 0)
                surcharge_cost = int(data.get('surcharge_cost') or 0)
                car_rental_cost = int(data.get('car_rental_cost') or 0)

                total_cost_b2b = hotel_b2b_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
                margin = pack_price - total_cost_b2b

                comparison_total = hotel_b2c_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
                savings = comparison_total - pack_price

            except (ValueError, TypeError):
                margin = 0
                savings = 0
                comparison_total = 0

            return jsonify({
                'success': True, 
                'form_data': data, 
                'api_data': real_data,
                'margin': margin,
                'savings': savings,
                'comparison_total': comparison_total
            })
        except Exception as e:
            print(f"Erreur dans /api/generate-preview: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/render-html-preview', methods=['POST'])
    def render_html_preview():
        if not check_auth():
            return "Non autorisé", 403
        
        data = request.get_json()
        form_data = data.get('form_data')
        api_data = data.get('api_data')
        savings = data.get('savings')
        comparison_total = data.get('comparison_total')

        if not all([form_data, api_data]):
            return "Données manquantes", 400

        html_content = generate_travel_page_html(form_data, api_data, savings, comparison_total)
        return Response(html_content, mimetype='text/html')


    @app.route('/api/trips', methods=['POST'])
    def save_trip():
        data = request.get_json()
        form_data = data.get('form_data')
        
        new_trip = Trip(
            full_data_json=json.dumps(data),
            hotel_name=form_data.get('hotel_name'),
            destination=form_data.get('destination'),
            price=int(form_data.get('pack_price') or 0),
            status=data.get('status', 'proposed'),
            is_ultra_budget=form_data.get('is_ultra_budget', False)
        )
        
        if new_trip.status == 'assigned':
            new_trip.client_first_name=data.get('client_first_name')
            new_trip.client_last_name=data.get('client_last_name')
            new_trip.client_email=data.get('client_email')
            new_trip.client_phone=data.get('client_phone')
            new_trip.assigned_at = datetime.utcnow()

        db.session.add(new_trip)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Voyage enregistré !', 'trip': new_trip.to_dict()})

    @app.route('/api/trip/<int:trip_id>/assign', methods=['POST'])
    def assign_trip_to_client(trip_id):
        try:
            source_trip = Trip.query.get_or_404(trip_id)
            client_data = request.get_json()

            new_trip = Trip(
                full_data_json=source_trip.full_data_json,
                hotel_name=source_trip.hotel_name,
                destination=source_trip.destination,
                price=source_trip.price,
                status='assigned',
                is_ultra_budget=source_trip.is_ultra_budget,
                client_first_name=client_data.get('client_first_name'),
                client_last_name=client_data.get('client_last_name'),
                client_email=client_data.get('client_email'),
                client_phone=client_data.get('client_phone'),
                assigned_at=datetime.utcnow()
            )
            
            db.session.add(new_trip)
            db.session.commit()

            print(f"ℹ️ Tentative de publication du fichier pour le voyage {new_trip.id}...")
            client_filename = publication_service.publish_client_offer(new_trip)
            
            if client_filename:
                new_trip.client_published_filename = client_filename
                db.session.commit()
                print(f"✅ Publication réussie: {client_filename}")
                return jsonify({'success': True, 'message': 'Voyage assigné au client et page privée créée.'})
            else:
                db.session.rollback() 
                db.session.delete(new_trip)
                db.session.commit()
                print(f"❌ La publication a échoué. Le voyage {new_trip.id} a été annulé.")
                return jsonify({'success': False, 'message': 'Le voyage n\'a pas pu être assigné car la publication du fichier sur le serveur a échoué. Vérifiez les logs de Railway pour les détails de l\'erreur réseau.'})

        except Exception as e:
            db.session.rollback()
            print(f"❌ Erreur critique dans assign_trip_to_client: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': f'Une erreur interne est survenue: {str(e)}'}), 500

    @app.route('/api/trips', methods=['GET'])
    def get_trips():
        status = request.args.get('status', 'proposed')
        trips_query = Trip.query.filter_by(status=status).order_by(Trip.created_at.desc()).all()
        trips_data = [trip.to_dict() for trip in trips_query]
        return jsonify(trips_data)

    @app.route('/api/trip/<int:trip_id>', methods=['GET'])
    def get_trip_details(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        trip_details = trip.to_dict()
        trip_details['full_data_json'] = trip.full_data_json
        return jsonify(trip_details)

    @app.route('/api/trip/<int:trip_id>/status', methods=['PUT'])
    def update_trip_status(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        data = request.get_json()
        new_status = data.get('status')

        if new_status == 'sold':
            trip.status = 'sold'
            trip.sold_at = datetime.utcnow()

        elif new_status == 'proposed':
            if trip.client_published_filename:
                publication_service.unpublish(trip.client_published_filename, is_client_offer=True)
            
            trip.status = 'proposed'
            trip.client_first_name = None
            trip.client_last_name = None
            trip.client_email = None
            trip.assigned_at = None
            trip.client_published_filename = None
            trip.client_phone = None

        db.session.commit()
        return jsonify({'success': True, 'message': 'Statut mis à jour.'})

    @app.route('/api/trip/<int:trip_id>/update', methods=['PUT'])
    def update_trip_details(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        new_form_data = request.get_json()

        try:
            full_data = json.loads(trip.full_data_json)
            full_data['form_data'] = new_form_data
            
            hotel_b2b_price = int(new_form_data.get('hotel_b2b_price') or 0)
            hotel_b2c_price = int(new_form_data.get('hotel_b2c_price') or 0)
            pack_price = int(new_form_data.get('pack_price') or 0)
            flight_price = int(new_form_data.get('flight_price') or 0)
            transfer_cost = int(new_form_data.get('transfer_cost') or 0)
            surcharge_cost = int(new_form_data.get('surcharge_cost') or 0)
            car_rental_cost = int(new_form_data.get('car_rental_cost') or 0)

            total_cost_b2b = hotel_b2b_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
            margin = pack_price - total_cost_b2b
            
            comparison_total = hotel_b2c_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
            savings = comparison_total - pack_price
            
            full_data['margin'] = margin
            full_data['comparison_total'] = comparison_total
            full_data['savings'] = savings
            
            trip.price = pack_price
            trip.full_data_json = json.dumps(full_data)
            trip.is_ultra_budget = new_form_data.get('is_ultra_budget', False)
            
            if trip.status == 'assigned':
                print(f"ℹ️ Mise à jour et republication du fichier client pour le voyage {trip.id}...")
                client_filename = publication_service.publish_client_offer(trip)
                if client_filename:
                    trip.client_published_filename = client_filename
                else:
                    return jsonify({'success': False, 'message': 'Les données ont été sauvegardées, mais la republication a échoué.'})

            elif trip.status == 'proposed' and trip.is_published:
                print(f"ℹ️ Mise à jour et republication du fichier public pour le voyage {trip.id}...")
                public_filename = publication_service.publish_public_offer(trip)
                if public_filename:
                    trip.published_filename = public_filename
                else:
                    return jsonify({'success': False, 'message': 'Les données ont été sauvegardées, mais la republication de l\'offre publique a échoué.'})
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'Offre mise à jour et republiée avec succès !'})

        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du voyage {trip_id}: {e}")
            traceback.print_exc()
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/trip/<int:trip_id>', methods=['DELETE'])
    def delete_trip(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if trip.is_published:
            publication_service.unpublish(trip.published_filename, is_client_offer=False)
        if trip.client_published_filename:
            publication_service.unpublish(trip.client_published_filename, is_client_offer=True)
            
        db.session.delete(trip)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Voyage supprimé.'})
        
    @app.route('/api/trip/<int:trip_id>/publish', methods=['POST'])
    def toggle_publish_status(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        data = request.get_json()
        publish_action = data.get('publish', False)

        if publish_action:
            filename = publication_service.publish_public_offer(trip)
            if filename:
                trip.is_published = True
                trip.published_filename = filename
                db.session.commit()
                return jsonify({'success': True, 'message': 'Voyage publié !', 'trip': trip.to_dict()})
            else:
                return jsonify({'success': False, 'message': 'Erreur lors de la publication.'}), 500
        else:
            if trip.published_filename and publication_service.unpublish(trip.published_filename, is_client_offer=False):
                trip.is_published = False
                trip.published_filename = None
                db.session.commit()
                return jsonify({'success': True, 'message': 'Voyage dépublié !', 'trip': trip.to_dict()})
            elif not trip.published_filename:
                trip.is_published = False
                db.session.commit()
                return jsonify({'success': True, 'message': 'Voyage marqué comme non publié.'})
            else:
                return jsonify({'success': False, 'message': 'Erreur lors de la dépublication.'}), 500

    @app.route('/api/trip/<int:trip_id>/send-offer', methods=['POST'])
    def send_offer_email(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        data = request.get_json()

        if not trip.client_email:
            return jsonify({'success': False, 'message': 'Aucun email de client associé à ce voyage.'}), 400

        if not trip.client_published_filename:
            return jsonify({'success': False, 'message': "L'offre pour ce client n'a pas de page privée publiée."}), 500
        
        full_data = json.loads(trip.full_data_json)
        header_photo = full_data.get('api_data', {}).get('photos', [None])[0]
        hotel_name_only = trip.hotel_name.split(',')[0].strip()
        client_first_name_only = trip.client_first_name.split(' ')[0].strip() if trip.client_first_name else ""

        client_offer_url = f"{app.config['SITE_PUBLIC_URL']}/clients/{trip.client_published_filename}"
        payment_type = data.get('payment_type', 'total')
        amount_to_pay = trip.price
        
        if payment_type == 'down_payment':
            try:
                down_payment_amount = int(data.get('down_payment_amount'))
                balance_due_date_str = data.get('balance_due_date')
                trip.down_payment_amount = down_payment_amount
                trip.balance_due_date = datetime.strptime(balance_due_date_str, '%Y-%m-%d').date()
                amount_to_pay = down_payment_amount
            except (TypeError, ValueError) as e:
                return jsonify({'success': False, 'message': f'Données d\'acompte invalides: {e}'}), 400
        else:
            trip.down_payment_amount = None
            trip.balance_due_date = None

        try:
            product_name = f"Voyage: {trip.hotel_name} pour {trip.client_first_name} {trip.client_last_name}"
            
            product = stripe.Product.create(name=product_name)
            price = stripe.Price.create(
                product=product.id,
                unit_amount=amount_to_pay * 100,
                currency="eur",
            )
            
            checkout_session = stripe.checkout.Session.create(
                line_items=[{'price': price.id, 'quantity': 1}],
                mode='payment',
                success_url=f"{app.config['SITE_PUBLIC_URL']}?payment=success&trip_id={trip.id}",
                cancel_url=client_offer_url,
                client_reference_id=trip.id,
                customer_email=trip.client_email
            )
            trip.stripe_payment_link = checkout_session.url
            db.session.commit()

        except Exception as e:
            print(f"❌ [Trip ID: {trip.id}] Erreur Stripe: {e}")
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Erreur lors de la création du lien de paiement Stripe: {e}'}), 500

        try:
            client_name = f"{trip.client_first_name} {trip.client_last_name}"
            
            if payment_type == 'down_payment':
                balance_amount = trip.price - trip.down_payment_amount
                balance_due_date_formatted = trip.balance_due_date.strftime('%d/%m/%Y')
                template = 'offer_template_down_payment.html'
                email_context = {
                    'client_name': client_name,
                    'client_first_name': client_first_name_only,
                    'hotel_name': hotel_name_only,
                    'destination': trip.destination,
                    'public_offer_url': client_offer_url,
                    'stripe_payment_link': trip.stripe_payment_link,
                    'down_payment_amount': trip.down_payment_amount,
                    'balance_amount': balance_amount,
                    'balance_due_date': balance_due_date_formatted,
                    'header_photo': header_photo
                }
            else:
                template = 'offer_template.html'
                email_context = {
                    'client_name': client_name,
                    'client_first_name': client_first_name_only,
                    'hotel_name': hotel_name_only,
                    'destination': trip.destination,
                    'public_offer_url': client_offer_url,
                    'stripe_payment_link': trip.stripe_payment_link,
                    'header_photo': header_photo
                }

            email_html = render_template(template, **email_context)
            msg = Message(
                subject=f"Votre proposition de voyage pour {trip.destination}",
                sender=("Voyages Privilèges", app.config['MAIL_DEFAULT_SENDER']),
                recipients=[trip.client_email]
            )
            msg.html = email_html
            mail.send(msg)
            
        except Exception as e:
            print(f"❌ [Trip ID: {trip.id}] ERREUR DÉTAILLÉE LORS DE L'ENVOI DE L'EMAIL:")
            traceback.print_exc()
            return jsonify({'success': False, 'message': f"Erreur lors de l'envoi de l'email: {str(e)}"}), 500

        return jsonify({'success': True, 'message': 'Offre envoyée avec succès par email !'})
    
    @app.route('/api/trip/<int:trip_id>/send-whatsapp', methods=['POST'])
    def send_whatsapp_offer(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        n8n_webhook_url = app.config.get('N8N_WHATSAPP_WEBHOOK')

        if not n8n_webhook_url:
            return jsonify({'success': False, 'message': 'URL du webhook N8N non configurée.'}), 500
        
        if not trip.is_published or not trip.published_filename:
            return jsonify({'success': False, 'message': 'Le voyage doit être publié pour être partagé.'}), 400

        try:
            full_data = json.loads(trip.full_data_json)
            form_data = full_data.get('form_data', {})
            api_data = full_data.get('api_data', {})
            savings = full_data.get('savings', 0)
            
            gatherer = RealAPIGatherer()
            catchphrase = gatherer.generate_whatsapp_catchphrase({
                'hotel_name': trip.hotel_name,
                'destination': trip.destination
            })

            caption_parts = [
                f"🌟 *{catchphrase}*",
                f"🏨 *{trip.hotel_name}* à {trip.destination}",
                f"💰 À partir de *{trip.price}€* (Économisez {savings}€ !)",
            ]

            services = form_data.get('exclusive_services', '').strip()
            if services:
                services_list = "\n".join([f"✓ {s.strip()}" for s in services.split('\n')])
                caption_parts.append(f"\n🎁 *Services Exclusifs Offerts :*\n{services_list}")

            offer_url = f"{app.config['SITE_PUBLIC_URL']}/offres/{trip.published_filename}"
            caption_parts.append(f"\n👉 *Voir l'offre complète ici :* {offer_url}")
            
            final_caption = "\n\n".join(caption_parts)

            payload = {
                "imageUrl": api_data.get('photos', [None])[0],
                "caption": final_caption,
                "offerUrl": offer_url
            }

            if not payload["imageUrl"]:
                return jsonify({'success': False, 'message': 'Aucune image trouvée pour ce voyage.'}), 400

            response = requests.post(n8n_webhook_url, json=payload, timeout=20)
            response.raise_for_status() 

            return jsonify({'success': True, 'message': 'Offre envoyée au canal WhatsApp !'})

        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur en contactant le webhook N8N: {e}")
            return jsonify({'success': False, 'message': 'Erreur de communication avec le service d\'envoi.'}), 500
        except Exception as e:
            print(f"❌ Erreur inattendue dans send_whatsapp_offer: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': 'Une erreur interne est survenue.'}), 500

    @app.route('/stripe-webhook', methods=['POST'])
    def stripe_webhook():
        return jsonify(status='success'), 200

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)

app = create_app()
