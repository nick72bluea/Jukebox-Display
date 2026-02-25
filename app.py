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
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except:
        return default

SPOTIPY_CLIENT_ID = get_secret("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = get_secret("SPOTIPY_CLIENT_SECRET")

# --- FIREBASE ADMIN SDK INITIALIZATION (FIXED FOR RENDER) ---
service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")

if service_account_info:
    if not firebase_admin._apps:
        try:
            # Render delivers env vars as strings; this parses it into a dict
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
    st.error("❌ Missing FIREBASE_SERVICE_ACCOUNT")

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
    [data-testid="stHeader"] { background-color: transparent !important; }
    [data-testid="stHeader"] button {
        background-color: rgba(255, 255, 255, 0.85) !important;
        border-radius: 8px !important;
        margin: 10px !important;
        border: 2px solid black !important;
    }
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
        overflow: hidden !important; 
    }
    .block-container { padding: 0px !important; max-width: 100vw !important; }
    [data-testid="stImage"] img { width: 100vw !important; height: 100vh !important; object-fit: cover !important; }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# Lifeboat CSS
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

# --- HELPER FUNCTIONS ---
def get_current_song_from_cloud(venue_id):
    try:
        ref = db.reference(f"venues/{venue_id}/now_playing")
        data = ref.get()
        if data: return data.get('track'), data.get('artist')
    except: pass
    return None, None

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_data = requests.get(geo_url, timeout=5).json()
        if not geo_data.get('results'): return None
        lat, lon = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude']
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(w_url, timeout=5).json()
        return {"temp": w_data['current']['temperature_2m'], "emoji": "☀️", "condition": "Clear", "name": geo_data['results'][0]['name']}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    html = f"<div style='text-align: center; padding: 150px; color: white; background: black; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem;'>{current_time}</h1>"
    if weather: html += f"<h2>{weather['emoji']} {weather['temp']}°C in {weather['name']}</h2>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def clean_album_title(title):
    keywords = [" (deluxe", " [deluxe", " - deluxe", " (remaster", " [remaster"]
    for kw in keywords:
        if kw in title.lower(): title = title[:title.lower().index(kw)]
    return title.strip()

def clean_track_title(title):
    return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def get_safe_font(size):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]
    for p in paths:
        try: return ImageFont.truetype(p, size)
        except: continue
    return ImageFont.load_default()

def draw_wrapped_text(draw, text, font, max_width, x_anchor, start_y, fill, align="right"):
    if not text: return start_y
    lines, words = [], text.split()
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

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

def get_album_from_track(track, artist):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"track:{track} artist:{artist}", type='track', limit=1)
        return res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else None
    except: return None

