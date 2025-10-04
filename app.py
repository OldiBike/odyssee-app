# app.py - Version complète avec gestion WhatsApp, Stripe, Emails et Factures
import os
import json
import csv
import io
import requests
from datetime import datetime, date, timedelta
import traceback
from functools import wraps
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print("✅ Fichier .env chargé explicitement.")
else:
    print("⚠️ Fichier .env introuvable au chemin:", dotenv_path)

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, g
from flask_migrate import Migrate
from flask_mail import Mail, Message
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from weasyprint import HTML
from sqlalchemy import func, extract, desc, or_
from collections import defaultdict
import click

from config import Config
from models import db, Trip, Invoice, User, Client
from services import RealAPIGatherer, generate_travel_page_html, PublicationService
import stripe

mail = Mail()
migrate = Migrate()
bcrypt = Bcrypt()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app, resources={r"/api/*": {"origins": ["https://voyages-privileges.be", "https://www.voyages-privileges.be"]}})

    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    
    if app.config.get('STRIPE_API_KEY'):
        stripe.api_key = app.config['STRIPE_API_KEY']

    @app.cli.command("create-admin")
    def create_admin_command():
        """Crée le(s) compte(s) admin à partir des variables d'environnement."""
        with app.app_context():
            for i in [1, 2]:
                admin_user = os.environ.get(f'ADMIN_{i}_USERNAME')
                if not admin_user:
                    continue
                
                if User.query.filter_by(username=admin_user).first():
                    print(f"L'utilisateur admin '{admin_user}' existe déjà.")
                    continue

                admin_pass = os.environ.get(f'ADMIN_{i}_PASSWORD')
                admin_email = os.environ.get(f'ADMIN_{i}_EMAIL')
                admin_pseudo = os.environ.get(f'ADMIN_{i}_PSEUDO')
                
                if all([admin_pass, admin_email, admin_pseudo]):
                    hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
                    new_admin = User(
                        username=admin_user, 
                        password=hashed_password, 
                        pseudo=admin_pseudo, 
                        email=admin_email, 
                        role='admin'
                    )
                    db.session.add(new_admin)
                    print(f"✅ Compte admin '{admin_user}' créé avec succès.")
                else:
                    print(f"❌ Données manquantes pour l'admin {i}. Compte non créé.")
            db.session.commit()

    publication_service = PublicationService(app.config)

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            g.user = User.query.get(session['user_id'])
            if not g.user:
                session.clear()
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    def admin_required(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if g.user.role != 'admin':
                return jsonify({'success': False, 'message': 'Accès non autorisé.'}), 403
            return f(*args, **kwargs)
        return decorated_function

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()
            if user and bcrypt.check_password_hash(user.password, password):
                session.clear()
                session['user_id'] = user.id
                session['pseudo'] = user.pseudo
                session['role'] = user.role
                return redirect(url_for('generation_tool'))
            else:
                return render_template('login.html', error="Identifiants incorrects")
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/')
    @login_required
    def home():
        return redirect(url_for('generation_tool'))

    @app.route('/generation')
    @login_required
    def generation_tool():
        return render_template('generation.html', google_api_key=app.config['GOOGLE_API_KEY'], user_margin=g.user.margin_percentage)

    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('dashboard.html', view_mode=request.args.get('view', 'proposed'), site_public_url=app.config.get('SITE_PUBLIC_URL', ''))

    @app.route('/sellers')
    @admin_required
    def sellers_page():
        return render_template('sellers.html')

    @app.route('/clients')
    @login_required
    def clients_page():
        return render_template('clients.html')

    @app.route('/sales_report')
    @login_required
    def sales_report_page():
        return render_template('sales_report.html')

    @app.route('/stats')
    @login_required
    def stats_page():
        return render_template('stats.html')

    @app.route('/api/generate-preview', methods=['POST'])
    @login_required
    def generate_preview():
        if g.user.role == 'vendeur':
            today = date.today()
            if g.user.last_generation_date != today:
                g.user.generation_count = 0
                g.user.last_generation_date = today
            if g.user.generation_count >= g.user.daily_generation_limit:
                return jsonify({'success': False, 'error': f"Quota de {g.user.daily_generation_limit} générations atteint."}), 429
            g.user.generation_count += 1
            db.session.commit()
        
        try:
            gatherer = RealAPIGatherer()
            data = request.get_json()
            
            required_fields = ['hotel_name', 'destination', 'date_start', 'date_end', 'hotel_b2b_price', 'hotel_b2c_price', 'pack_price']
            if not all(field in data and data[field] for field in required_fields):
                raise ValueError('Tous les champs requis ne sont pas remplis.')

            real_data = gatherer.gather_all_real_data(data['hotel_name'], data['destination'])
            
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

            return jsonify({'success': True, 'form_data': data, 'api_data': real_data, 'margin': margin, 'savings': savings, 'comparison_total': comparison_total})
        except Exception as e:
            if g.user.role == 'vendeur':
                g.user.generation_count -= 1
                db.session.commit()
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/render-html-preview', methods=['POST'])
    @login_required
    def render_html_preview():
        data = request.get_json()
        html_content = generate_travel_page_html(data.get('form_data'), data.get('api_data'), data.get('savings'), data.get('comparison_total'), creator_pseudo=g.user.pseudo)
        return Response(html_content, mimetype='text/html')

    @app.route('/api/trips', methods=['POST'])
    @login_required
    def save_trip():
        try:
            data = request.get_json()
            form_data = data.get('form_data', {})
            
            client_id = None
            
            if form_data.get('client_id'):
                client_id = int(form_data.get('client_id'))
                print(f"✅ Client existant sélectionné: ID {client_id}")
            
            elif data.get('client_first_name') and data.get('client_last_name') and data.get('client_email'):
                new_client_data = {
                    'first_name': data.get('client_first_name'),
                    'last_name': data.get('client_last_name'),
                    'email': data.get('client_email'),
                    'phone': data.get('client_phone', ''),
                }
                
                existing_client = Client.query.filter_by(email=new_client_data['email']).first()
                if existing_client:
                    client_id = existing_client.id
                    print(f"✅ Client existant trouvé: {existing_client.to_dict()['full_name']}")
                else:
                    new_client = Client(**new_client_data)
                    db.session.add(new_client)
                    db.session.flush()
                    client_id = new_client.id
                    print(f"✅ Nouveau client créé: ID {client_id}")
            
            else:
                print("✅ Enregistrement comme proposition générale (pas de client)")
            
            status = 'assigned' if client_id else 'proposed'
            
            new_trip = Trip(
                user_id=g.user.id,
                client_id=client_id,
                full_data_json=json.dumps(data),
                hotel_name=form_data.get('hotel_name', 'Hôtel inconnu'),
                destination=form_data.get('destination', 'Destination inconnue'),
                price=int(form_data.get('pack_price') or 0),
                status=status,
                is_ultra_budget=form_data.get('is_ultra_budget', False)
            )
            
            if status == 'assigned':
                new_trip.assigned_at = datetime.utcnow()

            db.session.add(new_trip)
            db.session.commit()
            
            print(f"✅ Voyage créé avec succès: ID {new_trip.id}, Status: {status}")
            
            if status == 'assigned':
                client_filename = publication_service.publish_client_offer(new_trip)
                if client_filename:
                    new_trip.client_published_filename = client_filename
                    db.session.commit()
                    print(f"✅ Page client publiée: {client_filename}")
                else:
                    print("⚠️ Échec de publication de la page client")

            return jsonify({
                'success': True, 
                'message': f'Voyage enregistré comme {status}!', 
                'trip': new_trip.to_dict()
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erreur lors de la sauvegarde: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': f'Erreur serveur: {str(e)}'}), 500

    @app.route('/api/trip/<int:trip_id>/assign', methods=['POST'])
    @login_required
    def assign_trip(trip_id):
        try:
            source_trip = Trip.query.get_or_404(trip_id)
            if g.user.role != 'admin' and source_trip.user_id != g.user.id:
                return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403

            data = request.get_json()
            client_id = data.get('client_id')

            if not client_id:
                new_client_data = {
                    'first_name': data.get('first_name'),
                    'last_name': data.get('last_name'),
                    'email': data.get('email'),
                    'phone': data.get('phone', ''),
                }
                if not all([new_client_data['first_name'], new_client_data['last_name'], new_client_data['email']]):
                    return jsonify({'success': False, 'message': 'Données du client incomplètes.'}), 400
                
                existing_client = Client.query.filter_by(email=new_client_data['email']).first()
                if existing_client:
                    client_id = existing_client.id
                else:
                    new_client_obj = Client(**new_client_data)
                    db.session.add(new_client_obj)
                    db.session.flush()
                    client_id = new_client_obj.id
            
            new_trip = Trip(
                user_id=g.user.id,
                client_id=client_id,
                full_data_json=source_trip.full_data_json,
                hotel_name=source_trip.hotel_name,
                destination=source_trip.destination,
                price=source_trip.price,
                status='assigned',
                is_ultra_budget=source_trip.is_ultra_budget,
                assigned_at=datetime.utcnow()
            )
            db.session.add(new_trip)
            db.session.commit()

            client_filename = publication_service.publish_client_offer(new_trip)
            if client_filename:
                new_trip.client_published_filename = client_filename
                db.session.commit()
                return jsonify({'success': True, 'message': 'Voyage assigné et page privée créée.'})
            else:
                db.session.delete(new_trip)
                db.session.commit()
                return jsonify({'success': False, 'message': 'Publication de la page client échouée.'}), 500
                
        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/trip/<int:trip_id>/reproduce', methods=['POST'])
    @login_required
    def reproduce_trip(trip_id):
        try:
            source_trip = Trip.query.get_or_404(trip_id)

            new_trip = Trip(
                user_id=g.user.id,
                client_id=None, 
                full_data_json=source_trip.full_data_json,
                hotel_name=source_trip.hotel_name,
                destination=source_trip.destination,
                price=source_trip.price,
                status='proposed',
                is_ultra_budget=source_trip.is_ultra_budget
            )
            db.session.add(new_trip)
            db.session.commit()

            return jsonify({'success': True, 'message': 'Voyage dupliqué.', 'new_trip_id': new_trip.id})

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/trips', methods=['GET'])
    @login_required
    def get_trips():
        status = request.args.get('status', 'proposed')
        query = Trip.query.filter_by(status=status)
        if g.user.role == 'vendeur':
            query = query.filter_by(user_id=g.user.id)
        trips = query.order_by(desc(Trip.created_at)).all()
        return jsonify([trip.to_dict() for trip in trips])

    @app.route('/api/trip/<int:trip_id>', methods=['GET', 'DELETE'])
    @login_required
    def handle_trip(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        
        if g.user.role == 'vendeur' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403

        if request.method == 'GET':
            trip_details = trip.to_dict()
            trip_details['full_data_json'] = trip.full_data_json
            trip_details['user_margin_percentage'] = trip.user.margin_percentage 
            return jsonify(trip_details)

        if request.method == 'DELETE':
            if g.user.role != 'admin' and trip.user_id != g.user.id:
                return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
                
            if trip.is_published and trip.published_filename:
                publication_service.unpublish(trip.published_filename)
            if trip.client_published_filename:
                publication_service.unpublish(trip.client_published_filename, is_client_offer=True)
            db.session.delete(trip)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Voyage supprimé.'})

    @app.route('/api/trip/<int:trip_id>/update', methods=['PUT'])
    @login_required
    def update_trip_details(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        new_form_data = request.get_json()
        try:
            full_data = json.loads(trip.full_data_json)
            full_data['form_data'].update(new_form_data)
            
            pack_price = int(new_form_data.get('pack_price') or 0)
            hotel_b2b_price = int(new_form_data.get('hotel_b2b_price') or 0)
            hotel_b2c_price = int(new_form_data.get('hotel_b2c_price') or 0)
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
            
            republished = False
            if trip.status == 'assigned' and trip.client_published_filename:
                if publication_service.publish_client_offer(trip):
                    republished = True
            elif trip.is_published and trip.published_filename:
                if publication_service.publish_public_offer(trip):
                    republished = True
            
            db.session.commit()
            return jsonify({'success': True, 'message': f'Voyage mis à jour. Republié: {republished}'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/trip/<int:trip_id>/publish', methods=['POST'])
    @login_required
    def toggle_publish_trip(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        data = request.get_json()
        should_publish = data.get('publish', False)
        
        try:
            if should_publish and not trip.is_published:
                filename = publication_service.publish_public_offer(trip)
                if filename:
                    trip.is_published = True
                    trip.published_filename = filename
                    db.session.commit()
                    public_url = f"{app.config.get('SITE_PUBLIC_URL', '')}/offres/{filename}"
                    return jsonify({'success': True, 'message': 'Voyage publié !', 'url': public_url})
                else:
                    return jsonify({'success': False, 'message': 'Échec de la publication.'}), 500
            elif not should_publish and trip.is_published:
                if publication_service.unpublish(trip.published_filename):
                    trip.is_published = False
                    trip.published_filename = None
                    db.session.commit()
                    return jsonify({'success': True, 'message': 'Publication retirée.'})
                else:
                    return jsonify({'success': False, 'message': 'Échec de la dépublication.'}), 500
            else:
                return jsonify({'success': True, 'message': 'Aucun changement nécessaire.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    # =========================================================================
    # 🆕 ROUTE 1: ENVOI WHATSAPP
    # =========================================================================
    @app.route('/api/trip/<int:trip_id>/send-whatsapp', methods=['POST'])
    @login_required
    def send_to_whatsapp(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        try:
            webhook_url = app.config.get('N8N_WHATSAPP_WEBHOOK')
            if not webhook_url:
                return jsonify({'success': False, 'message': 'Webhook WhatsApp non configuré.'}), 500
            
            full_data = json.loads(trip.full_data_json)
            form_data = full_data.get('form_data', {})
            
            gatherer = RealAPIGatherer()
            catchphrase = gatherer.generate_whatsapp_catchphrase({
                'hotel_name': trip.hotel_name,
                'destination': trip.destination
            })
            
            offer_url = f"{app.config.get('SITE_PUBLIC_URL', '')}/offres/{trip.published_filename}" if trip.published_filename else ""
            
            payload = {
                'catchphrase': catchphrase,
                'hotel_name': trip.hotel_name,
                'destination': trip.destination,
                'price': trip.price,
                'offer_url': offer_url
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return jsonify({'success': True, 'message': 'Message envoyé sur WhatsApp avec succès !'})
            else:
                return jsonify({'success': False, 'message': f'Erreur webhook: {response.status_code}'}), 500
                
        except Exception as e:
            print(f"❌ Erreur WhatsApp: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500

    # =========================================================================
    # 🆕 ROUTE 2: ENVOI OFFRE (avec Stripe)
    # =========================================================================
    @app.route('/api/trip/<int:trip_id>/send-offer', methods=['POST'])
    @login_required
    def send_offer_email(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        if not trip.client:
            return jsonify({'success': False, 'message': 'Aucun client assigné à ce voyage.'}), 400
        
        try:
            data = request.get_json()
            payment_type = data.get('payment_type', 'total')
            
            if payment_type == 'down_payment':
                down_payment_amount = int(data.get('down_payment_amount', 0))
                balance_due_date_str = data.get('balance_due_date', '')
                
                if not down_payment_amount or not balance_due_date_str:
                    return jsonify({'success': False, 'message': 'Montant acompte et date solde requis.'}), 400
                
                balance_due_date = datetime.strptime(balance_due_date_str, '%Y-%m-%d').date()
                amount_to_pay = down_payment_amount
                
                trip.down_payment_amount = down_payment_amount
                trip.balance_due_date = balance_due_date
            else:
                amount_to_pay = trip.price
            
            payment_link = stripe.PaymentLink.create(
                line_items=[{
                    'price_data': {
                        'currency': 'eur',
                        'product_data': {
                            'name': f'Voyage {trip.hotel_name}',
                            'description': f'{trip.destination} - {trip.client.to_dict()["full_name"]}'
                        },
                        'unit_amount': amount_to_pay * 100
                    },
                    'quantity': 1
                }],
                after_completion={
                    'type': 'redirect',
                    'redirect': {'url': f"{app.config.get('SITE_PUBLIC_URL', '')}/merci"}
                }
            )
            
            trip.stripe_payment_link = payment_link.url
            db.session.commit()
            
            full_data = json.loads(trip.full_data_json)
            form_data = full_data.get('form_data', {})
            api_data = full_data.get('api_data', {})
            
            public_offer_url = f"{app.config.get('SITE_PUBLIC_URL', '')}/clients/{trip.client_published_filename}"
            header_photo = api_data.get('photos', [''])[0] if api_data.get('photos') else ''
            
            if payment_type == 'down_payment':
                template = 'offer_template_down_payment.html'
                email_context = {
                    'client_first_name': trip.client.first_name,
                    'hotel_name': trip.hotel_name,
                    'destination': trip.destination,
                    'public_offer_url': public_offer_url,
                    'header_photo': header_photo,
                    'stripe_payment_link': payment_link.url,
                    'down_payment_amount': down_payment_amount,
                    'balance_amount': trip.price - down_payment_amount,
                    'balance_due_date': balance_due_date.strftime('%d/%m/%Y'),
                    'client_name': trip.client.to_dict()['full_name']
                }
            else:
                template = 'offer_template.html'
                email_context = {
                    'client_first_name': trip.client.first_name,
                    'hotel_name': trip.hotel_name,
                    'destination': trip.destination,
                    'public_offer_url': public_offer_url,
                    'header_photo': header_photo,
                    'stripe_payment_link': payment_link.url
                }
            
            msg = Message(
                subject=f'Votre proposition de voyage - {trip.hotel_name}',
                recipients=[trip.client.email],
                html=render_template(template, **email_context)
            )
            mail.send(msg)
            
            return jsonify({'success': True, 'message': 'Offre envoyée par email avec succès !'})
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erreur envoi offre: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500

    # =========================================================================
    # 🆕 ROUTE 3: FINALISER VENTE (upload documents + email)
    # =========================================================================
    @app.route('/api/trip/<int:trip_id>/finalize-sale', methods=['POST'])
    @login_required
    def finalize_sale(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        if not trip.client:
            return jsonify({'success': False, 'message': 'Aucun client assigné.'}), 400
        
        try:
            uploaded_files = request.files.getlist('documents')
            if not uploaded_files:
                return jsonify({'success': False, 'message': 'Aucun document fourni.'}), 400
            
            uploaded_filenames = []
            for file in uploaded_files:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    file_content = file.read()
                    
                    success = publication_service.upload_document(filename, file_content, trip.id)
                    if success:
                        uploaded_filenames.append(filename)
                    else:
                        return jsonify({'success': False, 'message': f'Échec upload: {filename}'}), 500
            
            trip.document_filenames = ','.join(uploaded_filenames)
            trip.status = 'sold'
            trip.sold_at = datetime.utcnow()
            db.session.commit()
            
            full_data = json.loads(trip.full_data_json)
            api_data = full_data.get('api_data', {})
            header_photo = api_data.get('photos', [''])[0] if api_data.get('photos') else ''
            
            msg = Message(
                subject=f'Confirmation de votre réservation - {trip.hotel_name}',
                recipients=[trip.client.email],
                html=render_template('payment_confirmation.html',
                    client_name=trip.client.to_dict()['full_name'],
                    hotel_name=trip.hotel_name,
                    destination=trip.destination,
                    header_photo=header_photo
                )
            )
            
            for filename in uploaded_filenames:
                file_content = publication_service.download_document(filename, trip.id)
                if file_content:
                    msg.attach(filename, 'application/octet-stream', file_content)
            
            mail.send(msg)
            
            return jsonify({'success': True, 'message': 'Vente finalisée et documents envoyés !'})
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erreur finalisation vente: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500

    # =========================================================================
    # 🆕 ROUTE 4: GÉNÉRER FACTURE
    # =========================================================================
    @app.route('/api/trip/<int:trip_id>/generate-invoice', methods=['POST'])
    @login_required
    def generate_invoice(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        if not trip.client:
            return jsonify({'success': False, 'message': 'Aucun client assigné.'}), 400
        
        try:
            data = request.get_json()
            client_name = data.get('client_name', trip.client.to_dict()['full_name'])
            client_address = data.get('client_address', '')
            client_tva = data.get('client_tva', '')
            
            invoice_number = f"VP-{datetime.now().strftime('%Y%m%d')}-{trip.id}"
            
            existing_invoice = Invoice.query.filter_by(invoice_number=invoice_number).first()
            if existing_invoice:
                invoice_number = f"{invoice_number}-{datetime.now().strftime('%H%M%S')}"
            
            new_invoice = Invoice(
                invoice_number=invoice_number,
                trip_id=trip.id
            )
            db.session.add(new_invoice)
            db.session.commit()
            
            full_data = json.loads(trip.full_data_json)
            form_data = full_data.get('form_data', {})
            
            date_start = datetime.strptime(form_data.get('date_start', ''), '%Y-%m-%d')
            date_end = datetime.strptime(form_data.get('date_end', ''), '%Y-%m-%d')
            number_of_nights = (date_end - date_start).days
            
            invoice_html = render_template('invoice_template.html',
                invoice_number=invoice_number,
                invoice_date=datetime.now().strftime('%d/%m/%Y'),
                client_name=client_name,
                client_address=client_address,
                client_tva=client_tva if client_tva else '',
                hotel_name=trip.hotel_name,
                date_start=date_start.strftime('%d/%m/%Y'),
                date_end=date_end.strftime('%d/%m/%Y'),
                number_of_nights=number_of_nights,
                total_price=trip.price
            )
            
            pdf = HTML(string=invoice_html).write_pdf()
            
            msg = Message(
                subject=f'Facture {invoice_number} - Voyages Privilèges',
                recipients=[trip.client.email],
                body=f'Bonjour,\n\nVeuillez trouver ci-joint votre facture {invoice_number}.\n\nCordialement,\nL\'équipe Voyages Privilèges'
            )
            msg.attach(f'{invoice_number}.pdf', 'application/pdf', pdf)
            mail.send(msg)
            
            return jsonify({'success': True, 'message': 'Facture générée et envoyée par email !'})
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erreur génération facture: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500

    # =========================================================================
    # 🆕 ROUTE 5: RENVOYER FACTURE
    # =========================================================================
    @app.route('/api/invoice/<int:invoice_id>/resend', methods=['POST'])
    @login_required
    def resend_invoice(invoice_id):
        invoice = Invoice.query.get_or_404(invoice_id)
        trip = invoice.trip
        
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        if not trip.client:
            return jsonify({'success': False, 'message': 'Aucun client assigné.'}), 400
        
        try:
            full_data = json.loads(trip.full_data_json)
            form_data = full_data.get('form_data', {})
            
            date_start = datetime.strptime(form_data.get('date_start', ''), '%Y-%m-%d')
            date_end = datetime.strptime(form_data.get('date_end', ''), '%Y-%m-%d')
            number_of_nights = (date_end - date_start).days
            
            invoice_html = render_template('invoice_template.html',
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.created_at.strftime('%d/%m/%Y'),
                client_name=trip.client.to_dict()['full_name'],
                client_address=trip.client.address or '',
                client_tva='',
                hotel_name=trip.hotel_name,
                date_start=date_start.strftime('%d/%m/%Y'),
                date_end=date_end.strftime('%d/%m/%Y'),
                number_of_nights=number_of_nights,
                total_price=trip.price
            )
            
            pdf = HTML(string=invoice_html).write_pdf()
            
            msg = Message(
                subject=f'Facture {invoice.invoice_number} - Voyages Privilèges',
                recipients=[trip.client.email],
                body=f'Bonjour,\n\nVoici de nouveau votre facture {invoice.invoice_number}.\n\nCordialement,\nL\'équipe Voyages Privilèges'
            )
            msg.attach(f'{invoice.invoice_number}.pdf', 'application/pdf', pdf)
            mail.send(msg)
            
            return jsonify({'success': True, 'message': 'Facture renvoyée par email !'})
            
        except Exception as e:
            print(f"❌ Erreur renvoi facture: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500

    # =========================================================================
    # FIN DES 5 NOUVELLES ROUTES
    # =========================================================================

    @app.route('/api/trip/<int:trip_id>/mark_sold', methods=['POST'])
    @login_required
    def mark_trip_sold(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403
        
        trip.status = 'sold'
        trip.sold_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Voyage marqué comme vendu !'})

    @app.route('/api/clients', methods=['GET', 'POST'])
    @login_required
    def handle_clients():
        if request.method == 'GET':
            search_term = request.args.get('search', '').lower()
            query = Client.query
            if search_term:
                search_filter = f"%{search_term}%"
                query = query.filter(
                    or_(
                        func.lower(Client.first_name).like(search_filter),
                        func.lower(Client.last_name).like(search_filter),
                        func.lower(Client.email).like(search_filter)
                    )
                )
            clients = query.order_by(Client.last_name).all()
            return jsonify([client.to_dict() for client in clients])
        
        if request.method == 'POST':
            data = request.get_json()
            try:
                new_client = Client(
                    first_name=data.get('first_name'),
                    last_name=data.get('last_name'),
                    email=data.get('email'),
                    phone=data.get('phone'),
                    address=data.get('address')
                )
                db.session.add(new_client)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Client créé !', 'client': new_client.to_dict()})
            except Exception as e:
                db.session.rollback()
                return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/client/<int:client_id>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def handle_client(client_id):
        client = Client.query.get_or_404(client_id)
        
        if request.method == 'GET':
            client_data = client.to_dict()
            client_data['trips'] = [trip.to_dict() for trip in client.trips]
            return jsonify(client_data)
        
        if g.user.role != 'admin':
             return jsonify({'success': False, 'message': 'Action réservée aux administrateurs.'}), 403

        if request.method == 'PUT':
            data = request.get_json()
            try:
                client.first_name = data.get('first_name', client.first_name)
                client.last_name = data.get('last_name', client.last_name)
                client.email = data.get('email', client.email)
                client.phone = data.get('phone', client.phone)
                client.address = data.get('address', client.address)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Client mis à jour !', 'client': client.to_dict()})
            except Exception as e:
                db.session.rollback()
                return jsonify({'success': False, 'message': str(e)}), 500
        
        if request.method == 'DELETE':
            db.session.delete(client)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Client supprimé.'})

    @app.route('/api/sellers', methods=['GET', 'POST'])
    @admin_required
    def handle_sellers():
        if request.method == 'GET':
            today = date.today()
            users_to_reset = User.query.filter(User.last_generation_date != today, User.role == 'vendeur').all()
            for user in users_to_reset:
                user.generation_count = 0
                user.last_generation_date = today
            if users_to_reset:
                db.session.commit()
            
            users = User.query.order_by(User.pseudo).all()
            return jsonify([user.to_dict() for user in users])
        
        if request.method == 'POST':
            data = request.get_json()
            try:
                hashed_password = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
                new_user = User(
                    username=data.get('username'),
                    password=hashed_password,
                    pseudo=data.get('pseudo'),
                    email=data.get('email'),
                    phone=data.get('phone'),
                    role='vendeur',
                    margin_percentage=int(data.get('margin_percentage', 80))
                )
                db.session.add(new_user)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Vendeur créé !', 'user': new_user.to_dict()})
            except Exception as e:
                db.session.rollback()
                return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/seller/<int:user_id>', methods=['GET', 'PUT'])
    @admin_required
    def handle_seller(user_id):
        user = User.query.get_or_404(user_id)
        
        if request.method == 'GET':
            return jsonify(user.to_dict())
        
        if request.method == 'PUT':
            data = request.get_json()
            try:
                user.pseudo = data.get('pseudo', user.pseudo)
                user.email = data.get('email', user.email)
                user.phone = data.get('phone', user.phone)
                user.margin_percentage = int(data.get('margin_percentage', user.margin_percentage))
                if data.get('password'):
                    user.password = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
                db.session.commit()
                return jsonify({'success': True, 'message': 'Vendeur mis à jour !', 'user': user.to_dict()})
            except Exception as e:
                db.session.rollback()
                return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/seller/<int:user_id>/add_quota', methods=['POST'])
    @admin_required
    def add_seller_quota(user_id):
        user = User.query.get_or_404(user_id)
        user.daily_generation_limit += 5
        db.session.commit()
        return jsonify({'success': True, 'message': f'Quota augmenté à {user.daily_generation_limit}'})

    def _get_sales_query():
        query = Trip.query.join(User).join(Client).filter(Trip.status == 'sold')
        if g.user.role == 'vendeur':
            query = query.filter(Trip.user_id == g.user.id)
        return query

    @app.route('/api/sales_report')
    @login_required
    def get_sales_report():
        sales = _get_sales_query().order_by(desc(Trip.sold_at)).all()
        report_data = []
        for sale in sales:
            full_data = json.loads(sale.full_data_json)
            total_margin = full_data.get('margin', 0)
            seller_margin = round(total_margin * (sale.user.margin_percentage / 100))
            vp_margin = total_margin - seller_margin
            report_data.append({
                'sold_at': sale.sold_at.strftime('%d/%m/%Y'),
                'hotel_name': sale.hotel_name,
                'client_full_name': sale.client.to_dict()['full_name'],
                'creator_pseudo': sale.user.pseudo,
                'price': sale.price,
                'total_margin': total_margin,
                'seller_margin': seller_margin,
                'vp_margin': vp_margin
            })
        return jsonify(report_data)

    @app.route('/api/export_sales')
    @login_required
    def export_sales():
        sales = _get_sales_query().order_by(Trip.sold_at).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date Vente', 'Vendeur', 'Client', 'Destination', 'Prix Total', 'Marge Totale', 'Marge Vendeur', 'Marge VP'])
        for sale in sales:
            full_data = json.loads(sale.full_data_json)
            total_margin = full_data.get('margin', 0)
            seller_margin = round(total_margin * (sale.user.margin_percentage / 100))
            vp_margin = total_margin - seller_margin
            writer.writerow([
                sale.sold_at.strftime('%Y-%m-%d'),
                sale.user.pseudo,
                sale.client.to_dict()['full_name'],
                sale.destination,
                sale.price,
                total_margin,
                seller_margin,
                vp_margin
            ])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=export_ventes.csv"})

    @app.route('/api/stats')
    @login_required
    def get_stats_data():
        twelve_months_ago = datetime.utcnow() - timedelta(days=365)
        query = Trip.query.filter(Trip.status == 'sold', Trip.sold_at >= twelve_months_ago)
        if g.user.role == 'vendeur':
            query = query.filter(Trip.user_id == g.user.id)
        sales = query.all()
        
        monthly_data = defaultdict(lambda: {'revenue': 0, 'margin': 0})
        for sale in sales:
            month = sale.sold_at.strftime('%Y-%m')
            monthly_data[month]['revenue'] += sale.price
            monthly_data[month]['margin'] += json.loads(sale.full_data_json).get('margin', 0)
        
        sorted_months = sorted(monthly_data.keys())
        monthly_performance = {
            'labels': [datetime.strptime(m, '%Y-%m').strftime('%b %y') for m in sorted_months],
            'revenues': [monthly_data[m]['revenue'] for m in sorted_months],
            'margins': [monthly_data[m]['margin'] for m in sorted_months]
        }

        top_sellers, top_destinations = {}, {}
        if g.user.role == 'admin':
            seller_margins, dest_revenues = defaultdict(int), defaultdict(int)
            for sale in sales:
                seller_margins[sale.user.pseudo] += round(json.loads(sale.full_data_json).get('margin', 0) * (sale.user.margin_percentage / 100))
                dest_revenues[sale.destination] += sale.price
            
            sorted_sellers = sorted(seller_margins.items(), key=lambda i: i[1], reverse=True)[:5]
            top_sellers = {'labels': [s[0] for s in sorted_sellers], 'values': [s[1] for s in sorted_sellers]}
            sorted_dests = sorted(dest_revenues.items(), key=lambda i: i[1], reverse=True)[:5]
            top_destinations = {'labels': [d[0] for d in sorted_dests], 'values': [d[1] for d in sorted_dests]}

        return jsonify({'monthly_performance': monthly_performance, 'top_sellers': top_sellers, 'top_destinations': top_destinations})

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
