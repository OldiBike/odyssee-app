# app.py - Version finale, fusionnée et corrigée
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
from sqlalchemy import func, extract, desc
from collections import defaultdict

from config import Config
from models import db, Trip, Invoice, User, Client
from services import RealAPIGatherer, generate_travel_page_html, PublicationService
import stripe

mail = Mail()
migrate = Migrate()
bcrypt = Bcrypt()

def create_app(config_class=Config):
    """Crée et configure l'instance de l'application Flask."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app, resources={r"/api/*": {"origins": ["https://voyages-privileges.be", "https://www.voyages-privileges.be"]}})

    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    
    if app.config.get('STRIPE_API_KEY'):
        stripe.api_key = app.config['STRIPE_API_KEY']

    # Crée les comptes admin au démarrage si ils n'existent pas
    with app.app_context():
        for i in [1, 2]:
            admin_user = os.environ.get(f'ADMIN_{i}_USERNAME')
            if admin_user and not User.query.filter_by(username=admin_user).first():
                admin_pass = os.environ.get(f'ADMIN_{i}_PASSWORD')
                admin_email = os.environ.get(f'ADMIN_{i}_EMAIL')
                admin_pseudo = os.environ.get(f'ADMIN_{i}_PSEUDO')
                if all([admin_pass, admin_email, admin_pseudo]):
                    hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
                    new_admin = User(username=admin_user, password=hashed_password, pseudo=admin_pseudo, email=admin_email, role='admin')
                    db.session.add(new_admin)
                    print(f"✅ Compte admin '{admin_user}' créé.")
        db.session.commit()

    publication_service = PublicationService(app.config)

    # --- DECORATEURS D'AUTHENTIFICATION ---
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            # Charge l'utilisateur actuel dans le contexte global 'g' pour un accès facile
            g.user = User.query.get(session['user_id'])
            if not g.user:
                session.clear()
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    def admin_required(f):
        @wraps(f)
        @login_required # Assure que l'utilisateur est d'abord connecté
        def decorated_function(*args, **kwargs):
            if g.user.role != 'admin':
                return jsonify({'success': False, 'message': 'Accès non autorisé.'}), 403
            return f(*args, **kwargs)
        return decorated_function

    # --- ROUTES D'AUTHENTIFICATION ET DE NAVIGATION ---
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            print(f"DEBUG: Username reçu: '{username}'")
            print(f"DEBUG: Password reçu: '{password}'")
            
            user = User.query.filter_by(username=username).first()
            print(f"DEBUG: User trouvé: {user}")
            
            if user:
                is_valid = bcrypt.check_password_hash(user.password, password)
                print(f"DEBUG: Mot de passe valide: {is_valid}")
                
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

    # --- ROUTES DES PAGES PRINCIPALES ---
    @app.route('/generation')
    @login_required
    def generation_tool():
        return render_template('generation.html', google_api_key=app.config['GOOGLE_API_KEY'], user_margin=g.user.margin_percentage)

    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('dashboard.html', view_mode=request.args.get('view', 'proposed'), site_public_url=app.config.get('SITE_PUBLIC_URL', ''), google_api_key=app.config['GOOGLE_API_KEY'])

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

    # --- API POUR LA GÉNÉRATION DE VOYAGES ---
    @app.route('/api/generate-preview', methods=['POST'])
    @login_required
    def generate_preview():
        if g.user.role == 'vendeur':
            today = date.today()
            if g.user.last_generation_date != today:
                g.user.generation_count = 0
                g.user.daily_generation_limit = 5
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

    # --- API CRUD POUR LES VOYAGES (TRIPS) ---
    @app.route('/api/trips', methods=['POST'])
    @login_required
    def save_trip():
        data = request.get_json()
        form_data = data.get('form_data')
        client_id = form_data.get('client_id') if form_data.get('client_id') else None

        new_trip = Trip(
            user_id=g.user.id, client_id=client_id, full_data_json=json.dumps(data), hotel_name=form_data.get('hotel_name'),
            destination=form_data.get('destination'), price=int(form_data.get('pack_price') or 0),
            status='assigned' if client_id else 'proposed', is_ultra_budget=form_data.get('is_ultra_budget', False)
        )
        if new_trip.status == 'assigned':
            new_trip.assigned_at = datetime.utcnow()

        db.session.add(new_trip)
        db.session.commit()
        
        if new_trip.status == 'assigned':
            client_filename = publication_service.publish_client_offer(new_trip)
            if client_filename:
                new_trip.client_published_filename = client_filename
                db.session.commit()
            else:
                db.session.delete(new_trip)
                db.session.commit()
                return jsonify({'success': False, 'message': 'La publication de la page client a échoué. Le voyage n\'a pas été enregistré.'}), 500

        return jsonify({'success': True, 'message': 'Voyage enregistré !', 'trip': new_trip.to_dict()})

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
            trip_details['full_data_json'] = trip.full_data_json # Ajouter les données complètes pour l'édition
            return jsonify(trip_details)

        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403

        if request.method == 'DELETE':
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
        
        should_publish = request.get_json().get('publish', False)
        
        try:
            if should_publish and not trip.is_published:
                filename = publication_service.publish_public_offer(trip)
                if filename:
                    trip.is_published = True
                    trip.published_filename = filename
                    db.session.commit()
                    public_url = f"{app.config.get('SITE_PUBLIC_URL', '')}/offres/{filename}"
                    return jsonify({'success': True, 'message': 'Voyage publié !', 'url': public_url, 'trip': trip.to_dict()})
                else:
                    return jsonify({'success': False, 'message': 'Échec de la publication.'}), 500
            elif not should_publish and trip.is_published:
                if publication_service.unpublish(trip.published_filename):
                    trip.is_published = False
                    trip.published_filename = None
                    db.session.commit()
                    return jsonify({'success': True, 'message': 'Publication retirée.', 'trip': trip.to_dict()})
                else:
                    return jsonify({'success': False, 'message': 'Échec de la dépublication.'}), 500
            else:
                return jsonify({'success': True, 'message': 'Aucun changement nécessaire.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
            
    # --- ROUTE CORRIGÉE POUR L'ASSIGNATION ---
    @app.route('/api/trip/<int:trip_id>/assign', methods=['POST'])
    @login_required
    def assign_trip(trip_id):
        trip = Trip.query.get_or_404(trip_id)
        if g.user.role != 'admin' and trip.user_id != g.user.id:
            return jsonify({'success': False, 'message': 'Action non autorisée.'}), 403

        client_id = request.get_json().get('client_id')
        if not client_id:
            return jsonify({'success': False, 'message': 'ID de client manquant.'}), 400

        trip.client_id = client_id
        trip.status = 'assigned'
        trip.assigned_at = datetime.utcnow()
        
        client_filename = publication_service.publish_client_offer(trip)
        if client_filename:
            trip.client_published_filename = client_filename
            db.session.commit()
            return jsonify({'success': True, 'message': 'Voyage assigné au client avec succès !'})
        else:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Erreur lors de la publication de la page client.'}), 500

    @app.route('/api/trip/<int:trip_id>/repropose', methods=['POST'])
    @login_required
    def repropose_trip(trip_id):
        original_trip = Trip.query.get_or_404(trip_id)
        client_id = request.get_json().get('client_id')
        if not client_id:
            return jsonify({'success': False, 'message': 'Veuillez sélectionner un client.'}), 400

        new_trip = Trip(
            user_id=g.user.id, client_id=client_id, full_data_json=original_trip.full_data_json,
            hotel_name=original_trip.hotel_name, destination=original_trip.destination, price=original_trip.price,
            status='assigned', is_ultra_budget=original_trip.is_ultra_budget, assigned_at=datetime.utcnow()
        )
        db.session.add(new_trip)
        db.session.commit()

        client_filename = publication_service.publish_client_offer(new_trip)
        if client_filename:
            new_trip.client_published_filename = client_filename
            db.session.commit()
            return jsonify({'success': True, 'message': 'Voyage reproposé et assigné au client.'})
        else:
            db.session.delete(new_trip)
            db.session.commit()
            return jsonify({'success': False, 'message': 'La publication de la nouvelle offre a échoué.'}), 500

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

    # --- API CRUD POUR LES CLIENTS ---
    @app.route('/api/clients', methods=['GET', 'POST'])
    @login_required
    def handle_clients():
        if request.method == 'GET':
            clients = Client.query.order_by(Client.last_name).all()
            return jsonify([client.to_dict() for client in clients])
        
        if request.method == 'POST':
            data = request.get_json()
            try:
                new_client = Client(
                    first_name=data.get('first_name'), last_name=data.get('last_name'),
                    email=data.get('email'), phone=data.get('phone'), address=data.get('address')
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

    # --- API CRUD POUR LES VENDEURS (ADMIN SEULEMENT) ---
    @app.route('/api/sellers', methods=['GET', 'POST'])
    @admin_required
    def handle_sellers():
        if request.method == 'GET':
            today = date.today()
            users_to_reset = User.query.filter(User.last_generation_date != today, User.role == 'vendeur').all()
            for user in users_to_reset:
                user.generation_count = 0
                user.daily_generation_limit = 5
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
                    username=data.get('username'), password=hashed_password, pseudo=data.get('pseudo'),
                    email=data.get('email'), phone=data.get('phone'), role='vendeur',
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

    # --- API POUR LES RAPPORTS ET STATISTIQUES ---
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
                'sold_at': sale.sold_at.strftime('%d/%m/%Y'), 'hotel_name': sale.hotel_name,
                'client_full_name': sale.client.to_dict()['full_name'], 'creator_pseudo': sale.user.pseudo,
                'price': sale.price, 'total_margin': total_margin,
                'seller_margin': seller_margin, 'vp_margin': vp_margin
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
                sale.sold_at.strftime('%Y-%m-%d'), sale.user.pseudo, sale.client.to_dict()['full_name'],
                sale.destination, sale.price, total_margin, seller_margin, vp_margin
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

# Point d'entrée pour Gunicorn et les tests locaux
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
else:
    app = create_app()

