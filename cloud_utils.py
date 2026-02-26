import requests
import time
from datetime import datetime
import os
import streamlit as st

def get_cred(key):
    if key in os.environ:
        return os.environ[key]
    try:
        return st.secrets[key]
    except Exception:
        return None

FIREBASE_BASE = get_cred("FIREBASE_BASE")



def get_current_song_from_cloud(venue_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/now_playing.json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and 'track' in data and 'artist' in data:
                return data['track'], data['artist']
    except Exception: pass 
    return None, None

def log_manual_history(venue_id, album, artist):
    record_id = str(int(time.time() * 1000))
    url = f"{FIREBASE_BASE}/venues/{venue_id}/history/{record_id}.json"
    payload = {
        "id": record_id,
        "track": album,
        "artist": artist,
        "time": datetime.now().strftime("%H:%M"),
        "type": "manual"
    }
    try: requests.put(url, json=payload, timeout=3)
    except Exception: pass

def init_pairing_code(code, display_id):
    url = f"{FIREBASE_BASE}/pairing_codes/{code}.json"
    payload = {"status": "waiting", "display_id": display_id, "timestamp": time.time()}
    try: requests.put(url, json=payload, timeout=3)
    except Exception: pass

def check_pairing_status(code):
    url = f"{FIREBASE_BASE}/pairing_codes/{code}.json"
    try:
        res = requests.get(url, timeout=5).json()
        if res and res.get("status") == "linked" and res.get("venue_id"):
            requests.delete(url)
            return res["venue_id"]
    except Exception: pass
    return None

def check_if_unpaired(venue_id, display_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/displays/{display_id}.json"
    try:
        res = requests.get(url)
        if res.status_code == 200 and res.json() is None:
            return True # Missing from database = unpaired
    except Exception: pass
    return False

def unpair_from_cloud(venue_id, display_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/displays/{display_id}.json"
    try: requests.delete(url)
    except Exception: pass


def check_subscription_status(venue_id):
    """Checks if the venue has an active Pro subscription."""
    url = f"{FIREBASE_BASE}/venues/{venue_id}.json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, dict):
                # If isPro is True, return True. Otherwise return False.
                return data.get('isPro', False)
    except Exception: 
        pass 
    return False

