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
# --- 2. THE "SLICK DARK" SIDEBAR CSS ---
# ==========================================

st.set_page_config(page_title="Jukebox Funk TV", layout="wide")

st.markdown("""
    <style>
    /* Main TV Area */
    [data-testid="stAppViewContainer"], .stApp {
        background-color: #000000 !important;
    }
    
    /* Sidebar: Pure Black Background */
    [data-testid="stSidebar"] {
        background-color: #000000 !important;
        border-right: 1px solid #222222;
    }

    /* Sidebar Text: Light Grey/Silver */
    [data-testid="stSidebar"] .stMarkdown, 
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #AAAAAA !important;
        font-family: 'Inter', sans-serif;
    }

    /* Sidebar Inputs */
    [data-testid="stSidebar"] input {
        background-color: #1A1A1A !important;
        color: #FFFFFF !important;
        border: 1px solid #333333 !important;
    }

    /* Sidebar Buttons */
    [data-testid="stSidebar"] button {
        background-color: #1A1A1A !important;
        color: #AAAAAA !important;
        border: 1px solid #333333 !important;
    }

    /* Hide Streamlit Bloat */
    [data-testid="stToolbar"], .stAppDeployButton, footer {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# --- 3. HELPERS ---
# ==========================================

def get_saved_venue(): return st.query_params.get("venue_id", None)
def save_connection(vid): st.query_params["venue_id"] = vid
def clear_connection(): st.query_params.clear()

# ==========================================
# --- 4. ENGINE ---
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
        # Search strategy: use album if provided, otherwise search for top album by artist
        query = f"album:{album_name} artist:{artist_name}" if album_name else f"artist:{artist_name}"
        results = sp.search(q=query, type='album', limit=1)
        
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
# --- 5. LOGIC & UI ---
# ==========================================

venue_id = get_saved_venue()

if not venue_id:
    # PAIRING ROOM
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "timestamp": time.time()})

    st.markdown(f"<h1 style='text-align: center; color: #666666; margin-top: 25vh;'>LINK DISPLAY</h1>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center; color: #FFFFFF; font-size: 8rem;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    
    time.sleep(3)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"])
        st.rerun()
    st.rerun()

else:
    # MAIN CONTROL PANEL
    with st.sidebar:
        st.subheader("⚙️ CONTROLS")
        if st.button("🔴 UNPAIR DISPLAY", use_container_width=True):
            clear_connection()
            st.rerun()
        
        st.divider()
        mode = st.radio("POSTER MODE", ["Live Sync", "Manual Search"])
        orientation = st.radio("LAYOUT", ["Portrait", "Landscape"])
        
        st.divider()
        # RESTORED MANUAL FIELDS
        st.write("🔍 MANUAL SEARCH")
        manual_artist = st.text_input("Artist Name", placeholder="e.g. Fleetwood Mac")
        manual_album = st.text_input("Album Name (Optional)", placeholder="e.g. Rumours")
        
        if st.button("🚀 GENERATE POSTER", use_container_width=True):
            with st.spinner("Fetching..."):
                st.session_state.current_poster = create_poster(manual_album, manual_artist, orientation)
                st.session_state.last_mode = "Manual"

    # DISPLAY AREA
    if mode == "Live Sync":
        if st.session_state.get('current_poster'):
            st.image(st.session_state.current_poster, use_container_width=True)
            
        @st.fragment(run_every=3)
        def sync_loop():
            track, artist = get_current_song_from_cloud(venue_id)
            if track and track != st.session_state.get('last_track'):
                st.session_state.last_track = track
                # Auto-fetch poster
                st.session_state.current_poster = create_poster(track, artist, orientation)
                st.rerun()
        sync_loop()
    else:
        # Show manually generated poster
        if st.session_state.get('current_poster'):
            st.image(st.session_state.current_poster, use_container_width=True)
