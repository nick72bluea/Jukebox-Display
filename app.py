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
import os  # FIXED: Critical import for Render/Environment Variables

# --- 1. CONFIG & CREDENTIALS (SECURITY LAYER) ---
def get_secret(key, default=None):
    """Universal fetcher for Environment Variables (Render) or Secrets (Streamlit)."""
    if key in os.environ:
        return os.environ.get(key)
    try:
        if key in st.secrets:
            return st.secrets[key]
    except:
        return default

SPOTIPY_CLIENT_ID = get_secret("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = get_secret("SPOTIPY_CLIENT_SECRET")
FIREBASE_BASE = get_secret("FIREBASE_BASE")

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# --- FIXED KIOSK CSS (Supports Portrait Scrolling) ---
hide_st_style = """
    <style>
    /* Hide Header and Footer */
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { 
        display: none !important; 
    }
    
    /* Make background black */
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
        margin: 0 !important;
        padding: 0 !important;
        overflow-y: auto !important; /* FIXED: Allows scrolling in Portrait */
    }

    /* Remove Streamlit padding */
    .block-container {
        padding: 0px !important;
        margin: 0px !important;
        max-width: 100vw !important;
    }

    /* Image Scaling for Portrait visibility */
    [data-testid="stImage"] {
        width: 100vw !important;
        margin: 0 !important;
        display: flex; 
        justify-content: center;
    }

    [data-testid="stImage"] img {
        width: 100vw !important;
        height: auto !important; /* FIXED: Maintains aspect ratio so it doesn't get cut off */
        object-fit: contain !important; 
    }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS ---
def get_saved_venue():
    return st.query_params.get("venue_id")

def get_saved_display():
    return st.query_params.get("display_id")

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
    except: pass
    return None, None

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_data = requests.get(geo_url, timeout=5).json()
        if not geo_data.get('results'): return None
        res = geo_data['results'][0]
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={res['latitude']}&longitude={res['longitude']}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(weather_url, timeout=5).json()
        code = w_data['current']['weather_code']
        emoji = "☀️" if code == 0 else "🌧️" if code > 50 else "⛅️"
        return {"temp": w_data['current']['temperature_2m'], "emoji": emoji, "condition": "Updated", "name": res['name']}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    now = datetime.now()
    html = f"""
    <div style='text-align: center; padding: 100px 20px; color: white; background: black; height: 100vh; font-family: sans-serif;'>
        <h1 style='font-size: 8rem; margin: 0;'>{now.strftime("%H:%M")}</h1>
        <p style='font-size: 2rem; opacity: 0.6;'>{now.strftime("%A, %B %d")}</p>
        {f"<h2 style='font-size: 4rem;'>{weather['emoji']} {weather['temp']}°C</h2>" if weather else ""}
    </div>"""
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    return re.split(r' \(| \[| - ', title)[0].strip()

def clean_track_title(title):
    return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def draw_wrapped_text(draw, text, font, max_width, x_anchor, start_y, fill, align="right"):
    lines, words = [], text.split()
    if not words: return start_y
    line = words[0]
    for word in words[1:]:
        if font.getlength(line + " " + word) <= max_width: line += " " + word
        else: lines.append(line); line = word
    lines.append(line)
    y = start_y
    for l in lines:
        x = x_anchor - font.getlength(l) if align == "right" else x_anchor
        draw.text((x, y), l, font=font, fill=fill)
        y += font.getbbox("A")[3] + 10
    return y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width: text = text[:-1]
    return text.strip() + "..."

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return results['tracks']['items'][0]['album']['name'] if results['tracks']['items'] else None
    except: return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not res['albums']['items']: return None
        album = res['albums']['items'][0]
        album_details = sp.album(album['id'])
        
        # Poster Setup
        w, h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        img = Image.new("RGBA", (w, h), (0,0,0,255))
        
        # Get Cover
        cover = Image.open(BytesIO(requests.get(album['images'][0]['url']).content)).convert("RGBA")
        bg = cover.resize((w, h)).filter(ImageFilter.GaussianBlur(40))
        img = Image.alpha_composite(bg, Image.new('RGBA', (w, h), (0, 0, 0, 140)))
        draw = ImageDraw.Draw(img)
        
        # Paste Cover
        c_size = 1060 if orientation == "Portrait" else 800
        img.paste(cover.resize((c_size, c_size)), (70, 70))
        
        return img
    except: return None

# --- APP LOGIC ---
current_vid = get_saved_venue()
current_did = get_saved_display()

if not current_vid or not current_did:
    st.markdown("<style>[data-testid='stSidebar'] { display: none !important; }</style>", unsafe_allow_html=True)
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=8))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()})
    
    st.markdown(f"<h1 style='text-align: center; color: white; margin-top: 20vh; font-size: 8rem;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    time.sleep(3)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], st.session_state.temp_id)
        st.rerun()
    st.rerun()
else:
    # Sidebar
    st.sidebar.title("Settings")
    orient = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=0)
    city = st.sidebar.text_input("City", "London")
    if st.sidebar.button("Unpair"):
        clear_connection()
        st.rerun()

    # Display
    if st.session_state.current_poster:
        st.image(st.session_state.current_poster, use_container_width=True)
    
    @st.fragment(run_every=5)
    def sync():
        t, a = get_current_song_from_cloud(current_vid)
        if t and t != st.session_state.last_track:
            st.session_state.last_track = t
            alb = get_album_from_track(t, a)
            if alb:
                post = create_poster(alb, a, orient)
                if post:
                    st.session_state.current_poster = post
                    st.rerun()
    sync()
