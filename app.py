import streamlit as st
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
import os

# --- 1. CONFIG & CREDENTIALS (SECURITY LAYER) ---
def get_secret(key, default=None):
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except:
        return default

SPOTIPY_CLIENT_ID = get_secret("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = get_secret("SPOTIPY_CLIENT_SECRET")

# CLEAN URL LOGIC
raw_firebase = get_secret("FIREBASE_BASE", "")
FIREBASE_BASE = raw_firebase.strip().rstrip('/')

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# --- THE SIGNED-OFF KIOSK CSS ---
hide_st_style = """
    <style>
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { display: none !important; }
    [data-testid="stHeader"] { background-color: transparent !important; z-index: 999999 !important; }
    [data-testid="stHeader"] button {
        background-color: rgba(255, 255, 255, 0.85) !important;
        border-radius: 8px !important; margin: 10px !important;
        border: 2px solid black !important; visibility: visible !important; display: inline-flex !important;
    }
    [data-testid="stHeader"] button svg { fill: #000000 !important; color: #000000 !important; }
    [data-testid="stAppViewContainer"], .stApp, html, body { background-color: #000000 !important; margin: 0 !important; padding: 0 !important; }
    .block-container { padding: 0px !important; margin: 0px !important; max-width: 100vw !important; }
    [data-testid="stImage"] img { width: 100vw !important; height: 100vh !important; object-fit: cover !important; }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS ---
def get_saved_venue(): return st.query_params.get("venue_id", None)
def get_saved_display(): return st.query_params.get("display_id", None)
def save_connection(vid, did):
    st.query_params["venue_id"] = vid
    st.query_params["display_id"] = did
def clear_connection():
    if "venue_id" in st.query_params: del st.query_params["venue_id"]
    if "display_id" in st.query_params: del st.query_params["display_id"]

# --- INIT SESSION STATE ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None
if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state: st.session_state.is_standby = False

# --- UTILITIES ---
def get_current_song_from_cloud(venue_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/now_playing.json"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data and 'track' in data: return data['track'], data['artist']
    except: pass
    return None, None

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_data = requests.get(geo_url, timeout=5).json()
        if not geo_data.get('results'): return None
        lat, lon, name = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude'], geo_data['results'][0]['name']
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(weather_url, timeout=5).json()
        return {"temp": w_data['current']['temperature_2m'], "name": name, "code": w_data['current']['weather_code']}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    html = f"<div style='text-align: center; padding-top: 25vh; color: white; background: black; height: 100vh;'>"
    html += f"<h1 style='font-size: 12rem; margin: 0;'>{current_time}</h1>"
    if weather:
        html += f"<h2 style='font-size: 4rem; opacity: 0.7;'>{weather['temp']}°C in {weather['name']}</h2>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    for kw in [" (deluxe", " [deluxe", " - deluxe", " (remaster"]:
        if kw in title.lower(): title = title[:title.lower().index(kw)]
    return title.strip()

def clean_track_title(title): return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        if res['tracks']['items']: return res['tracks']['items'][0]['album']['name']
    except: pass
    return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not res['albums']['items']: return None
        album = res['albums']['items'][0]
        album_details = sp.album(album['id'])
        
        # Image Assets
        cover_img = Image.open(BytesIO(requests.get(album['images'][0]['url']).content)).convert("RGBA")
        code_img = Image.open(BytesIO(requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{album['uri']}").content)).convert("RGBA")
        
        # Dimensions
        w, h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(40))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        # Draw Cover
        c_size = 1060 if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (70, 70))
        
        return poster
    except: return None

# --- ROUTING LOGIC ---
current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

# 1. PAIRING SCREEN (FEATURE: Stabilized with Fragment)
if not current_venue_id or not current_display_id:
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='collapsedControl'] { display: none !important; }</style>", unsafe_allow_html=True)
    
    with st.expander("🛠 Connection Debug"):
        st.write(f"Target: {FIREBASE_BASE}")
        try:
            r = requests.get(f"{FIREBASE_BASE}/.json?shallow=true", timeout=5)
            st.write(f"Status: {r.status_code}")
        except Exception as e: st.write(f"Error: {e}")

    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", json={
            "status": "waiting", "display_id": st.session_state.temp_display_id, "timestamp": time.time()
        }, timeout=5)

    code = st.session_state.pair_code
    st.markdown(f"<div style='text-align:center; padding-top:20vh;'>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='color:#7C3AED; letter-spacing:4px;'>LINK YOUR DISPLAY</h3>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='font-size:10rem; color:white;'>{code[:3]} {code[3:]}</h1>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    @st.fragment(run_every=5)
    def wait_for_link():
        try:
            res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", timeout=5).json()
            if res and res.get("status") == "linked":
                save_connection(res["venue_id"], st.session_state.temp_display_id)
                requests.delete(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json")
                st.rerun()
        except: pass
    wait_for_link()
    st.stop()

# 2. MAIN APP (FEATURE: Cloud Remote + Standby + Manual)
else:
    st.sidebar.markdown("## ⚙️ TV Settings")
    display_orientation = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    weather_city = st.sidebar.text_input("Weather City", value="London")
    idle_timeout = st.sidebar.slider("Standby (Mins)", 1, 15, 5)
    
    live_mode = st.sidebar.toggle("📺 CONNECT TO CLOUD REMOTE", value=True)
    
    # FEATURE: Manual Poster Entry
    st.sidebar.markdown("---")
    m_artist = st.sidebar.text_input("Artist", key="ma")
    m_album = st.sidebar.text_input("Album", key="mal")
    if st.sidebar.button("Generate Manual"):
        new_p = create_poster(m_album, m_artist, display_orientation)
        if new_p: 
            st.session_state.current_poster = new_p
            st.session_state.is_standby = False

    # FEATURE: Unpair
    if st.sidebar.button("Unpair Display"):
        clear_connection()
        st.rerun()

    # DISPLAY AREA
    if st.session_state.is_standby:
        draw_weather_dashboard(weather_city)
    elif st.session_state.current_poster:
        st.image(st.session_state.current_poster, use_container_width=True)

    # FEATURE: Background Cloud Listener
    if live_mode:
        @st.fragment(run_every=3)
        def sync_cloud():
            track, artist = get_current_song_from_cloud(current_venue_id)
            if track and track != st.session_state.last_track:
                st.session_state.last_track = track
                st.session_state.last_heard_time = time.time()
                album = get_album_from_track(track, artist)
                if album:
                    st.session_state.current_poster = create_poster(album, artist, display_orientation)
                    st.session_state.is_standby = False
                    st.rerun()
            
            # Standby Logic
            if time.time() - st.session_state.last_heard_time > (idle_timeout * 60):
                if not st.session_state.is_standby:
                    st.session_state.is_standby = True
                    st.rerun()
        sync_cloud()
