import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import base64
import os
import time
from datetime import datetime

def get_secret(key, default=None):
    try:
        return st.secrets.get(key, default)
    except:
        return default

def init_firebase():
    if firebase_admin._apps:
        return True
    
    b64_key = get_secret("FIREBASE_KEY_BASE64")
    if not b64_key:
        st.error("Missing FIREBASE_KEY_BASE64 in Secrets")
        return False

    try:
        # Decode the key safely
        decoded_key = base64.b64decode(b64_key).decode("utf-8")
        
        # This dict uses the same values from your project
        cert_dict = {
            "type": "service_account",
            "project_id": "posterjukebox",
            "private_key_id": "5dfa6f9688d66a95835e469005de46d325ab5615",
            "private_key": decoded_key,
            "client_email": "firebase-adminsdk-fbsvc@posterjukebox.iam.gserviceaccount.com",
            "client_id": "102973933404996152824",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40posterjukebox.iam.gserviceaccount.com"
        }
        
        db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        return True
    except Exception as e:
        st.error(f"Final Attempt Failed: {e}")
        return False

# ... keep get_current_song and log_manual_history as they were ...