# --- RESTORED POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not res['albums']['items']: return None
        
        album = res['albums']['items'][0]
        details = sp.album(album['id'])
        clean_name = clean_album_title(album['name'])
        cover_url, uri = album['images'][0]['url'], album['uri']
        
        try: release_date = datetime.strptime(details['release_date'], '%Y-%m-%d').strftime('%b %d, %Y').upper()
        except: release_date = details['release_date']
        
        clean_tracks = [clean_track_title(t['name'].upper()) for t in details['tracks']['items']]
        display_tracks = clean_tracks[:22]
        total_ms = sum(t['duration_ms'] for t in details['tracks']['items'])
        duration_str = f"{total_ms // 60000}:{(total_ms % 60000) // 1000:02d}"

        cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")
        code_res = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}")
        spotify_code_img = Image.open(BytesIO(code_res.content)).convert("RGBA")

        w, h, pad = (1200, 1800, 70) if orientation == "Portrait" else (1920, 1080, 80)
        bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(50))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        c_size = (w - pad*2) if orientation == "Portrait" else 800
        draw.rectangle([pad-3, pad-3, pad+c_size+2, pad+c_size+2], fill="black")
        poster.paste(cover_img.resize((c_size, c_size)), (pad, pad))
        
        if orientation == "Portrait":
            code_y = pad + c_size + 45
            code_w = int((90 / spotify_code_img.height) * spotify_code_img.width)
            poster.paste(spotify_code_img.resize((code_w, 90)), (pad, code_y), spotify_code_img.resize((code_w, 90)))
            
            y_artist = draw_wrapped_text(draw, artist_name.upper(), get_safe_font(75), w-pad-code_w-150, w-pad, code_y-12, "white")
            y_title = draw_wrapped_text(draw, clean_name.upper(), get_safe_font(42), w-pad-code_w-150, w-pad, y_artist+5, "white")
            
            track_y, f_tracks = y_title + 50, get_safe_font(34)
            mid = (len(display_tracks) + 1) // 2
            for i, t in enumerate(display_tracks[:mid]):
                draw.text((pad, track_y + (i*45)), truncate_text(f"{i+1}. {t}", f_tracks, (w//2)-pad-20), font=f_tracks, fill="white")
            for i, t in enumerate(display_tracks[mid:]):
                draw.text((w-pad, track_y + (i*45)), truncate_text(f"{t} .{mid+i+1}", f_tracks, (w//2)-pad-20), font=f_tracks, fill="white", anchor="ra")
        else:
            tx = pad + c_size + 80
            code_w = int((100 / spotify_code_img.height) * spotify_code_img.width)
            poster.paste(spotify_code_img.resize((code_w, 100)), (tx, pad), spotify_code_img.resize((code_w, 100)))
            y_art = draw_wrapped_text(draw, artist_name.upper(), get_safe_font(90), w-tx-pad, w-pad, pad-10, "white")
            y_tit = draw_wrapped_text(draw, clean_name.upper(), get_safe_font(50), w-tx-pad, w-pad, y_art+15, "#e0e0e0")
            
            track_y, f_tracks = y_tit + 70, get_safe_font(34)
            mid = (len(display_tracks) + 1) // 2
            for i, t in enumerate(display_tracks[:mid]):
                draw.text((tx, track_y + (i*45)), truncate_text(f"{i+1}. {t}", f_tracks, (w-tx-pad)//2-20), font=f_tracks, fill="white")
            for i, t in enumerate(display_tracks[mid:]):
                draw.text((w-pad, track_y + (i*45)), truncate_text(f"{t} .{mid+i+1}", f_tracks, (w-tx-pad)//2-20), font=f_tracks, fill="white", anchor="ra")

        bar_y, seg_w = h - pad + 5, c_size // 4
        for i in range(4):
            color = cover_img.crop((i*(cover_img.width//4), 0, (i+1)*(cover_img.width//4), cover_img.height)).resize((1,1)).getpixel((0,0))
            draw.rectangle([pad + (i*seg_w), bar_y, pad + ((i+1)*seg_w), bar_y + 20], fill=color)
        
        return poster
    except: return None

# --- MAIN LOGIC ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None
if 'is_standby' not in st.session_state: st.session_state.is_standby = False

v_id = get_saved_venue()
d_id = get_saved_display()

if not v_id:
    # Pairing State
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=8))
        db.reference(f"pairing_codes/{st.session_state.pair_code}").set({"status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()})
    
    st.markdown(f"<h1 style='text-align:center; font-size:8rem; margin-top:20vh;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    
    res = db.reference(f"pairing_codes/{st.session_state.pair_code}").get()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], st.session_state.temp_id)
        db.reference(f"pairing_codes/{st.session_state.pair_code}").delete()
        st.rerun()
    time.sleep(2)
    st.rerun()

else:
    # Paired State
    st.sidebar.title("⚙️ TV Settings")
    orient = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    live = st.sidebar.toggle("📺 CONNECT TO CLOUD", value=True)
    
    st.sidebar.markdown("### Manual Search")
    m_art = st.sidebar.text_input("Artist", "Oasis")
    m_alb = st.sidebar.text_input("Album", "Definitely Maybe")
    if st.sidebar.button("Generate"):
        img = create_poster(m_alb, m_art, orient)
        if img: 
            st.session_state.current_poster = img
            st.session_state.is_standby = False

    if live:
        @st.fragment(run_every=5)
        def sync():
            t, a = get_current_song_from_cloud(v_id)
            if t and t != st.session_state.last_track:
                st.session_state.last_track = t
                alb = get_album_from_track(t, a) or t
                img = create_poster(alb, a, orient)
                if img: 
                    st.session_state.current_poster = img
                    st.session_state.is_standby = False
                    st.rerun()
        sync()

    if st.session_state.get('current_poster'):
        st.image(st.session_state.current_poster, use_container_width=True)
