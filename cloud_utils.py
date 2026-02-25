import streamlit as st
import base64  # Add this at the very top of the file
import json
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
    except Exception:
        return default

import base64  # Add this at the very top of the file

import json

def init_firebase():
    def init_firebase():
    if firebase_admin._apps:
        return True
    
    service_account_json = get_secret("FIREBASE_SERVICE_ACCOUNT_JSON")
    db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"
    
    if not service_account_json:
        return False

    try:
        # We ensure the string is treated as a clean JSON format
        # and replace any literal '\n' text with actual newlines
        clean_json = service_account_json.replace("\\n", "\n")
        cert_dict = json.loads(clean_json)
            
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        return True
    except Exception as e:
        st.error(f"Firebase Connection Error: {e}")
        return False

def get_current_song(venue_id):
    try:
        ref = db.reference(f"venues/{venue_id}/now_playing")
        data = ref.get()
        if data:
            return data.get('track'), data.get('artist')
    except:
        pass
    return None, None

def log_manual_history(venue_id, album, artist):
    try:
        record_id = str(int(time.time() * 1000))
        db.reference(f"venues/{venue_id}/history/{record_id}").set({
            "id": record_id, "track": album, "artist": artist,
            "time": datetime.now().strftime("%H:%M"), "type": "manual"
        })
    except:
        pass
