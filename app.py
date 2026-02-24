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
import os  # FIXED: Required for Render environment variables

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

# --- PAGE SETUP & KIOSK MODE CSS ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# Bulletproof Kiosk CSS (Updated for Portrait Visibility)
hide_st_style = """
    <style>
    /* 1. Hide only the top right tools */
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { 
        display: none !important; 
    }
    
    /* 2. Header setup */
    [data-testid="stHeader"] {
        background-color: transparent !important;
        background: transparent !important;
        z-index: 999999 !important;
    }
    
    /* 3. Sidebar toggle button visibility */
    [data-testid="stHeader"] button {
        background-color: rgba(255, 255, 255, 0.85) !important;
        border-radius: 8px !important;
        margin: 10px !important;
        border: 2px solid black !important;
        opacity: 1 !important;
        visibility: visible !important;
        display: inline-flex !important;
    }
    
    [data-testid="stHeader"] button svg {
        fill: #000000 !important;
        color: #000000 !important;
    }
    
    /* 4. Background and Scrolling Fix */
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
        margin: 0 !important;
        padding: 0 !important;
        overflow-y: auto !important; /* FIXED: Allows scrolling in Portrait mode */
    }
    
    /* 5. Nuke Streamlit padding */
    .block-container {
        padding: 0px !important;
        margin: 0px !important;
        max-width: 100vw !important;
    }
    
    /* 6. Edge-to-Edge Image Fix */
    [data-testid="stImage"] {
        width: 100vw !important;
        margin: 0 !important;
        padding: 0 !important;
        display: flex; 
        justify-content: center; 
        align-items: center;
    }
    
    [data-testid="stImage"] img {
        width: 100vw !important;
        height: auto !important; /* FIXED: Prevents vertical cropping in Portrait */
        object-fit: contain !important; 
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
    if "venue_id" in st.query_params: del st.query_params["venue_id"]
    if "display_id" in st.query_params: del st.query_params["display_id"]

# --- INIT SESSION STATE ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None
if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state: st.session_state.is_standby = False

# --- HELPERS (Network Resilient) ---
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
        elif code in [51, 53, 55, 56, 57]: emoji, condition = "🌧️", "Drizzle"
        elif code in [61, 63, 65, 66, 67]: emoji, condition = "🌧️", "Rain"
        elif code in [71, 73, 75, 77]: emoji, condition = "❄️", "Snow"
        elif code in [80, 81, 82]: emoji, condition = "🌦️", "Showers"
        elif code in [95, 96, 99]: emoji, condition = "⛈️", "Thunderstorm"
        return {"temp": temp, "emoji": emoji, "condition": condition, "name": resolved_name}
    except Exception: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    current_date = datetime.now().strftime("%A, %B %d")
    html = f"<div style='text-align: center; padding: 150px 20px; font-family: sans-serif; color: white; background: #000000; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem; margin: 0; font-weight: 200;'>{current_time}</h1>"
    html += f"<p style='font-size: 2rem; margin: 0 0 60px 0; opacity: 0.6;'>{current_date}</p>"
    if weather:
        html += f"<div style='display: inline-block; background: rgba(255,255,255,0.05); padding: 40px 60px; border-radius: 30px;'>"
        html += f"<h2 style='font-size: 6rem; margin: 0;'>{weather['emoji']} {weather['temp']}°C</h2>"
        html += f"<p style='font-size: 1.8rem; margin: 15px 0 0 0; opacity: 0.8;'>{weather['condition']} in {weather['name']}</p></div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    keywords = [" (deluxe", " [deluxe", " - deluxe", " (remaster", " [remaster", " - remaster", " (expanded", " [expanded", " - expanded", " (original", " [original", " - original"]
    lower_title = title.lower()
    for kw in keywords:
        if kw in lower_title:
            title = title[:lower_title.index(kw)]
            lower_title = title.lower() 
    return title.strip() if title.strip() else title

def clean_track_title(title):
    return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def draw_wrapped_text(draw, text, font, max_width, x_anchor, start_y, fill, align="right"):
    if not text or not text.strip(): return start_y
    lines, words = [], text.split()
    if not words: return start_y
    current_line = words[0]
    for word in words[1:]:
        if font.getlength(current_line + " " + word) <= max_width: current_line += " " + word
        else: lines.append(current_line); current_line = word
    lines.append(current_line)
    current_y, line_height = start_y, font.getbbox("A")[3] + 10 
    for line in lines:
        if align == "right": draw.text((x_anchor - font.getlength(line), current_y), line, font=font, fill=fill)
        else: draw.text((x_anchor, current_y), line, font=font, fill=fill)
        current_y += line_height
    return current_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET), requests_timeout=5)
        results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        if results['tracks']['items']: return results['tracks']['items'][0]['album']['name']
        return None
    except Exception: return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET), requests_timeout=5)
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        album = results['albums']['items'][0]
        album_details = sp.album(album['id'])
        clean_name = clean_album_title(album['name'])
        cover_url, uri = album['images'][0]['url'], album['uri'] 

        try: release_date = datetime.strptime(album_details['release_date'], '%Y-%m-%d').strftime('%b %d, %Y').upper()
        except ValueError: release_date = album_details['release_date']
        
        display_tracks = [clean_track_title(t['name'].upper()) for t in album_details['tracks']['items']][:22]
        total_ms = sum(track['duration_ms'] for track in album_details['tracks']['items'])
        duration_str = f"{total_ms // 60000}:{(total_ms % 60000) // 1000:02d}"

        cover_response = requests.get(cover_url, timeout=5)
        cover_img = Image.open(BytesIO(cover_response.content)).convert("RGBA")
        
        code_response = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}", timeout=5)
        spotify_code_img = Image.open(BytesIO(code_response.content)).convert("RGBA") if code_response.status_code == 200 else Image.new('RGBA', (640, 160), (255, 255, 255, 0))

        def get_safe_font(size):
            font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]
            for path in font_paths:
                try: return ImageFont.truetype(path, size)
                except: continue
            return ImageFont.load_default()

        if orientation == "Portrait":
            poster_w, poster_h, padding = 1200, 1800, 70
            cover_size = poster_w - (padding * 2)
            bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=40))
            poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 130)))
            draw = ImageDraw.Draw(poster)
            draw.rectangle([padding-3, padding-3, padding+cover_size+2, padding+cover_size+2], fill="black")
            poster.paste(cover_img.resize((cover_size, cover_size)), (padding, padding))
            
            code_y = padding + cover_size + 45      
            code_w = int((90 / spotify_code_img.height) * spotify_code_img.width)
            poster.paste(spotify_code_img.resize((code_w, 90)), (padding, code_y), spotify_code_img.resize((code_w, 90)))
            
            # Text drawing logic remains same
            draw_wrapped_text(draw, artist_name.upper(), get_safe_font(60), poster_w - padding, poster_w - padding, code_y - 12, "white", "right")
            
        else:
            poster_w, poster_h, padding = 1920, 1080, 80
            cover_size = 800 
            bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=50))
            poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 160))) 
            draw = ImageDraw.Draw(poster)
            poster.paste(cover_img.resize((cover_size, cover_size)), (padding, padding))

        return poster
    except Exception: return None

# --- CORE APP LOGIC (ROUTING) ---
current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    st.markdown("<style>[data-testid='stSidebar'] { display: none !important; } [data-testid='collapsedControl'] { display: none !important; }</style>", unsafe_allow_html=True)
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        try: requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", json={"status": "waiting", "display_id": st.session_state.temp_display_id, "timestamp": time.time()}, timeout=5)
        except: pass

    st.markdown(f"<h1 style='text-align: center; font-size: 8rem; color: white; margin-top: 15vh;'>{st.session_state.pair_code[:3]} {st.session_state.pair_code[3:]}</h1>", unsafe_allow_html=True)
    time.sleep(2)
    try:
        res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", timeout=5).json()
        if res and res.get("status") == "linked" and res.get("venue_id"):
            save_connection(res["venue_id"], st.session_state.temp_display_id)
            st.rerun() 
    except: pass
    st.rerun() 

else:
    # --- PAIRED STATE (MAIN APP) ---
    if 'live_mode_toggle' not in st.session_state: st.session_state.live_mode_toggle = False
    if 'prev_live_mode' not in st.session_state: st.session_state.prev_live_mode = False

    st.sidebar.markdown("## ⚙️ TV Settings")
    display_orientation = st.sidebar.radio("Display Layout", ["Portrait", "Landscape"], index=1, key="display_layout")
    weather_city = st.sidebar.text_input("Local City for Weather", value="London")
    idle_timeout_mins = st.sidebar.slider("Minutes until Standby Screen", min_value=1, max_value=15, value=5)
    
    live_mode = st.sidebar.toggle("📺 **CONNECT TO CLOUD REMOTE**", key="live_mode_toggle")
    if live_mode != st.session_state.prev_live_mode:
        st.session_state.prev_live_mode = live_mode
        st.rerun() 

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎸 Manual Search")
    st.sidebar.text_input("Artist Name", placeholder="e.g., Oasis", value="Oasis", key="manual_artist")
    st.sidebar.text_input("Album Name", placeholder="e.g., Definitely Maybe", value="Definitely Maybe", key="manual_album")

    def generate_manual_poster():
        result_img = create_poster(st.session_state.manual_album, st.session_state.manual_artist, st.session_state.display_layout)
        if result_img:
            st.session_state.current_poster = result_img
            st.session_state.is_standby = False
            st.session_state.live_mode_toggle = False
            st.session_state.prev_live_mode = False
    
    st.sidebar.button("Generate Layout", type="primary", on_click=generate_manual_poster)

    if live_mode:
        if st.session_state.is_standby: draw_weather_dashboard(weather_city)
        elif st.session_state.current_poster: st.image(st.session_state.current_poster, use_container_width=True)
        
        @st.fragment(run_every=3)
        def background_listener():
            track_found, artist_found = get_current_song_from_cloud(current_venue_id)
            if track_found and (track_found != st.session_state.last_track or display_orientation != getattr(st.session_state, 'last_orientation', None)):
                st.session_state.last_track = track_found
                st.session_state.last_orientation = display_orientation
                st.session_state.is_standby = False
                album_found = get_album_from_track(track_found, artist_found)
                if album_found:
                    new_poster = create_poster(album_found, artist_found, display_orientation)
                    if new_poster: st.session_state.current_poster = new_poster
                st.rerun()
        background_listener()
    else:
        if st.session_state.current_poster: st.image(st.session_state.current_poster, use_container_width=True)
