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
# Added os.environ check so Render can provide these via the Dashboard
SPOTIPY_CLIENT_ID = os.environ.get('SPOTIPY_CLIENT_ID', '02c1d6fcc3a149138d815e4036c0c36e')
SPOTIPY_CLIENT_SECRET = os.environ.get('SPOTIPY_CLIENT_SECRET', '7e96739194134d83ba322af5cefd9af4')
FIREBASE_BASE = os.environ.get('FIREBASE_BASE', "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app")

# --- PAGE SETUP & KIOSK MODE CSS ---
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
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
        margin: 0 !important; padding: 0 !important; overflow: hidden !important; 
    }
    .block-container { padding: 0px !important; margin: 0px !important; max-width: 100vw !important; }
    [data-testid="stImage"] { 
        width: 100vw !important; height: 100vh !important; 
        display: flex; justify-content: center; align-items: center; z-index: 1 !important; 
    }
    [data-testid="stImage"] img { width: 100vw !important; height: 100vh !important; object-fit: cover !important; }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# Temporary Lifeboat CSS for visibility
st.markdown("""
    <style>
    h1, h2, h3, p, div { color: #000000 !important; font-weight: bold !important; }
    .stApp { background-color: #FFFFFF !important; }
    </style>
""", unsafe_allow_html=True)

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

# --- HELPERS ---
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
        emoji, condition = "☀️", "Clear"
        if code in [1, 2, 3]: emoji, condition = "⛅️", "Partly Cloudy"
        elif code in [45, 48]: emoji, condition = "🌫️", "Fog"
        elif code in [61, 63, 65, 66, 67]: emoji, condition = "🌧️", "Rain"
        return {"temp": temp, "emoji": emoji, "condition": condition, "name": resolved_name}
    except Exception: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    current_date = datetime.now().strftime("%A, %B %d")
    html = f"<div style='text-align: center; padding: 150px 20px; color: white; background: #000000; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem; margin: 0;'>{current_time}</h1>"
    html += f"<p style='font-size: 2rem; opacity: 0.6;'>{current_date}</p>"
    if weather:
        html += f"<h2 style='font-size: 6rem;'>{weather['emoji']} {weather['temp']}°C</h2>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    keywords = [" (deluxe", " [deluxe", " - deluxe", " (remaster", " [remaster"]
    lower_title = title.lower()
    for kw in keywords:
        if kw in lower_title: title = title[:lower_title.index(kw)]
    return title.strip()

def clean_track_title(title):
    return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def draw_wrapped_text(draw, text, font, max_width, x_anchor, start_y, fill, align="right"):
    if not text: return start_y
    lines, words = [], text.split()
    current_line = words[0]
    for word in words[1:]:
        if font.getlength(current_line + " " + word) <= max_width: current_line += " " + word
        else: lines.append(current_line); current_line = word
    lines.append(current_line)
    curr_y = start_y
    for line in lines:
        x = x_anchor - font.getlength(line) if align == "right" else x_anchor
        draw.text((x, curr_y), line, font=font, fill=fill)
        curr_y += font.getbbox("A")[3] + 10
    return curr_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    return text[:15].strip() + "..."

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return results['tracks']['items'][0]['album']['name'] if results['tracks']['items'] else None
    except Exception: return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        album = results['albums']['items'][0]
        album_details = sp.album(album['id'])
        cover_url = album['images'][0]['url']
        
        cover_response = requests.get(cover_url, timeout=5)
        cover_img = Image.open(BytesIO(cover_response.content)).convert("RGBA")
        
        def get_safe_font(size):
            # Added Render-specific Linux font path
            paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
            for p in paths:
                try: return ImageFont.truetype(p, size)
                except: continue
            return ImageFont.load_default()

        # Your original Portrait/Landscape logic here
        if orientation == "Portrait":
            poster_w, poster_h, padding = 1200, 1800, 70
            cover_size = poster_w - (padding * 2)
            bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=40))
            poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 130)))
            draw = ImageDraw.Draw(poster)
            poster.paste(cover_img.resize((cover_size, cover_size)), (padding, padding))
            draw.text((padding, 1600), artist_name.upper(), font=get_safe_font(80), fill="white")
        else:
            poster_w, poster_h, padding = 1920, 1080, 80
            cover_size = 800
            bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=50))
            poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 160)))
            draw = ImageDraw.Draw(poster)
            poster.paste(cover_img.resize((cover_size, cover_size)), (padding, padding))
            draw.text((950, 200), artist_name.upper(), font=get_safe_font(100), fill="white")

        return poster
    except Exception: return None

# --- CORE APP LOGIC ---
current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    st.markdown("<style>[data-testid='stSidebar'] { display: none !important; }</style>", unsafe_allow_html=True)
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "display_id": st.session_state.temp_display_id, "timestamp": time.time()})

    st.markdown(f"<h1 style='text-align: center; color: white; margin-top: 20vh;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    time.sleep(2)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], st.session_state.temp_display_id)
        st.rerun()
    st.rerun()

else:
    st.sidebar.markdown("## ⚙️ TV Settings")
    display_orientation = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    live_mode = st.sidebar.toggle("📺 **CONNECT TO CLOUD REMOTE**", value=True)
    
    # Manual Search Section
    st.sidebar.markdown("### 🎸 Manual Search")
    m_artist = st.sidebar.text_input("Artist", value="Oasis")
    m_album = st.sidebar.text_input("Album", value="Definitely Maybe")
    if st.sidebar.button("Generate Layout"):
        st.session_state.current_poster = create_poster(m_album, m_artist, display_orientation)
        st.session_state.is_standby = False

    if st.sidebar.button("Unpair Display"):
        clear_connection()
        st.rerun()

    if live_mode:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        
        @st.fragment(run_every=3)
        def sync_loop():
            track, artist = get_current_song_from_cloud(current_venue_id)
            if track and track != st.session_state.last_track:
                st.session_state.last_track = track
                album = get_album_from_track(track, artist)
                if album:
                    st.session_state.current_poster = create_poster(album, artist, display_orientation)
                    st.rerun()
        sync_loop()
    else:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
