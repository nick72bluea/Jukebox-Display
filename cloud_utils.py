import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import os
import json
import time
from datetime import datetime

def get_secret(key, default=None):
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except:
        return default

def init_firebase():
    """Initializes Firebase Admin SDK and returns the database base URL."""
    service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")
    db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"
    
    if service_account_info and not firebase_admin._apps:
        try:
            if isinstance(service_account_info, str):
                cert_dict = json.loads(service_account_info)
            else:
                cert_dict = service_account_info
            
            cred = credentials.Certificate(cert_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        except Exception as e:
            st.error(f"Firebase Init Error: {e}")
    return db_url

def get_current_song(venue_id):
    try:
        ref = db.reference(f"venues/{venue_id}/now_playing")
        data = ref.get()
        if data: return data.get('track'), data.get('artist')
    except: pass
    return None, None

def log_manual_history(venue_id, album, artist):
    try:
        record_id = str(int(time.time() * 1000))
        db.reference(f"venues/{venue_id}/history/{record_id}").set({
            "id": record_id,
            "track": album,
            "artist": artist,
            "time": datetime.now().strftime("%H:%M"),
            "type": "manual"
        })
    except: pass
