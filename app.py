# app.py
import os
import json
from datetime import datetime

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

from config import Config
from models import db, Trip
from services import RealAPIGatherer, generate_travel_page_html, PublicationService
import stripe

mail = Mail()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

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
        if not check_auth() and request.endpoint not in ['login', 'static', 'stripe_webhook']:
            return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if username in USERS and USERS[username] == password:
                session['authenticated'] = True
                session['username'] = username
                return redirect(url_for('home'))
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
                               google_api_key=app.config['GOOGLE_API_KEY']) # Ajout de la clé API
                               
    @app.route('/test-ftp')
    def test_ftp():
        if not check_auth():
            return "Non autorisé", 403
        
        success = publication_service.test_connection()
        if success:
            return "✅ Connexion FTP/SFTP réussie !"
        else:
            return "❌ Échec de connexion - Vérifiez les logs du terminal pour plus de détails."

    @app.route('/api/generate-preview', methods=['POST'])
    def generate_preview():
        try:
            gatherer = RealAPIGatherer()
            data = request.get_json()
            
            required_fields = ['hotel_name', 'destination', 'date_start', 'date_end', 'price', 'booking_price']
            if not all(field in data and data[field] for field in required_fields):
                return jsonify({'success': False, 'error': 'Tous les champs requis ne sont pas remplis.'}), 400

            real_data = gatherer.gather_all_real_data(data['hotel_name'], data['destination'])
            
            try:
                hotel_price = int(data.get('booking_price', 0))
                flight_price = int(data.get('flight_price', 0))
                transfer_cost = int(data.get('transfer_cost', 0))
                surcharge_cost = int(data.get('surcharge_cost', 0))
                your_price = int(data.get('price', 0))
                car_rental_cost = int(data.get('car_rental_cost', 0))
                comparison_total = hotel_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
                savings = comparison_total - your_price
            except (ValueError, TypeError):
                savings = 0
                comparison_total = 0

            return jsonify({
                'success': True, 
                'form_data': data, 
                'api_data': real_data,
                'savings': savings,
                'comparison_total': comparison_total
            })
        except Exception as e:
            print(f"Erreur dans /api/generate-preview: {e}")
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
            price=int(form_data.get('price', 0)),
            status=data.get('status', 'proposed')
        )
        
        if new_trip.status == 'assigned':
            new_trip.client_first_name=data.get('client_first_name')
            new_trip.client_last_name=data.get('client_last_name')
            new_trip.client_email=data.get('client_email')
            new_trip.assigned_at = datetime.utcnow()

        db.session.add(new_trip)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Voyage enregistré !', 'trip': new_trip.to_dict()})

    @app.route('/api/trip/<int:trip_id>/assign', methods=['POST'])
    def assign_trip_to_client(trip_id):
        source_trip = Trip.query.get_or_404(trip_id)
        client_data = request.get_json()

        new_trip = Trip(
            full_data_json=source_trip.full_data_json,
            hotel_name=source_trip.hotel_name,
            destination=source_trip.destination,
            price=source_trip.price,
            status='assigned',
            client_first_name=client_data.get('client_first_name'),
            client_last_name=client_data.get('client_last_name'),
            client_email=client_data.get('client_email'),
            assigned_at=datetime.utcnow()
        )
        
        db.session.add(new_trip)
        db.session.commit()

        client_filename = publication_service.publish_client_offer(new_trip)
        if client_filename:
            new_trip.client_published_filename = client_filename
            db.session.commit()
        else:
            return jsonify({'success': False, 'message': 'Le voyage a été assigné, mais la publication du fichier client a échoué.'})
        
        return jsonify({'success': True, 'message': 'Voyage assigné au client et page privée créée.'})


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

        db.session.commit()
        return jsonify({'success': True, 'message': 'Statut mis à jour.'})

    @app.route('/api/trip/<int:trip_id>/update', methods=['PUT'])
    def update_trip_details(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        new_form_data = request.get_json()

        try:
            full_data = json.loads(trip.full_data_json)
            full_data['form_data'] = new_form_data
            
            hotel_price = int(new_form_data.get('booking_price', 0))
            flight_price = int(new_form_data.get('flight_price', 0))
            transfer_cost = int(new_form_data.get('transfer_cost', 0))
            surcharge_cost = int(new_form_data.get('surcharge_cost', 0))
            your_price = int(new_form_data.get('price', 0))
            car_rental_cost = int(new_form_data.get('car_rental_cost', 0))
            
            comparison_total = hotel_price + flight_price + transfer_cost + surcharge_cost + car_rental_cost
            savings = comparison_total - your_price
            
            full_data['comparison_total'] = comparison_total
            full_data['savings'] = savings
            
            trip.price = your_price
            trip.full_data_json = json.dumps(full_data)
            
            if trip.status == 'assigned':
                print(f"ℹ️ Mise à jour et republication du fichier client pour le voyage {trip.id}...")
                client_filename = publication_service.publish_client_offer(trip)
                if client_filename:
                    trip.client_published_filename = client_filename
                else:
                    return jsonify({'success': False, 'message': 'Les données ont été sauvegardées, mais la republication a échoué.'})

            db.session.commit()
            return jsonify({'success': True, 'message': 'Offre client mise à jour et republiée !'})

        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du voyage {trip_id}: {e}")
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
        else: # Unpublish
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

        if not trip.client_email:
            return jsonify({'success': False, 'message': 'Aucun email de client associé à ce voyage.'}), 400

        if not trip.client_published_filename:
            return jsonify({'success': False, 'message': "L'offre pour ce client n'a pas de page privée publiée."}), 500
        
        client_offer_url = f"{app.config['SITE_PUBLIC_URL']}/clients/{trip.client_published_filename}"

        try:
            product_name = f"Voyage: {trip.hotel_name} pour {trip.client_first_name} {trip.client_last_name}"
            product = stripe.Product.create(name=product_name)
            price = stripe.Price.create(
                product=product.id,
                unit_amount=trip.price * 100,
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
            print(f"❌ Erreur Stripe: {e}")
            return jsonify({'success': False, 'message': f'Erreur lors de la création du lien de paiement Stripe: {e}'}), 500

        try:
            client_name = f"{trip.client_first_name} {trip.client_last_name}"
            email_html = render_template(
                'offer_template.html',
                client_name=client_name,
                hotel_name=trip.hotel_name,
                destination=trip.destination,
                public_offer_url=client_offer_url,
                stripe_payment_link=trip.stripe_payment_link
            )
            msg = Message(
                subject=f"Votre proposition de voyage pour {trip.destination}",
                sender=("Voyages Privilèges", app.config['MAIL_DEFAULT_SENDER']),
                recipients=[trip.client_email]
            )
            msg.html = email_html
            mail.send(msg)
        except Exception as e:
            print(f"❌ Erreur Email: {e}")
            return jsonify({'success': False, 'message': f"Erreur lors de l'envoi de l'email: {e}"}), 500

        return jsonify({'success': True, 'message': 'Offre envoyée avec succès par email !'})


    @app.route('/stripe-webhook', methods=['POST'])
    def stripe_webhook():
        return jsonify(status='success'), 200

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)

# Ajout pour Gunicorn - créer l'instance app au niveau du module
app = create_app()
