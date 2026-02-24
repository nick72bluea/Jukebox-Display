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

# --- 1. CONFIG & CREDENTIALS ---
# These are now pulled from Streamlit Secrets (Render Environment Variables)
SPOTIPY_CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
SPOTIPY_CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]
FIREBASE_BASE = st.secrets["FIREBASE_BASE"]

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# --- KIOSK MODE CSS (Full Screen, Black Background, Hidden UI) ---
hide_st_style = """
    <style>
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { 
        display: none !important; 
    }
    [data-testid="stHeader"] {
        background-color: transparent !important;
        z-index: 999999 !important;
    }
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important; 
    }
    .block-container {
        padding: 0px !important;
        margin: 0px !important;
        max-width: 100vw !important;
    }
    [data-testid="stImage"] img {
        width: 100vw !important;
        height: 100vh !important;
        object-fit: cover !important; 
    }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS ---
def get_saved_venue():
    return st.query_params.get("venue_id", None)

def get_saved_display():
    return st.query_params.get("display_id", None)

def save_connection(vid, did):
    st.query_params["venue_id"] = vid
    st.query_params["display_id"] = did

def clear_connection():
    st.query_params.clear()

# --- INIT SESSION STATE ---
for key, val in {
    'last_track': None, 
    'current_poster': None, 
    'last_heard_time': time.time(), 
    'is_standby': False,
    'last_orientation': "Landscape"
}.items():
    if key not in st.session_state: st.session_state[key] = val

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
        lat, lon, res_name = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude'], geo_data['results'][0]['name']
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(w_url, timeout=5).json()
        temp, code = w_data['current']['temperature_2m'], w_data['current']['weather_code']
        return {"temp": temp, "emoji": "☀️", "condition": "Clear", "name": res_name}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    now = datetime.now()
    html = f"""
    <div style='text-align: center; padding-top: 20vh; font-family: sans-serif; color: white; background: black; height: 100vh;'>
        <h1 style='font-size: 12rem; margin: 0;'>{now.strftime("%H:%M")}</h1>
        <p style='font-size: 3rem; opacity: 0.5;'>{now.strftime("%A, %B %d")}</p>
        {f"<h2 style='font-size: 5rem;'>{weather['emoji']} {weather['temp']}°C</h2>" if weather else ""}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    return re.split(r' \(deluxe| \[deluxe| - deluxe| \(remaster| \[remaster| - remaster', title, flags=re.I)[0].strip()

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
    curr_y = start_y
    for l in lines:
        x = x_anchor - font.getlength(l) if align == "right" else x_anchor
        draw.text((x, curr_y), l, font=font, fill=fill)
        curr_y += font.getbbox("A")[3] + 10
    return curr_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width: text = text[:-1]
    return text + "..."

def get_album_from_track(track, artist):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"track:{track} artist:{artist}", type='track', limit=1)
        return res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else None
    except: return None

def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not res['albums']['items']: return None
        
        alb = res['albums']['items'][0]
        full_alb = sp.album(alb['id'])
        img_url = alb['images'][0]['url']
        
        cover = Image.open(BytesIO(requests.get(img_url).content)).convert("RGBA")
        
        # Simple Font Fallback for Render (Linux)
        def get_safe_font(size):
            for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
                if os.path.exists(p): return ImageFont.truetype(p, size)
            return ImageFont.load_default()

        # Canvas Setup
        w, h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        poster = cover.resize((w, h)).filter(ImageFilter.GaussianBlur(40))
        poster = Image.alpha_composite(poster, Image.new('RGBA', (w, h), (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        # Basic Poster Layout (simplified for brevity)
        pad = 80
        c_size = 700
        poster.paste(cover.resize((c_size, c_size)), (pad, pad))
        draw.text((pad, pad + c_size + 20), artist_name.upper(), font=get_safe_font(60), fill="white")
        draw.text((pad, pad + c_size + 90), album_name.upper(), font=get_safe_font(40), fill="#ccc")
        
        return poster
    except Exception as e:
        return None

# --- CORE LOGIC ---
venue_id = get_saved_venue()
display_id = get_saved_display()

if not venue_id or not display_id:
    # --- PAIRING SCREEN ---
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=5))
        try:
            requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                         json={"status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()})
        except: pass

    st.markdown(f"<div style='text-align:center; margin-top:20vh;'><h2 style='color:#7C3AED;'>LINK TV</h2><h1 style='font-size:10rem; color:white;'>{st.session_state.pair_code}</h1></div>", unsafe_allow_html=True)
    
    time.sleep(3)
    try:
        res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
        if res and res.get("status") == "linked":
            save_connection(res["venue_id"], st.session_state.temp_id)
            st.rerun()
    except: pass
    st.rerun()

else:
    # --- ACTIVE TV MODE ---
    st.sidebar.title("Settings")
    orient = st.sidebar.selectbox("Orientation", ["Portrait", "Landscape"], index=1)
    city = st.sidebar.text_input("Weather City", "London")
    
    if st.session_state.is_standby:
        draw_weather_dashboard(city)
    elif st.session_state.current_poster:
        st.image(st.session_state.current_poster)
    
    @st.fragment(run_every=4)
    def sync():
        t, a = get_current_song_from_cloud(venue_id)
        if t and t != st.session_state.last_track:
            st.session_state.last_track = t
            alb = get_album_from_track(t, a) or t
            poster = create_poster(alb, a, orient)
            if poster:
                st.session_state.current_poster = poster
                st.rerun()
    sync()
