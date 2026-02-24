import streamlit as st
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
import re
import time
import random
import string

# ==========================================
# --- 1. CONFIG & PRODUCTION FIREBASE ---
# ==========================================

def load_key(key_name):
    if key_name in os.environ: return os.environ.get(key_name)
    try:
        if key_name in st.secrets: return st.secrets[key_name]
    except: pass
    return None

if "FIREBASE_CONFIG" in os.environ:
    try:
        service_account_info = json.loads(os.environ.get("FIREBASE_CONFIG"))
        cred = credentials.Certificate(service_account_info)
    except: cred = None
else:
    try: cred = credentials.Certificate("serviceAccountKey.json")
    except: cred = None

if cred and not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client() if firebase_admin._apps else None
SPOTIPY_CLIENT_ID = load_key("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = load_key("SPOTIPY_CLIENT_SECRET")
FIREBASE_BASE = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"

# ==========================================
# --- 2. PAGE SETUP & FIXED SIDEBAR CSS ---
# ==========================================

st.set_page_config(page_title="Jukebox Funk TV", layout="wide")

# This CSS fixes the "Unreadable Sidebar" and keeps the TV looking clean
st.markdown("""
    <style>
    /* Make Sidebar Text Visible */
    section[data-testid="stSidebar"] { background-color: #f0f2f6 !important; }
    section[data-testid="stSidebar"] .stMarkdown, 
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p {
        color: #000000 !important;
        font-weight: bold !important;
    }
    /* Kiosk Style for Main App */
    [data-testid="stAppViewContainer"] { background-color: #000000 !important; }
    .stAppDeployButton, footer { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# --- 3. HELPERS ---
# ==========================================

def log_event(venue_id, action, details=""):
    if db:
        try:
            db.collection("logs").add({
                "venue_id": venue_id, "action": action, "details": details,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
        except: pass

def get_saved_venue(): return st.query_params.get("venue_id", None)
def save_connection(vid): st.query_params["venue_id"] = vid
def clear_connection(): 
    if "venue_id" in st.query_params:
        st.query_params.clear()

# ==========================================
# --- 4. API & ENGINE ---
# ==========================================

def get_current_song_from_cloud(venue_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/now_playing.json"
    try:
        res = requests.get(url, timeout=5).json()
        if res and 'track' in res: return res['track'], res['artist']
    except: pass
    return None, None

def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        cover_url = results['albums']['items'][0]['images'][0]['url']
        cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")
        
        poster_w, poster_h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=40))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 140)))
        
        c_size = 1000 if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (100, 100))
        return poster
    except: return None

# ==========================================
# --- 5. APP LOGIC ---
# ==========================================

venue_id = get_saved_venue()

if not venue_id:
    # --- PAIRING SCREEN ---
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "timestamp": time.time()})

    st.markdown(f"<h1 style='text-align: center; color: white; margin-top: 20vh;'>LINK YOUR DISPLAY</h1>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center; color: #7C3AED; font-size: 8rem;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    
    time.sleep(3)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"])
        st.rerun()
    st.rerun()

else:
    # --- MAIN SIDEBAR (RESTORED FEATURES) ---
    with st.sidebar:
        st.header("⚙️ Controls")
        if st.button("🔴 Unpair Display", use_container_width=True):
            clear_connection()
            st.rerun()
        
        st.divider()
        mode = st.radio("Poster Source", ["Live Cloud Sync", "Manual Search"])
        orientation = st.radio("Orientation", ["Portrait", "Landscape"], index=0)
        
        if mode == "Manual Search":
            m_artist = st.text_input("Artist")
            m_album = st.text_input("Album")
            if st.button("Generate Poster"):
                st.session_state.current_poster = create_poster(m_album, m_artist, orientation)
    
    # --- DISPLAY AREA ---
    if mode == "Live Cloud Sync":
        if st.session_state.get('current_poster'):
            st.image(st.session_state.current_poster, use_container_width=True)
            
        @st.fragment(run_every=3)
        def sync():
            track, artist = get_current_song_from_cloud(venue_id)
            if track and track != st.session_state.get('last_track'):
                st.session_state.last_track = track
                # Try to find album name for better search
                sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
                res = sp.search(q=f"track:{track} artist:{artist}", type='track', limit=1)
                album = res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else track
                st.session_state.current_poster = create_poster(album, artist, orientation)
                st.rerun()
        sync()
    else:
        # Manual Display
        if st.session_state.get('current_poster'):
            st.image(st.session_state.current_poster, use_container_width=True)
