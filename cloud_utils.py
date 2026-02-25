import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import os
import json

def get_secret(key, default=None):
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except:
        return default

def init_firebase():
    """Initializes Firebase and returns True if successful."""
    if firebase_admin._apps:
        return True
        
    service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")
    db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"
    
    if not service_account_info:
        st.error("❌ FIREBASE_SERVICE_ACCOUNT not found in Secrets.")
        return False

    try:
        if isinstance(service_account_info, str):
            cert_dict = json.loads(service_account_info)
        else:
            cert_dict = service_account_info
        
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        return True
    except Exception as e:
        st.error(f"❌ Firebase Init Failed: {e}")
        return False
