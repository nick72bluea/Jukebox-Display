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
    """Universal fetcher for Environment Variables (Render) or Secrets (Streamlit)."""
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except:
        return default

SPOTIPY_CLIENT_ID = get_secret("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = get_secret("SPOTIPY_CLIENT_SECRET")
FIREBASE_BASE = get_secret("FIREBASE_BASE")

# --- 2. FONT SYSTEM (Environment Agnostic) ---
def get_safe_font(size):
    """Finds available fonts on Linux (Render/Streamlit) or macOS/Windows."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Standard Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",    # macOS
        "/Library/Fonts/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf"                      # Windows
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

# --- 3. PAGE SETUP & KIOSK CSS ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

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
    [data-testid="stHeader"] button svg { fill: #000000 !important; }
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
        margin: 0 !important; padding: 0 !important;
        overflow: hidden !important; 
    }
    .block-container { padding: 0px !important; margin: 0px !important; max-width: 100vw !important; }
    [data-testid="stImage"] {
        width: 100vw !important; height: 100vh !important;
        display: flex; justify-content: center; align-items: center;
    }
    [data-testid="stImage"] img { width: 100vw !important; height: 100vh !important; object-fit: cover !important; }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- 4. HELPERS ---
def get_saved_venue(): return st.query_params.get("venue_id", None)
def get_saved_display(): return st.query_params.get("display_id", None)
def save_connection(vid, did):
    st.query_params["venue_id"] = vid
    st.query_params["display_id"] = did

def clear_connection():
    if "venue_id" in st.query_params: del st.query_params["venue_id"]
    if "display_id" in st.query_params: del st.query_params["display_id"]

def get_current_song_from_cloud(venue_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/now_playing.json"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data and 'track' in data: return data['track'], data['artist']
    except: pass
    return None, None

def get_weather(city_name):
    try:
        geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json", timeout=5).json()
        if not geo.get('results'): return None
        res = geo['results'][0]
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={res['latitude']}&longitude={res['longitude']}&current=temperature_2m,weather_code&timezone=auto", timeout=5).json()
        return {"temp": w['current']['temperature_2m'], "name": res['name'], "emoji": "☀️"}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    now = datetime.now()
    html = f"<div style='text-align: center; padding-top: 20vh; color: white; background: black; height: 100vh; font-family: sans-serif;'>"
    html += f"<h1 style='font-size: 10rem; margin: 0;'>{now.strftime('%H:%M')}</h1>"
    html += f"<p style='font-size: 2rem; opacity: 0.6;'>{now.strftime('%A, %B %d')}</p>"
    if weather: html += f"<h2 style='font-size: 5rem;'>{weather['emoji']} {weather['temp']}°C in {weather['name']}</h2>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    for kw in [" (deluxe", " [deluxe", " - deluxe", " (remaster"]:
        if kw in title.lower(): title = title[:title.lower().index(kw)]
    return title.strip()

def clean_track_title(title): return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def draw_wrapped_text(draw, text, font, max_width, x_anchor, start_y, fill, align="right"):
    if not text: return start_y
    lines, words = [], text.split()
    curr = words[0]
    for w in words[1:]:
        if font.getlength(curr + " " + w) <= max_width: curr += " " + w
        else: lines.append(curr); curr = w
    lines.append(curr)
    y = start_y
    for l in lines:
        draw.text((x_anchor - font.getlength(l) if align=="right" else x_anchor, y), l, font=font, fill=fill)
        y += font.getbbox("A")[3] + 10
    return y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

# --- 5. POSTER ENGINE ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        album = results['albums']['items'][0]
        details = sp.album(album['id'])
        cover_img = Image.open(BytesIO(requests.get(album['images'][0]['url']).content)).convert("RGBA")
        
        w, h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(40))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0,0,0,140)))
        draw = ImageDraw.Draw(poster)
        
        pad = 70
        c_size = (w - pad*2) if orientation == "Portrait" else 750
        poster.paste(cover_img.resize((c_size, c_size)), (pad, pad))
        
        f_artist = get_safe_font(70 if orientation == "Portrait" else 90)
        draw_wrapped_text(draw, artist_name.upper(), f_artist, w - pad*2, w - pad, pad + c_size + 20 if orientation=="Portrait" else pad, "white")
        
        return poster
    except: return None

# --- 6. CORE LOGIC ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None
if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state: st.session_state.is_standby = False

venue_id = get_saved_venue()
display_id = get_saved_display()

if not venue_id or not display_id:
    # Pairing Screen
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.tmp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=5))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", json={"status": "waiting", "display_id": st.session_state.tmp_id, "timestamp": time.time()})
    
    st.markdown(f"<h1 style='text-align:center; color:white; margin-top:30vh; font-size:8rem;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    time.sleep(3)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], st.session_state.tmp_id)
        st.rerun()
    st.rerun()

else:
    # Sidebar UI
    st.sidebar.title("⚙️ TV Settings")
    orient = st.sidebar.radio("Display Layout", ["Portrait", "Landscape"], index=1)
    weather_city = st.sidebar.text_input("Weather City", "London")
    
    st.sidebar.markdown("---")
    live_mode = st.sidebar.toggle("📺 **CONNECT TO CLOUD REMOTE**", value=True)
    
    st.sidebar.markdown("### 🎸 Manual Search")
    m_artist = st.sidebar.text_input("Artist Name", "Oasis")
    m_album = st.sidebar.text_input("Album Name", "Definitely Maybe")

    if st.sidebar.button("Generate Layout", type="primary"):
        manual_p = create_poster(m_album, m_artist, orient)
        if manual_p:
            st.session_state.current_poster = manual_p
            st.session_state.is_standby = False
            # We don't rerun immediately so the user sees the image update

    if st.sidebar.button("Unpair Display"):
        clear_connection()
        st.rerun()

    # Cloud Sync Logic
    if live_mode:
        @st.fragment(run_every=5)
        def sync_listener():
            t, a = get_current_song_from_cloud(venue_id)
            if t and t != st.session_state.last_track:
                st.session_state.last_track = t
                new_p = create_poster(t, a, orient)
                if new_p: st.session_state.current_poster = new_p
                st.rerun()
        sync_listener()

    # Display Render
    if st.session_state.current_poster:
        st.image(st.session_state.current_poster, use_container_width=True)
    else:
        st.markdown("<h2 style='color:white;text-align:center;margin-top:40vh;'>Waiting for Music...</h2>", unsafe_allow_html=True)
