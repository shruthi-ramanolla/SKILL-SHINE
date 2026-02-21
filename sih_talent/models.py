# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    school = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    badges = db.relationship('Badge', backref='user', lazy=True)
    uploads = db.relationship('Upload', backref='user', lazy=True)
    score = db.Column(db.Float, default=0.0)  # aggregate score

class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    talent_type = db.Column(db.String(50))
    score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100))
    description = db.Column(db.String(255))
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    description = db.Column(db.Text)
    start_at = db.Column(db.DateTime)
    end_at = db.Column(db.DateTime)
    reward_badge = db.Column(db.String(100))
