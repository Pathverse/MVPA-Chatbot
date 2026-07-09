"""Initialises the shared Firestore client used by the rest of the db package."""
import firebase_admin
from firebase_admin import credentials, firestore

from config import GOOGLE_APPLICATION_CREDENTIALS

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(GOOGLE_APPLICATION_CREDENTIALS))

db = firestore.client()
