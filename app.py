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
import json
import firebase_admin
from firebase_admin import credentials, db

# --- 1. CONFIG & CREDENTIALS ---
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

# --- FIREBASE INITIALIZATION ---
service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")

if service_account_info:
    try:
        if not firebase_admin._apps:
            if isinstance(service_account_info, str):
                cert_dict = json.loads(service_account_info)
            else:
                cert_dict = service_account_info
                
            cred = credentials.Certificate(cert_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app'
            })
    except Exception as e:
        st.error(f"Firebase Init Error: {e}")
else:
    st.error("❌ FIREBASE_SERVICE_ACCOUNT missing")

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# Kiosk CSS
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
    .block-container { padding: 0px !important; max-width: 100vw !important; }
    [data-testid="stImage"] img { width: 100vw !important; height: 100vh !important; object-fit: cover !important; }
    </style>
"""

# Lifeboat CSS (Remove this for pure black background production)
st.markdown("""
    <style>
    h1, h2, h3, p, div { color: #000000 !important; font-weight: bold !important; }
    .stApp { background-color: #FFFFFF !important; }
    </style>
""", unsafe_allow_html=True)

# --- PERSISTENCE HELPERS ---
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
if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state: st.session_state.is_standby = False
if 'last_orientation' not in st.session_state: st.session_state.last_orientation = "Landscape"

# --- FIREBASE & API HELPERS ---
def get_current_song_from_cloud(venue_id):
    try:
        ref = db.reference(f"venues/{venue_id}/now_playing")
        data = ref.get()
        if data and 'track' in data and 'artist' in data:
            return data['track'], data['artist']
    except: pass
    return None, None

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_data = requests.get(geo_url, timeout=5).json()
        if not geo_data.get('results'): return None
        lat, lon = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude']
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        wd = requests.get(weather_url, timeout=5).json()
        temp, code = wd['current']['temperature_2m'], wd['current']['weather_code']
        emoji = "☀️" if code == 0 else "⛅️" if code < 4 else "🌧️"
        return {"temp": temp, "emoji": emoji, "name": geo_data['results'][0]['name']}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    now = datetime.now()
    html = f"""
    <div style='text-align:center; padding:150px 20px; font-family:sans-serif; color:white; background:#000; height:100vh;'>
        <h1 style='font-size:10rem; margin:0;'>{now.strftime("%H:%M")}</h1>
        <p style='font-size:2rem; opacity:0.6;'>{now.strftime("%A, %B %d")}</p>
        {"<h2 style='font-size:5rem;'>" + weather['emoji'] + " " + str(weather['temp']) + "°C in " + weather['name'] + "</h2>" if weather else ""}
    </div>"""
    st.markdown(html, unsafe_allow_html=True)

# --- POSTER DESIGN ENGINE ---
def clean_album_title(title):
    for kw in [" (deluxe", " [deluxe", " - deluxe", " (remaster", " (original", " [original"]:
        if kw in title.lower(): title = title[:title.lower().index(kw)]
    return title.strip()

def clean_track_title(title):
    return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def get_safe_font(size):
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]
    for path in font_paths:
        try: return ImageFont.truetype(path, size)
        except: continue
    return ImageFont.load_default()

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

def draw_wrapped_text(draw, text, font, max_width, x_anchor, start_y, fill, align="right"):
    lines, words = [], text.split()
    if not words: return start_y
    curr = words[0]
    for w in words[1:]:
        if font.getlength(curr + " " + w) <= max_width: curr += " " + w
        else: lines.append(curr); curr = w
    lines.append(curr)
    y = start_y
    for line in lines:
        x = x_anchor - font.getlength(line) if align == "right" else x_anchor
        draw.text((x, y), line, font=font, fill=fill)
        y += font.getbbox("A")[3] + 10
    return y

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
        
        album_data = sp.album(res['albums']['items'][0]['id'])
        cover_url = album_data['images'][0]['url']
        uri = album_data['uri']
        
        # Metadata
        release_date = album_data['release_date'][:4] # Just the year
        tracks = [clean_track_title(t['name'].upper()) for t in album_data['tracks']['items']][:20]

        # Download images
        headers = {'User-Agent': 'Mozilla/5.0'}
        cover_img = Image.open(BytesIO(requests.get(cover_url, headers=headers).content)).convert("RGBA")
        code_url = f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}"
        code_img = Image.open(BytesIO(requests.get(code_url).content)).convert("RGBA")

        w, h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(50))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 150)))
        draw = ImageDraw.Draw(poster)
        
        pad = 80
        c_size = 700 if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (pad, pad))
        
        # Text Layout
        f_artist = get_safe_font(90)
        f_album = get_safe_font(50)
        f_tracks = get_safe_font(30)
        
        y = draw_wrapped_text(draw, artist_name.upper(), f_artist, w - pad*2, w - pad, pad, "white")
        y = draw_wrapped_text(draw, album_name.upper(), f_album, w - pad*2, w - pad, y + 10, "#e0e0e0")
        
        # Tracklist
        ty = y + 50
        for i, t in enumerate(tracks):
            if ty > h - pad: break
            draw.text((w - pad - f_tracks.getlength(t), ty), t, font=f_tracks, fill="white")
            ty += 40

        return poster
    except Exception as e:
        st.error(f"Design Error: {e}")
        return None

# --- ROUTING LOGIC ---
current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    # --- PAIRING SCREEN ---
    st.markdown("<style>[data-testid='stSidebar'] {display:none;}</style>", unsafe_allow_html=True)
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=8))
        try:
            db.reference(f"pairing_codes/{st.session_state.pair_code}").set({
                "status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()
            })
        except: pass

    st.markdown(f"<h3 style='text-align:center; color:#7C3AED; margin-top:20vh;'>LINK YOUR DISPLAY</h3>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align:center; font-size:10rem; color:white;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    
    # Poll for link status
    try:
        ref = db.reference(f"pairing_codes/{st.session_state.pair_code}")
        res = ref.get()
        if res and res.get("status") == "linked":
            save_connection(res["venue_id"], st.session_state.temp_id)
            ref.delete()
            st.rerun()
    except: pass
    time.sleep(2)
    st.rerun()

else:
    # --- MAIN TV APP ---
    st.sidebar.title("⚙️ TV Settings")
    display_orientation = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    weather_city = st.sidebar.text_input("City for Weather", "London")
    idle_mins = st.sidebar.slider("Standby Timeout (mins)", 1, 15, 5)
    
    st.sidebar.markdown("---")
    live_mode = st.sidebar.toggle("📺 CONNECT TO CLOUD", value=True)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎸 Manual Search")
    m_artist = st.sidebar.text_input("Artist", "Oasis")
    m_album = st.sidebar.text_input("Album", "Definitely Maybe")
    
    if st.sidebar.button("Generate Layout", type="primary"):
        with st.spinner("Creating..."):
            res_img = create_poster(m_album, m_artist, display_orientation)
            if res_img:
                st.session_state.current_poster = res_img
                st.session_state.is_standby = False
                # Log to history
                try:
                    hist_id = str(int(time.time() * 1000))
                    db.reference(f"venues/{current_venue_id}/history/{hist_id}").set({
                        "track": m_album, "artist": m_artist, "time": datetime.now().strftime("%H:%M"), "type": "manual"
                    })
                except: pass

    if st.sidebar.button("Unpair Display"):
        clear_connection()
        st.rerun()

    # --- DISPLAY LOGIC ---
    if live_mode:
        if st.session_state.is_standby:
            draw_weather_dashboard(weather_city)
        elif st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        else:
            st.markdown("<h3 style='color:gray;text-align:center;margin-top:20vh;'>Waiting for music...</h3>", unsafe_allow_html=True)

        @st.fragment(run_every=5)
        def sync_engine():
            # Check for song changes
            track, artist = get_current_song_from_cloud(current_venue_id)
            if track and track != st.session_state.last_track:
                st.session_state.last_track = track
                st.session_state.last_heard_time = time.time()
                album = get_album_from_track(track, artist) or track
                new_p = create_poster(album, artist, display_orientation)
                if new_p:
                    st.session_state.current_poster = new_p
                    st.session_state.is_standby = False
                    st.rerun()
            
            # Check for standby
            if time.time() - st.session_state.last_heard_time > (idle_mins * 60):
                if not st.session_state.is_standby:
                    st.session_state.is_standby = True
                    st.rerun()
        
        sync_engine()
    else:
        # Manual Mode Display
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        else:
            st.info("Manual Mode Active. Use sidebar to generate.")
