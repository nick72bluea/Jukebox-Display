import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import os
import json
import time
from datetime import datetime

def get_secret(key, default=None):
    """Retrieves secret from environment or Streamlit secrets."""
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except Exception:
        return default

def init_firebase():
    """Initializes Firebase and returns True if successful."""
    if firebase_admin._apps:
        return True
        
    service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")
    db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"
    
    if not service_account_info:
        return False

    try:
        # Convert the Streamlit secret object to a dictionary
        cert_dict = dict(service_account_info)
        
        # Clean up the private key
        if "private_key" in cert_dict:
            # This handles both the literal and escaped newlines
            pk = cert_dict["private_key"].replace("\\n", "\n")
            cert_dict["private_key"] = pk.strip()
            
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        return True
    except Exception as e:
        st.error(f"❌ Firebase Init Failed: {e}")
        return False

def get_current_song(venue_id):
    """Fetches the track and artist currently playing at the venue."""
    try:
        ref = db.reference(f"venues/{venue_id}/now_playing")
        data = ref.get()
        if data:
            return data.get('track'), data.get('artist')
    except Exception:
        pass
    return None, None

def log_manual_history(venue_id, album, artist):
    """Logs a manually searched album to the venue history."""
    try:
        record_id = str(int(time.time() * 1000))
        db.reference(f"venues/{venue_id}/history/{record_id}").set({
            "id": record_id,
            "track": album,
            "artist": artist,
            "time": datetime.now().strftime("%H:%M"),
            "type": "manual"
        })
    except Exception:
        pass
