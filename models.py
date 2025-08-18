# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    full_data_json = db.Column(db.Text, nullable=False)
    
    hotel_name = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    
    status = db.Column(db.String(50), nullable=False, default='proposed')
    
    is_published = db.Column(db.Boolean, default=False)
    published_filename = db.Column(db.String(255), nullable=True)
    
    client_published_filename = db.Column(db.String(255), nullable=True)
    
    client_first_name = db.Column(db.String(100), nullable=True)
    client_last_name = db.Column(db.String(100), nullable=True)
    client_email = db.Column(db.String(120), nullable=True)
    client_phone = db.Column(db.String(50), nullable=True) # --- CHAMP AJOUTÉ ---

    stripe_payment_link = db.Column(db.Text, nullable=True)

    down_payment_amount = db.Column(db.Integer, nullable=True)
    balance_due_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_at = db.Column(db.DateTime, nullable=True)
    sold_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        """Retourne une représentation dictionnaire du voyage."""
        return {
            'id': self.id,
            'hotel_name': self.hotel_name,
            'destination': self.destination,
            'price': self.price,
            'status': self.status,
            'is_published': self.is_published,
            'published_filename': self.published_filename,
            'client_published_filename': self.client_published_filename,
            'client_full_name': f"{self.client_first_name or ''} {self.client_last_name or ''}".strip(),
            'client_email': self.client_email, # --- LIGNE AJOUTÉE ---
            'client_phone': self.client_phone, # --- LIGNE AJOUTÉE ---
            'created_at': self.created_at.strftime('%d/%m/%Y'),
            'assigned_at': self.assigned_at.strftime('%d/%m/%Y') if self.assigned_at else None,
            'sold_at': self.sold_at.strftime('%d/%m/%Y') if self.sold_at else None,
            'down_payment_amount': self.down_payment_amount,
            'balance_due_date': self.balance_due_date.strftime('%d/%m/%Y') if self.balance_due_date else None,
        }

    def __repr__(self):
        return f'<Trip {self.id}: {self.hotel_name} - {self.status}>'
