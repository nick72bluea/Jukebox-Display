import streamlit as st
import os
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

# --- 1. CONFIG & CREDENTIALS ---
SPOTIPY_CLIENT_ID = os.environ.get('SPOTIPY_CLIENT_ID', '02c1d6fcc3a149138d815e4036c0c36e')
SPOTIPY_CLIENT_SECRET = os.environ.get('SPOTIPY_CLIENT_SECRET', '7e96739194134d83ba322af5cefd9af4')
FIREBASE_BASE = os.environ.get('FIREBASE_BASE', "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app")

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# --- THE "ALWAYS VISIBLE" SIDEBAR BUTTON & KIOSK CSS ---
st.markdown("""
    <style>
    /* 1. Hide default Streamlit clutter */
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { display: none !important; }
    [data-testid="stHeader"] { background: transparent !important; }

    /* 2. FORCE THE SIDEBAR OPENER TO BE VISIBLE */
    /* This targets the button that opens the sidebar */
    button[kind="headerNoContext"] {
        background-color: rgba(255, 255, 255, 0.2) !important; /* Semi-transparent white */
        border: 1px solid rgba(255, 255, 255, 0.5) !important;
        border-radius: 50% !important;
        position: fixed !important;
        top: 15px !important;
        left: 15px !important;
        z-index: 999999 !important;
        width: 50px !important;
        height: 50px !important;
    }
    
    /* Make the icon inside the button bright white */
    button[kind="headerNoContext"] svg {
        fill: white !important;
        stroke: white !important;
    }

    /* 3. True Black Kiosk Background */
    [data-testid="stAppViewContainer"], .stApp { 
        background-color: #000000 !important; 
    }
    
    .block-container { padding: 0px !important; margin: 0px !important; }
    
    /* 4. Full Screen Image logic */
    [data-testid="stImage"] img { 
        width: 100vw !important; 
        height: 100vh !important; 
        object-fit: cover !important; 
    }
    </style>
""", unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS ---
def get_saved_venue(): return st.query_params.get("venue_id", None)
def get_saved_display(): return st.query_params.get("display_id", None)
def save_connection(vid, did):
    st.query_params["venue_id"] = vid
    st.query_params["display_id"] = did
def clear_connection():
    st.query_params.clear()

# --- INIT SESSION STATE ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None

# --- HELPERS ---
def get_current_song_from_cloud(venue_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/now_playing.json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and 'track' in data: return data['track'], data['artist']
    except: pass 
    return None, None

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else None
    except: return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        cover_url = results['albums']['items'][0]['images'][0]['url']
        cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")
        
        def get_font(size):
            paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
            for p in paths:
                try: return ImageFont.truetype(p, size)
                except: continue
            return ImageFont.load_default()

        # Simple High-Contrast Layout
        poster_w, poster_h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=40))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        c_size = 1000 if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (100, 100))
        draw.text((100, poster_h - 200), artist_name.upper(), font=get_font(80), fill="white")
        
        return poster
    except: return None

# --- CORE LOGIC ---
venue_id = get_saved_venue()
display_id = get_saved_display()

if not venue_id:
    # PAIRING
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "venue_id": "", "timestamp": time.time()})

    st.markdown(f"<h1 style='text-align: center; color: white; margin-top: 30vh; font-size: 8rem;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    time.sleep(3)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], "disp_render")
        st.rerun()
    st.rerun()

else:
    # SIDEBAR
    with st.sidebar:
        st.header("Settings")
        orient = st.radio("Layout", ["Portrait", "Landscape"])
        live = st.toggle("Cloud Sync", value=True)
        st.divider()
        st.subheader("Manual Search")
        m_art = st.text_input("Artist", "Oasis")
        m_alb = st.text_input("Album", "Definitely Maybe")
        if st.button("Generate"):
            st.session_state.current_poster = create_poster(m_alb, m_art, orient)
        if st.button("Unpair"):
            clear_connection()
            st.rerun()

    # DISPLAY
    if live:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        
        @st.fragment(run_every=3)
        def sync():
            t, a = get_current_song_from_cloud(venue_id)
            if t and t != st.session_state.last_track:
                st.session_state.last_track = t
                alb = get_album_from_track(t, a)
                if alb:
                    st.session_state.current_poster = create_poster(alb, a, orient)
                    st.rerun()
        sync()
    else:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
