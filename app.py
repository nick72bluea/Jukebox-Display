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
    initial_sidebar_state="expanded" 
)

# --- THE "SIDEBAR SAVIOR" CSS ---
st.markdown("""
    <style>
    /* 1. Hide Toolbar but keep the Sidebar Toggle area */
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { display: none !important; }
    
    /* 2. BRUTE FORCE THE SIDEBAR TOGGLE VISIBILITY */
    /* This makes the 'Open Sidebar' arrow huge and white so you can't miss it */
    [data-testid="collapsedControl"] {
        background-color: rgba(124, 58, 237, 0.8) !important; /* Purple brand color */
        border-radius: 0 10px 10px 0 !important;
        width: 50px !important;
        height: 50px !important;
        top: 20px !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        z-index: 1000000 !important;
    }
    
    [data-testid="collapsedControl"] svg {
        fill: white !important;
        width: 30px !important;
        height: 30px !important;
    }

    /* 3. True Black Kiosk Background */
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
    }
    
    /* 4. Remove all padding for edge-to-edge posters */
    .block-container { padding: 0px !important; margin: 0px !important; max-width: 100vw !important; }
    
    [data-testid="stImage"] img { 
        width: 100vw !important; 
        height: 100vh !important; 
        object-fit: cover !important; 
    }
    
    /* 5. Sidebar Styling: Keep it dark but readable */
    [data-testid="stSidebar"] {
        background-color: #111111 !important;
        border-right: 1px solid #333333;
    }
    </style>
""", unsafe_allow_html=True)

# --- YOUR ORIGINAL PERSISTENCE HELPERS ---
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

# --- API HELPERS ---
def get_current_song_from_cloud(venue_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/now_playing.json"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            d = res.json()
            if d and 'track' in d: return d['track'], d['artist']
    except: pass 
    return None, None

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else None
    except: return None

# --- POSTER GENERATOR (Original Logic + Linux Fonts) ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        cover_url = results['albums']['items'][0]['images'][0]['url']
        cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")
        
        def get_safe_font(size):
            paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
            for p in paths:
                try: return ImageFont.truetype(p, size)
                except: continue
            return ImageFont.load_default()

        poster_w, poster_h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=40))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        c_size = 1000 if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (100, 100))
        draw.text((100, poster_h - 200), artist_name.upper(), font=get_safe_font(70), fill="white")
        
        return poster
    except: return None

# --- MAIN APP ROUTING ---
venue_id = get_saved_venue()
display_id = get_saved_display()

if not venue_id:
    # PAIRING ROOM
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "timestamp": time.time()})

    st.markdown(f"<h1 style='text-align: center; color: white; margin-top: 35vh; font-size: 8rem;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    time.sleep(3)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], "render_display")
        st.rerun()
    st.rerun()

else:
    # --- RESTORED SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ TV Settings")
        orient = st.radio("Display Layout", ["Portrait", "Landscape"], index=1)
        live = st.toggle("📺 CONNECT TO CLOUD REMOTE", value=True)
        
        st.divider()
        st.subheader("🎸 Manual Search")
        m_art = st.text_input("Artist Name", "Oasis")
        m_alb = st.text_input("Album Name", "Definitely Maybe")
        
        if st.button("Generate Layout", type="primary"):
            st.session_state.current_poster = create_poster(m_alb, m_art, orient)
            
        if st.button("Unpair Display", type="secondary"):
            clear_connection()
            st.rerun()

    # --- DISPLAY AREA ---
    if live:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        
        @st.fragment(run_every=3)
        def sync_engine():
            t, a = get_current_song_from_cloud(venue_id)
            if t and t != st.session_state.last_track:
                st.session_state.last_track = t
                alb = get_album_from_track(t, a)
                if alb:
                    st.session_state.current_poster = create_poster(alb, a, orient)
                    st.rerun()
        sync_engine()
    else:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
