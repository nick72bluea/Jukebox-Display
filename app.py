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
    if key in os.environ: return os.environ.get(key)
    try: return st.secrets[key]
    except: return default

SPOTIPY_CLIENT_ID = get_secret("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = get_secret("SPOTIPY_CLIENT_SECRET")
FIREBASE_BASE = get_secret("FIREBASE_BASE", "").strip().rstrip('/')

# --- 2. FIREBASE ADMIN SDK INIT ---
service_account_info = get_secret("FIREBASE_SERVICE_ACCOUNT")

if service_account_info and not firebase_admin._apps:
    try:
        if isinstance(service_account_info, str):
            cert_dict = json.loads(service_account_info)
        else:
            cert_dict = service_account_info
        
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_BASE})
    except Exception as e:
        st.error(f"Firebase Init Error: {e}")

# --- 3. PAGE SETUP & CSS (Your Original Styles) ---
st.set_page_config(page_title="Jukebox Funk TV", page_icon="🎵", layout="wide", initial_sidebar_state="expanded")

# Temporary Visibility CSS (White background as requested in your base)
st.markdown("""
    <style>
    h1, h2, h3, p, div { color: #000000 !important; font-weight: bold !important; }
    .stApp { background-color: #FFFFFF !important; }
    [data-testid="stHeader"] button { visibility: visible !important; }
    </style>
""", unsafe_allow_html=True)

# --- 4. PERSISTENCE HELPERS ---
def get_saved_venue(): return st.query_params.get("venue_id", None)
def get_saved_display(): return st.query_params.get("display_id", None)
def save_connection(vid, did):
    st.query_params["venue_id"] = vid
    st.query_params["display_id"] = did
def clear_connection():
    if "venue_id" in st.query_params: del st.query_params["venue_id"]
    if "display_id" in st.query_params: del st.query_params["display_id"]

# --- 5. SESSION STATE ---
if 'last_track' not in st.session_state: st.session_state.last_track = None
if 'current_poster' not in st.session_state: st.session_state.current_poster = None
if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state: st.session_state.is_standby = False

# --- 6. CORE HELPERS (Updated to use Admin SDK for Auth) ---
def get_current_song_from_cloud(venue_id):
    try:
        # Replaced requests with Admin SDK
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
        res = geo_data['results'][0]
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={res['latitude']}&longitude={res['longitude']}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(weather_url, timeout=5).json()
        temp, code = w_data['current']['temperature_2m'], w_data['current']['weather_code']
        return {"temp": temp, "emoji": "☀️", "condition": "Clear", "name": res['name']}
    except: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    html = f"<div style='text-align: center; padding: 150px 20px; color: black; background: white; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem;'>{current_time}</h1>"
    if weather: html += f"<h2>{weather['emoji']} {weather['temp']}°C</h2>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

# (Text cleaning and Drawing functions remain exactly as your base)
def clean_album_title(title):
    for kw in [" (deluxe", " [deluxe", " - deluxe", " (remaster"]:
        if kw in title.lower(): title = title[:title.lower().index(kw)]
    return title.strip()

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
    for line in lines:
        x = x_anchor - font.getlength(line) if align=="right" else x_anchor
        draw.text((x, curr_y), line, font=font, fill=fill)
        curr_y += font.getbbox("A")[3] + 10
    return curr_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width: text = text[:-1]
    return text.strip() + "..."

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else None
    except: return None

def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not res['albums']['items']: return None
        album = res['albums']['items'][0]
        # (Poster drawing logic simplified for code length, keep your full version if needed)
        img_url = album['images'][0]['url']
        return Image.open(BytesIO(requests.get(img_url).content))
    except: return None

# --- 7. ROUTING ---
current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    # ONBOARDING (Updated to Admin SDK)
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        db.reference(f"pairing_codes/{st.session_state.pair_code}").set({
            "status": "waiting", "display_id": st.session_state.temp_display_id, "timestamp": time.time()
        })

    st.markdown(f"<h1 style='text-align: center; font-size: 8rem; color: black;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    
    time.sleep(2)
    # Check pairing status via Admin SDK
    res = db.reference(f"pairing_codes/{st.session_state.pair_code}").get()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], st.session_state.temp_display_id)
        db.reference(f"pairing_codes/{st.session_state.pair_code}").delete()
        st.rerun()
    st.rerun()

else:
    # MAIN APP
    st.sidebar.markdown("## ⚙️ TV Settings")
    display_orientation = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    weather_city = st.sidebar.text_input("City", value="London")
    idle_timeout = st.sidebar.slider("Standby (Mins)", 1, 15, 5)
    live_mode = st.sidebar.toggle("📺 **LIVE REMOTE**", key="live_mode_toggle")

    if live_mode:
        if st.session_state.is_standby:
            draw_weather_dashboard(weather_city)
        elif st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        
        @st.fragment(run_every=3)
        def background_listener():
            # Check for unpair
            reg = db.reference(f"venues/{current_venue_id}/displays/{current_display_id}").get()
            if reg is None:
                clear_connection()
                st.rerun()

            track_found, artist_found = get_current_song_from_cloud(current_venue_id)
            if track_found and track_found != st.session_state.last_track:
                st.session_state.last_track = track_found
                st.session_state.is_standby = False
                album = get_album_from_track(track_found, artist_found)
                if album:
                    st.session_state.current_poster = create_poster(album, artist_found, display_orientation)
                st.rerun()
        background_listener()
    else:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
