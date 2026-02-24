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

# Initialize Firebase (Checks Render Cloud vs. Local Mac)
if "FIREBASE_CONFIG" in os.environ:
    # PRODUCTION: Using the Secret Environment Variable on Render
    try:
        service_account_info = json.loads(os.environ.get("FIREBASE_CONFIG"))
        cred = credentials.Certificate(service_account_info)
    except Exception as e:
        st.error(f"Cloud Firebase Init Failed: {e}")
        cred = None
else:
    # DEVELOPMENT: Using your local JSON file on your Mac
    try:
        # Ensure your downloaded file is named exactly 'serviceAccountKey.json'
        cred = credentials.Certificate("serviceAccountKey.json")
    except Exception as e:
        cred = None

if cred and not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Create the Firestore client (for logging and future dashboarding)
db = firestore.client() if firebase_admin._apps else None

# Spotify Credentials
# Looks in Streamlit secrets first, then environment variables (for Render)
SPOTIPY_CLIENT_ID = st.secrets.get("SPOTIPY_CLIENT_ID", os.environ.get("SPOTIPY_CLIENT_ID"))
SPOTIPY_CLIENT_SECRET = st.secrets.get("SPOTIPY_CLIENT_SECRET", os.environ.get("SPOTIPY_CLIENT_SECRET"))

# Legacy RTDB URL (Keeping your current pairing system alive)
FIREBASE_BASE = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"

# ==========================================
# --- 2. PAGE SETUP & KIOSK MODE CSS ---
# ==========================================

st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# Bulletproof Kiosk CSS
hide_st_style = """
    <style>
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { display: none !important; }
    [data-testid="stHeader"] { background-color: transparent !important; z-index: 999999 !important; }
    [data-testid="stHeader"] button {
        background-color: rgba(255, 255, 255, 0.85) !important;
        border-radius: 8px !important;
        margin: 10px !important;
        border: 2px solid black !important;
        visibility: visible !important;
        display: inline-flex !important;
    }
    [data-testid="stHeader"] button svg { fill: #000000 !important; color: #000000 !important; }
    [data-testid="stAppViewContainer"], .stApp, html, body { background-color: #000000 !important; overflow: hidden !important; }
    .block-container { padding: 0px !important; margin: 0px !important; max-width: 100vw !important; }
    [data-testid="stImage"] { width: 100vw !important; height: 100vh !important; display: flex; justify-content: center; align-items: center; z-index: 1 !important; }
    [data-testid="stImage"] img { width: 100vw !important; height: 100vh !important; object-fit: cover !important; }
    </style>
"""
# st.markdown(hide_st_style, unsafe_allow_html=True) 

# Temporary Lifeboat CSS for visibility (so you can see the UI during setup)
st.markdown("""
    <style>
    h1, h2, h3, p, div { color: #000000 !important; font-weight: bold !important; }
    .stApp { background-color: #FFFFFF !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# --- 3. CLOUD LOGGING & HELPERS ---
# ==========================================

def log_event(venue_id, action, status="success", details=""):
    """Sends a timestamped log to Firestore."""
    if db:
        try:
            db.collection("logs").add({
                "venue_id": venue_id,
                "action": action,
                "status": status,
                "details": details,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "device_type": "TV_DISPLAY"
            })
        except Exception:
            pass

def get_saved_venue(): return st.query_params.get("venue_id", None)
def get_saved_display(): return st.query_params.get("display_id", None)

def save_connection(vid, did):
    st.query_params["venue_id"] = vid
    st.query_params["display_id"] = did
    log_event(vid, "DISPLAY_LINKED", details=f"Display ID: {did}")

def clear_connection():
    if "venue_id" in st.query_params: del st.query_params["venue_id"]
    if "display_id" in st.query_params: del st.query_params["display_id"]

# --- INIT SESSION STATE ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None
if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state: st.session_state.is_standby = False

# ==========================================
# --- 4. API & POSTER ENGINE ---
# ==========================================

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

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_data = requests.get(geo_url, timeout=5).json()
        if not geo_data.get('results'): return None
        lat, lon, resolved_name = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude'], geo_data['results'][0]['name']
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        weather_data = requests.get(weather_url, timeout=5).json()
        temp, code = weather_data['current']['temperature_2m'], weather_data['current']['weather_code']
        emoji = "☀️"
        if code in [1, 2, 3]: emoji = "⛅️"
        elif code in [45, 48]: emoji = "🌫️"
        elif code in [61, 63, 65, 66, 67, 80, 81, 82]: emoji = "🌧️"
        return {"temp": temp, "emoji": emoji, "name": resolved_name}
    except Exception: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    html = f"<div style='text-align: center; padding: 150px 20px; color: white; background: #000000; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem; margin: 0;'>{current_time}</h1>"
    if weather:
        html += f"<div style='margin-top: 40px;'><h2 style='font-size: 6rem;'>{weather['emoji']} {weather['temp']}°C</h2>"
        html += f"<p style='font-size: 1.8rem; opacity: 0.8;'>{weather['name']}</p></div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    keywords = [" (deluxe", " [deluxe", " - deluxe", " (remaster", " [remaster"]
    for kw in keywords:
        if kw in title.lower(): title = title[:title.lower().index(kw)]
    return title.strip()

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        if results['tracks']['items']: return results['tracks']['items'][0]['album']['name']
        return None
    except Exception: return None

def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        album = results['albums']['items'][0]
        cover_url = album['images'][0]['url']
        cover_response = requests.get(cover_url, timeout=5)
        cover_img = Image.open(BytesIO(cover_response.content)).convert("RGBA")
        
        def get_safe_font(size):
            # Paths for Linux (Render) and Mac
            font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
            for path in font_paths:
                try: return ImageFont.truetype(path, size)
                except: continue
            return ImageFont.load_default()

        poster_w, poster_h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=40))
        poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        c_size = 1000 if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (100, 100))
        draw.text((100, poster_h - 180), artist_name.upper(), font=get_safe_font(80), fill="white")
        
        return poster
    except Exception: return None

# ==========================================
# --- 5. CORE ROUTING ---
# ==========================================

current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    # --- ONBOARDING ROOM ---
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "display_id": st.session_state.temp_display_id, "timestamp": time.time()})

    st.markdown(f"<h3 style='text-align: center; color: #7C3AED; margin-top: 15vh;'>LINK YOUR DISPLAY</h3>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center; font-size: 8rem;'>{st.session_state.pair_code[:3]} {st.session_state.pair_code[3:]}</h1>", unsafe_allow_html=True)
    
    time.sleep(4) 
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], st.session_state.temp_display_id)
        st.rerun()
    st.rerun()

else:
    # --- MAIN TV APP ---
    st.sidebar.markdown(f"**Venue:** {current_venue_id}")
    display_orientation = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    weather_city = st.sidebar.text_input("Weather City", value="London")
    live_mode = st.sidebar.toggle("Live Cloud Sync", value=True)

    if st.sidebar.button("Unpair Display"):
        clear_connection()
        st.rerun()

    if live_mode:
        if st.session_state.is_standby:
            draw_weather_dashboard(weather_city)
        elif st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)

        @st.fragment(run_every=3)
        def sync_loop():
            track, artist = get_current_song_from_cloud(current_venue_id)
            if track and track != st.session_state.last_track:
                st.session_state.last_track = track
                st.session_state.last_heard_time = time.time()
                album = get_album_from_track(track, artist)
                if album:
                    st.session_state.current_poster = create_poster(album, artist, display_orientation)
                    log_event(current_venue_id, "POSTER_AUTO_GEN", details=f"{track} by {artist}")
                    st.rerun()
        sync_loop()
