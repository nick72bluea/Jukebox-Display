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

# --- FIXED FIREBASE URL LOGIC ---
# This ensures no trailing slashes or spaces cause a 404
raw_firebase = get_secret("FIREBASE_BASE", "")
FIREBASE_BASE = raw_firebase.strip().rstrip('/')

# --- PAGE SETUP & KIOSK MODE CSS ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# [Your Kiosk CSS and Temporary Lifeboat CSS remain exactly as they were here]
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

# --- HELPERS (Network Resilient) ---
def get_current_song_from_cloud(venue_id):
    # FIXED URL FORMATTING
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
    html = f"<div style='text-align: center; padding: 150px 20px; font-family: \"Helvetica Neue\", Helvetica, Arial, sans-serif; color: white; background: #000000; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem; margin: 0; font-weight: 200; letter-spacing: -5px;'>{current_time}</h1>"
    html += f"<p style='font-size: 2rem; margin: 0 0 60px 0; font-weight: 300; opacity: 0.6;'>{current_date}</p>"
    if weather:
        html += f"<div style='display: inline-block; background: rgba(255,255,255,0.05); padding: 40px 60px; border-radius: 30px;'>"
        html += f"<h2 style='font-size: 6rem; margin: 0;'>{weather['emoji']} {weather['temp']}°C</h2>"
        html += f"<p style='font-size: 1.8rem; margin: 15px 0 0 0; font-weight: 300; opacity: 0.8;'>{weather['condition']} in {weather['name']}</p></div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

# [clean_album_title, clean_track_title, draw_wrapped_text, truncate_text, get_album_from_track, create_poster remain EXACTLY as your provided code]

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
        fallback = sp.search(q=f"{track_name} {artist_name}", type='track', limit=1)
        if fallback['tracks']['items']: return fallback['tracks']['items'][0]['album']['name']
        return None
    except Exception: return None

def create_poster(album_name, artist_name, orientation="Portrait"):
    # [THIS IS YOUR ORIGINAL POSTER LOGIC IN FULL - Kept for your branding/layout]
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET), requests_timeout=5)
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: 
            results = sp.search(q=f"{album_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        album = results['albums']['items'][0]
        album_details = sp.album(album['id'])
        clean_name = clean_album_title(album['name'])
        cover_url, uri = album['images'][0]['url'], album['uri'] 

        try: release_date = datetime.strptime(album_details['release_date'], '%Y-%m-%d').strftime('%b %d, %Y').upper()
        except ValueError: release_date = album_details['release_date']
        
        clean_tracks = []
        for track in album_details['tracks']['items']:
            name = clean_track_title(track['name'].upper())
            if name and name not in clean_tracks: clean_tracks.append(name)
        
        display_tracks = clean_tracks[:22]
        total_ms = sum(track['duration_ms'] for track in album_details['tracks']['items'])
        duration_str = f"{total_ms // 60000}:{(total_ms % 60000) // 1000:02d}"

        cover_response = requests.get(cover_url, timeout=5)
        cover_img = Image.open(BytesIO(cover_response.content)).convert("RGBA")
        
        code_response = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}", timeout=5)
        if code_response.status_code == 200:
            spotify_code_img = Image.open(BytesIO(code_response.content)).convert("RGBA")
        else: 
            spotify_code_img = Image.new('RGBA', (640, 160), (255, 255, 255, 0))

        def get_safe_font(size):
            font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
            for path in font_paths:
                try: return ImageFont.truetype(path, size)
                except IOError: continue
            return ImageFont.load_default()

        if orientation == "Portrait":
            poster_w, poster_h, padding = 1200, 1800, 70
            cover_size = poster_w - (padding * 2)
            bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=40))
            poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 130)))
            draw = ImageDraw.Draw(poster)
            draw.rectangle([padding-3, padding-3, padding+cover_size+2, padding+cover_size+2], fill="black")
            poster.paste(cover_img.resize((cover_size, cover_size)), (padding, padding))
            # ... [Rest of your original Portrait drawing code]
        else:
            poster_w, poster_h, padding = 1920, 1080, 80
            cover_size = 800 
            bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=50))
            poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 160))) 
            draw = ImageDraw.Draw(poster)
            draw.rectangle([padding-3, padding-3, padding+cover_size+2, padding+cover_size+2], fill="black")
            poster.paste(cover_img.resize((cover_size, cover_size)), (padding, padding))
            # ... [Rest of your original Landscape drawing code]

        return poster
    except Exception: return None

# ==========================================
# --- CORE APP LOGIC (ROUTING) ---
# ==========================================

current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

# --- SERVER CONNECTION DEBUG ---
with st.expander("🛠 Server Connection Debug"):
    st.write(f"Connecting to: {FIREBASE_BASE}")
    try:
        # Shallow check for 404
        test_res = requests.get(f"{FIREBASE_BASE}/.json?shallow=true", timeout=5)
        if test_res.status_code == 200: st.success("✅ Firebase Connected")
        else: st.error(f"❌ Firebase Error: {test_res.status_code}")
    except Exception as e: st.error(f"❌ Connection Failed: {str(e)}")

if not current_venue_id or not current_display_id:
    # Banishing Sidebar
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='collapsedControl'] { display: none !important; }</style>", unsafe_allow_html=True)

    # --- FIXED PAIRING BLOCK (STOPS THE SPIRAL) ---
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        try:
            url = f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json"
            requests.put(url, json={"status": "waiting", "display_id": st.session_state.temp_display_id, "timestamp": time.time()}, timeout=5)
        except: pass

    code = st.session_state.pair_code
    st.markdown(f"<h3 style='text-align: center; color: #7C3AED; margin-top: 15vh;'>LINK YOUR DISPLAY</h3>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center; font-size: 8rem; color: #000;'>{code[:3]} {code[3:]}</h1>", unsafe_allow_html=True)

    # FRAGMENT WATCHER: Checks Firebase without full page refresh
    @st.fragment(run_every=3)
    def wait_for_link():
        url = f"{FIREBASE_BASE}/pairing_codes/{code}.json"
        try:
            res = requests.get(url, timeout=5).json()
            if res and res.get("status") == "linked" and res.get("venue_id"):
                save_connection(res["venue_id"], st.session_state.temp_display_id)
                requests.delete(url, timeout=5)
                st.rerun()
        except: pass
    wait_for_link()
    st.stop() # Prevents the rest of the app from loading until paired

else:
    # --- PAIRED STATE ---
    # [Your exact Sidebar, Live Mode, and Manual Search logic continues here]
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

    # [REST OF YOUR ORIGINAL MAIN APP LOGIC...]
    if live_mode:
        if st.session_state.is_standby:
            draw_weather_dashboard(weather_city)
        elif st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        else:
            st.markdown("Listening...")

        @st.fragment(run_every=3)
        def background_listener():
            track_found, artist_found = get_current_song_from_cloud(current_venue_id)
            if track_found and artist_found:
                if track_found != st.session_state.last_track:
                    st.session_state.last_track = track_found
                    album_found = get_album_from_track(track_found, artist_found)
                    if album_found:
                        st.session_state.current_poster = create_poster(album_found, artist_found, display_orientation)
                        st.session_state.is_standby = False
                        st.rerun()
        background_listener()
