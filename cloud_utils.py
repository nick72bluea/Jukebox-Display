import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import os
import time
from datetime import datetime

def get_secret(key, default=None):
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except Exception:
        return default

def init_firebase():
    if firebase_admin._apps:
        return True
    
    # We fetch the table we just created in secrets
    service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")
    db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"
    
    if not service_account_info:
        st.error("Missing FIREBASE_SERVICE_ACCOUNT in Secrets")
        return False

    try:
        # Convert Streamlit secrets proxy to a real dict
        cert_dict = dict(service_account_info)
        
        # Ensure the private key is clean
        if "private_key" in cert_dict:
            cert_dict["private_key"] = cert_dict["private_key"].strip()
            
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
