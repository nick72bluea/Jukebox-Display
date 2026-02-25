import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import os
import json

def get_secret(key, default=None):
    """Retrieves secret from environment or Streamlit secrets."""
    if key in os.environ:
        return os.environ.get(key)
    try:
        # This handles both the flat key and the dictionary block
        return st.secrets[key]
    except Exception:
        return default

def init_firebase():
    """Initializes Firebase and returns True if successful."""
    if firebase_admin._apps:
        return True
        
    # Look for the [FIREBASE_SERVICE_ACCOUNT] block from your Secrets
    service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")
    db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"
    
    if not service_account_info:
        st.error("❌ FIREBASE_SERVICE_ACCOUNT block not found in Secrets.")
        return False

    try:
        # Streamlit converts TOML sections into AttrDict/Dict automatically.
        # If it's a string (old JSON way), we parse it. If it's a dict, we use it directly.
        if isinstance(service_account_info, str):
            cert_dict = json.loads(service_account_info)
        else:
            # This converts the Streamlit Secret object to a standard Python dict
            cert_dict = dict(service_account_info)
        
        # Ensure the private key handles the newline characters correctly
        if "private_key" in cert_dict:
            cert_dict["private_key"] = cert_dict["private_key"].replace("\\n", "\n")
            
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        return True
    except Exception as e:
        st.error(f"❌ Firebase Init Failed: {e}")
        return False
