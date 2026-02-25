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

# --- PAGE SETUP ---
st.set_page_config(page_title="Jukebox Funk TV", page_icon="🎵", layout="wide")

# Kiosk CSS
hide_st_style = """
    <style>
    [data-testid="stToolbar"], .stAppDeployButton, #MainMenu, footer { display: none !important; }
    [data-testid="stHeader"] { background-color: transparent !important; }
    [data-testid="stAppViewContainer"], .stApp, html, body { background-color: #000000 !important; overflow: hidden !important; }
    .block-container { padding: 0px !important; max-width: 100vw !important; }
    [data-testid="stImage"] img { width: 100vw !important; height: 100vh !important; object-fit: cover !important; }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- HELPERS ---
def clean_album_title(title):
    keywords = [" (deluxe", " [deluxe", " - deluxe", " (remaster", " [remaster", " - remaster", " (expanded", " (original"]
    lower_title = title.lower()
    for kw in keywords:
        if kw in lower_title: title = title[:lower_title.index(kw)]
    return title.strip()

def clean_track_title(title):
    return re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()

def get_safe_font(size):
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]
    for path in font_paths:
        try: return ImageFont.truetype(path, size)
        except: continue
    return ImageFont.load_default()

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

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

# --- DYNAMIC POSTER ENGINE (RESTORED ORIGINAL DESIGN) ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
        res = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not res['albums']['items']: return None
        
        album = res['albums']['items'][0]
        details = sp.album(album['id'])
        clean_name = clean_album_title(album['name'])
        cover_url, uri = album['images'][0]['url'], album['uri']
        
        # Metadata Restoration
        try: release_date = datetime.strptime(details['release_date'], '%Y-%m-%d').strftime('%b %d, %Y').upper()
        except: release_date = details['release_date']
        
        clean_tracks = [clean_track_title(t['name'].upper()) for t in details['tracks']['items']]
        display_tracks = clean_tracks[:22]
        total_ms = sum(t['duration_ms'] for t in details['tracks']['items'])
        duration_str = f"{total_ms // 60000}:{(total_ms % 60000) // 1000:02d}"

        # Images
        cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")
        code_res = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}")
        spotify_code_img = Image.open(BytesIO(code_res.content)).convert("RGBA")

        # Dimensions
        w, h, pad = (1200, 1800, 70) if orientation == "Portrait" else (1920, 1080, 80)
        bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(50))
        poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 140)))
        draw = ImageDraw.Draw(poster)
        
        c_size = (w - pad*2) if orientation == "Portrait" else 800
        poster.paste(cover_img.resize((c_size, c_size)), (pad, pad))
        
        # --- ORIGINAL TEXT LAYOUT RESTORED ---
        if orientation == "Portrait":
            code_y = pad + c_size + 45
            code_w = int((90 / spotify_code_img.height) * spotify_code_img.width)
            poster.paste(spotify_code_img.resize((code_w, 90)), (pad, code_y), spotify_code_img.resize((code_w, 90)))
            
            y_artist = draw_wrapped_text(draw, artist_name.upper(), get_safe_font(75), w-pad-code_w-150, w-pad, code_y-12, "white")
            y_title = draw_wrapped_text(draw, clean_name.upper(), get_safe_font(42), w-pad-code_w-150, w-pad, y_artist+5, "white")
            
            track_y = y_title + 50
            f_tracks = get_safe_font(34)
            mid = (len(display_tracks) + 1) // 2
            for i, t in enumerate(display_tracks[:mid]):
                draw.text((pad, track_y + (i*45)), truncate_text(f"{i+1}. {t}", f_tracks, (w//2)-pad-20), font=f_tracks, fill="white")
            for i, t in enumerate(display_tracks[mid:]):
                draw.text((w-pad, track_y + (i*45)), truncate_text(f"{t} .{mid+i+1}", f_tracks, (w//2)-pad-20), font=f_tracks, fill="white", anchor="ra")
        else:
            # Landscape Restored
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

        # Color Bar Restored
        bar_y, seg_w = h - pad + 5, c_size // 4
        for i in range(4):
            color = cover_img.crop((i*(cover_img.width//4), 0, (i+1)*(cover_img.width//4), cover_img.height)).resize((1,1)).getpixel((0,0))
            draw.rectangle([pad + (i*seg_w), bar_y, pad + ((i+1)*seg_w), bar_y + 20], fill=color)
        
        return poster
    except: return None

# --- FIREBASE DB HELPERS ---
def get_current_song_from_cloud(venue_id):
    try:
        ref = db.reference(f"venues/{venue_id}/now_playing")
        data = ref.get()
        return (data['track'], data['artist']) if data else (None, None)
    except: return None, None

# --- MAIN APP LOGIC ---
if 'venue_id' not in st.query_params:
    # Pairing Screen
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=8))
        db.reference(f"pairing_codes/{st.session_state.pair_code}").set({"status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()})
    
    st.markdown(f"<h1 style='text-align:center; color:white; font-size:10rem; margin-top:25vh;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    
    res = db.reference(f"pairing_codes/{st.session_state.pair_code}").get()
    if res and res.get("status") == "linked":
        st.query_params["venue_id"] = res["venue_id"]
        st.query_params["display_id"] = st.session_state.temp_id
        db.reference(f"pairing_codes/{st.session_state.pair_code}").delete()
        st.rerun()
    time.sleep(2)
    st.rerun()

else:
    # Active TV App
    v_id, d_id = st.query_params["venue_id"], st.query_params["display_id"]
    
    st.sidebar.title("⚙️ TV Settings")
    orient = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    live = st.sidebar.toggle("📺 CLOUD CONNECT", value=True)
    
    # Manual Search restoration
    st.sidebar.markdown("---")
    m_art = st.sidebar.text_input("Artist", "Oasis")
    m_alb = st.sidebar.text_input("Album", "Definitely Maybe")
    if st.sidebar.button("Generate Layout"):
        res_img = create_poster(m_alb, m_art, orient)
        if res_img:
            st.session_state.current_poster = res_img
            st.session_state.last_track = None # Break the cloud lock

    if live:
        @st.fragment(run_every=5)
        def sync():
            t, a = get_current_song_from_cloud(v_id)
            if t and t != st.session_state.get('last_track'):
                st.session_state.last_track = t
                sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET))
                search = sp.search(q=f"track:{t} artist:{a}", type='track', limit=1)
                alb = search['tracks']['items'][0]['album']['name'] if search['tracks']['items'] else t
                img = create_poster(alb, a, orient)
                if img: 
                    st.session_state.current_poster = img
                    st.rerun()
        sync()

    if st.session_state.get('current_poster'):
        st.image(st.session_state.current_poster, use_container_width=True)
