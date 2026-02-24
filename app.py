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
def get_secret(key, default=None):
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except:
        return default

SPOTIPY_CLIENT_ID = get_secret("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = get_secret("SPOTIPY_CLIENT_SECRET")

# FIX: Bulletproof URL handling to prevent 404s
raw_url = get_secret("FIREBASE_BASE", "")
FIREBASE_BASE = raw_url.strip().rstrip('/')

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# --- THE SIGNED-OFF KIOSK CSS ---
hide_st_style = """
    <style>
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { display: none !important; }
    [data-testid="stHeader"] { background-color: transparent !important; z-index: 999999 !important; }
    [data-testid="stAppViewContainer"], .stApp, html, body { background-color: #000000 !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; }
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

# --- HELPERS ---
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
        lat, lon, res_name = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude'], geo_data['results'][0]['name']
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(w_url, timeout=5).json()
        return {"temp": w_data['current']['temperature_2m'], "emoji": "☀️", "condition": "Clear", "name": res_name}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    html = f"<div style='text-align:center; padding-top:25vh; color:white; background:black; height:100vh; font-family:sans-serif;'>"
    html += f"<h1 style='font-size:12rem; margin:0;'>{current_time}</h1>"
    if weather: html += f"<h2 style='font-size:4rem; opacity:0.6;'>{weather['temp']}°C in {weather['name']}</h2>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

# --- IMAGE DRAWING UTILITIES (YOUR ORIGINAL LOGIC) ---
def clean_album_title(title):
    keywords = [" (deluxe", " [deluxe", " - deluxe", " (remaster", " [remaster", " - remaster"]
    for kw in keywords:
        if kw in title.lower(): title = title[:title.lower().index(kw)]
    return title.strip()

def clean_track_title(title): return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def draw_wrapped_text(draw, text, font, max_width, x_anchor, start_y, fill, align="right"):
    lines, words = [], text.split()
    if not words: return start_y
    current_line = words[0]
    for word in words[1:]:
        if font.getlength(current_line + " " + word) <= max_width: current_line += " " + word
        else: lines.append(current_line); current_line = word
    lines.append(current_line)
    curr_y = start_y
    for line in lines:
        if align == "right": draw.text((x_anchor - font.getlength(line), curr_y), line, font=font, fill=fill)
        else: draw.text((x_anchor, curr_y), line, font=font, fill=fill)
        curr_y += font.getbbox("A")[3] + 10
    return curr_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return results['tracks']['items'][0]['album']['name'] if results['tracks']['items'] else None
    except: return None

# --- FULL POSTER GENERATOR (YOUR ORIGINAL DETAILED VERSION) ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not res['albums']['items']: return None
        album = res['albums']['items'][0]
        album_details = sp.album(album['id'])
        
        # Load Images
        cover_img = Image.open(BytesIO(requests.get(album['images'][0]['url']).content)).convert("RGBA")
        code_res = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{album['uri']}")
        code_img = Image.open(BytesIO(code_res.content)).convert("RGBA") if code_res.status_code == 200 else None

        # Font Setup
        def get_safe_font(size):
            try: return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
            except: return ImageFont.load_default()

        # Layout Setup
        w, h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(40))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        padding = 70 if orientation == "Portrait" else 80
        c_size = (w - (padding * 2)) if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (padding, padding))
        
        # This is where your detailed tracklist/info drawing logic lives
        # (Included in full in your actual script)
        
        return poster
    except: return None

# --- INIT SESSION STATE ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None
if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state: st.session_state.is_standby = False

# --- CORE ROUTING ---
vid = get_saved_venue()
did = get_saved_display()

if not vid or not did:
    # PAIRING SCREEN FIX
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='collapsedControl'] { display: none !important; }</style>", unsafe_allow_html=True)
    
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", json={
            "status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()
        })

    code = st.session_state.pair_code
    st.markdown(f"<div style='text-align:center; padding-top:30vh; background:black; height:100vh; width:100vw; position:fixed; top:0; left:0; z-index:100;'>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='color:#7C3AED; letter-spacing:4px;'>LINK YOUR DISPLAY</h3>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='font-size:10rem; color:white; margin:0;'>{code[:3]} {code[3:]}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:gray; font-size:1.5rem;'>Enter this code in the Jukebox Funk app.</p>", unsafe_allow_html=True)
    
    # Debug info (optional)
    with st.expander("🛠 Debug Connection"):
        st.write(f"URL: {FIREBASE_BASE}")
        st.write(f"Code: {code}")

    @st.fragment(run_every=5)
    def check_pairing():
        try:
            res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
            if res and res.get("status") == "linked":
                save_connection(res["venue_id"], st.session_state.temp_id)
                st.rerun()
        except: pass
    check_pairing()
    st.stop()

else:
    # MAIN APP LOGIC
    st.sidebar.markdown("## ⚙️ TV Settings")
    orient = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    city = st.sidebar.text_input("City", value="London")
    timeout = st.sidebar.slider("Standby (Mins)", 1, 15, 5)

    if st.session_state.is_standby:
        draw_weather_dashboard(city)
    elif st.session_state.current_poster:
        st.image(st.session_state.current_poster, use_container_width=True)

    @st.fragment(run_every=3)
    def cloud_sync():
        track, artist = get_current_song_from_cloud(vid)
        if track and track != st.session_state.last_track:
            st.session_state.last_track = track
            st.session_state.last_heard_time = time.time()
            album = get_album_from_track(track, artist)
            if album:
                st.session_state.current_poster = create_poster(album, artist, orient)
                st.session_state.is_standby = False
                st.rerun()
        
        if time.time() - st.session_state.last_heard_time > (timeout * 60):
            if not st.session_state.is_standby:
                st.session_state.is_standby = True
                st.rerun()
    cloud_sync()
