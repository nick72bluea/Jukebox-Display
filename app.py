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
SPOTIPY_CLIENT_ID = '02c1d6fcc3a149138d815e4036c0c36e'
SPOTIPY_CLIENT_SECRET = '7e96739194134d83ba322af5cefd9af4'
FIREBASE_BASE = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Jukebox Funk TV", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# --- BULLETPROOF KIOSK & VISIBILITY CSS ---
st.markdown("""
    <style>
    /* 1. Hide default Streamlit tools */
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { display: none !important; }
    
    /* 2. BRUTE FORCE SIDEBAR TOGGLE VISIBILITY */
    /* This creates a purple tab on the left that is ALWAYS on top */
    [data-testid="collapsedControl"] {
        background-color: #7C3AED !important; /* Bright Purple */
        border-radius: 0 10px 10px 0 !important;
        width: 50px !important;
        height: 50px !important;
        top: 20px !important;
        left: 0px !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        z-index: 1000001 !important;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
    }
    
    /* Make the arrow inside the purple tab white and big */
    [data-testid="collapsedControl"] svg {
        fill: white !important;
        width: 30px !important;
        height: 30px !important;
    }

    /* 3. True Black Kiosk Background */
    [data-testid="stAppViewContainer"], .stApp, html, body { 
        background-color: #000000 !important; 
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* 4. Remove padding for edge-to-edge display */
    .block-container {
        padding: 0px !important;
        margin: 0px !important;
        max-width: 100vw !important;
    }
    
    /* 5. Poster Display Fix */
    [data-testid="stImage"] img { 
        width: 100vw !important; 
        height: 100vh !important; 
        object-fit: contain !important; /* Changed to contain to ensure poster fits screen */
        background-color: black;
    }

    /* 6. Sidebar look */
    [data-testid="stSidebar"] {
        background-color: #111111 !important;
        border-right: 1px solid #333333;
    }
    </style>
""", unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS ---
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

# --- HELPERS ---
def get_current_song_from_cloud(venue_id):
    url = f"{FIREBASE_BASE}/venues/{venue_id}/now_playing.json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and 'track' in data: return data['track'], data['artist']
    except: pass 
    return None, None

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_data = requests.get(geo_url, timeout=5).json()
        lat, lon, name = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude'], geo_data['results'][0]['name']
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(w_url).json()
        return {"temp": w_data['current']['temperature_2m'], "name": name}
    except: return None

def draw_weather_dashboard(city):
    w = get_weather(city)
    now = datetime.now()
    st.markdown(f"""
        <div style='text-align: center; color: white; background: black; height: 100vh; padding-top: 20vh;'>
            <h1 style='font-size: 10rem;'>{now.strftime("%H:%M")}</h1>
            <p style='font-size: 2rem; opacity: 0.5;'>{now.strftime("%A, %B %d")}</p>
            {f"<h2 style='font-size: 4rem;'>{w['temp']}°C in {w['name']}</h2>" if w else ""}
        </div>
    """, unsafe_allow_html=True)

def get_album_from_track(track_name, artist_name):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else None
    except: return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        album = results['albums']['items'][0]
        cover_url = album['images'][0]['url']
        cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")
        
        def get_safe_font(size):
            paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
            for p in paths:
                try: return ImageFont.truetype(p, size)
                except: continue
            return ImageFont.load_default()

        p_w, p_h = (1200, 1800) if orientation == "Portrait" else (1920, 1080)
        bg = cover_img.resize((p_w, p_h)).filter(ImageFilter.GaussianBlur(radius=40))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 150)))
        draw = ImageDraw.Draw(poster)
        
        c_size = 900 if orientation == "Portrait" else 750
        poster.paste(cover_img.resize((c_size, c_size)), (150, 100))
        
        draw.text((150, p_h - 250), artist_name.upper(), font=get_safe_font(80), fill="white")
        draw.text((150, p_h - 150), album_name.upper(), font=get_safe_font(40), fill="#cccccc")
        
        return poster
    except: return None

# --- ROUTING ---
vid = get_saved_venue()
did = get_saved_display()

if not vid:
    # Pairing Screen
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        requests.put(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json", 
                     json={"status": "waiting", "timestamp": time.time()})
    
    st.markdown(f"<h1 style='text-align: center; color: white; margin-top: 30vh; font-size: 8rem;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    time.sleep(3)
    res = requests.get(f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json").json()
    if res and res.get("status") == "linked":
        save_connection(res["venue_id"], "render_tv")
        st.rerun()
    st.rerun()

else:
    # Sidebar
    with st.sidebar:
        st.header("⚙️ TV Settings")
        orient = st.radio("Layout", ["Portrait", "Landscape"], index=1)
        city = st.text_input("City", "London")
        live = st.toggle("Cloud Sync", value=True)
        if st.button("Unpair"):
            clear_connection()
            st.rerun()

    # Main Display
    if live:
        if st.session_state.is_standby:
            draw_weather_dashboard(city)
        elif st.session_state.current_poster:
            st.image(st.session_state.current_poster)
        
        @st.fragment(run_every=3)
        def sync_loop():
            t, a = get_current_song_from_cloud(vid)
            if t and t != st.session_state.last_track:
                st.session_state.last_track = t
                alb = get_album_from_track(t, a)
                if alb:
                    st.session_state.current_poster = create_poster(alb, a, orient)
                    st.session_state.is_standby = False
                    st.rerun()
        sync_loop()
    else:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster)
            
