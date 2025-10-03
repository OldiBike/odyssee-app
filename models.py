# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import json

db = SQLAlchemy()

# NOUVEAU MODÈLE : User
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    pseudo = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='vendeur')  # 'vendeur' ou 'admin'
    margin_percentage = db.Column(db.Integer, default=80)

    # Pour la gestion des quotas
    generation_count = db.Column(db.Integer, default=0)
    last_generation_date = db.Column(db.Date, default=date.today)
    daily_generation_limit = db.Column(db.Integer, default=5)

    # Relation avec les voyages
    trips = db.relationship('Trip', backref='user', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'pseudo': self.pseudo,
            'email': self.email,
            'phone': self.phone,
            'role': self.role,
            'margin_percentage': self.margin_percentage,
            'generation_usage': f"{self.generation_count} / {self.daily_generation_limit}"
        }

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'

# NOUVEAU MODÈLE : Client
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=True)

    # Relation avec les voyages
    trips = db.relationship('Trip', backref='client', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': f"{self.first_name} {self.last_name}",
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
            'address': self.address
        }

    def __repr__(self):
        return f'<Client {self.first_name} {self.last_name}>'

# MODÈLE MIS À JOUR : Trip
class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Nouvelles clés étrangères pour les relations
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=True)

    full_data_json = db.Column(db.Text, nullable=False)
    
    hotel_name = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    
    status = db.Column(db.String(50), nullable=False, default='proposed')
    
    is_published = db.Column(db.Boolean, default=False)
    published_filename = db.Column(db.String(255), nullable=True)
    
    is_ultra_budget = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    
    client_published_filename = db.Column(db.String(255), nullable=True)
    
    # Les champs client_* sont maintenant dans la table Client
    # client_first_name, client_last_name, etc. sont supprimés ici.

    stripe_payment_link = db.Column(db.Text, nullable=True)
    down_payment_amount = db.Column(db.Integer, nullable=True)
    balance_due_date = db.Column(db.Date, nullable=True)
    
    document_filenames = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_at = db.Column(db.DateTime, nullable=True)
    sold_at = db.Column(db.DateTime, nullable=True)
    
    invoices = db.relationship('Invoice', backref='trip', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        """Retourne une représentation dictionnaire du voyage."""
        full_data = json.loads(self.full_data_json)
        form_data = full_data.get('form_data', {})
        
        client_full_name = self.client.to_dict()['full_name'] if self.client else None
        client_email = self.client.email if self.client else None
        client_phone = self.client.phone if self.client else None

        return {
            'id': self.id,
            'user_id': self.user_id,
            'creator_pseudo': self.user.pseudo if self.user else 'N/A',
            'hotel_name': self.hotel_name,
            'destination': self.destination,
            'price': self.price,
            'status': self.status,
            'is_published': self.is_published,
            'published_filename': self.published_filename,
            'is_ultra_budget': self.is_ultra_budget,
            'client_published_filename': self.client_published_filename,
            'client_full_name': client_full_name,
            'client_email': client_email,
            'client_phone': client_phone,
            'created_at': self.created_at.strftime('%d/%m/%Y'),
            'assigned_at': self.assigned_at.strftime('%d/%m/%Y') if self.assigned_at else None,
            'sold_at': self.sold_at.strftime('%d/%m/%Y') if self.sold_at else None,
            'down_payment_amount': self.down_payment_amount,
            'balance_due_date': self.balance_due_date.strftime('%Y-%m-%d') if self.balance_due_date else None,
            'date_start': form_data.get('date_start'),
            'date_end': form_data.get('date_end'),
            'document_filenames': self.document_filenames.split(',') if self.document_filenames else [],
            'invoices': [invoice.to_dict() for invoice in self.invoices]
        }

    def __repr__(self):
        return f'<Trip {self.id}: {self.hotel_name} - {self.status}>'

# MODÈLE INCHANGÉ : Invoice
class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'created_at': self.created_at.strftime('%d/%m/%Y')
        }
