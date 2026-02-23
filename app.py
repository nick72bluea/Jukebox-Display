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

# --- 1. CONFIG & CREDENTIALS ---
SPOTIPY_CLIENT_ID = '02c1d6fcc3a149138d815e4036c0c36e'
SPOTIPY_CLIENT_SECRET = '7e96739194134d83ba322af5cefd9af4'
FIREBASE_BASE = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"

# --- PAGE SETUP & KIOSK MODE CSS ---
st.set_page_config(
    page_title="Poster Jukebox", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" 
)

hide_st_style = """
    <style>
    /* 1. Hide Streamlit's default UI elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] { display: none !important; }
    div[data-testid="stToolbar"] { display: none !important; }
    div[data-testid="stDecoration"] { display: none !important; }
    div[data-testid="stStatusWidget"] { display: none !important; }

    /* 2. Force the entire page background to pitch black */
    .stApp, html, body { 
        background-color: #000000 !important; 
    }

    /* 3. Nuke Streamlit's default padding (the white border) */
    .block-container {
        padding: 0px !important;
        margin: 0px !important;
        max-width: 100% !important;
    }

    /* 4. Force the image to expand to the literal edges of the screen */
    [data-testid="stImage"] {
        width: 100vw !important;
        height: 100vh !important;
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    [data-testid="stImage"] img {
        width: 100vw !important;
        height: 100vh !important;
        object-fit: cover !important; 
    }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS (URL PARAMETERS) ---
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

# --- HELPERS (Cloud, Weather, Text) ---
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
        geo_data = requests.get(geo_url).json()
        if not geo_data.get('results'): return None
        lat, lon, resolved_name = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude'], geo_data['results'][0]['name']
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        weather_data = requests.get(weather_url).json()
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
        if align == "right":
            draw.text((x_anchor - font.getlength(line), current_y), line, font=font, fill=fill)
        else:
            draw.text((x_anchor, current_y), line, font=font, fill=fill)
        current_y += line_height
    return current_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

def get_album_from_track(track_name, artist_name):
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
    results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
    if results['tracks']['items']: return results['tracks']['items'][0]['album']['name']
    fallback = sp.search(q=f"{track_name} {artist_name}", type='track', limit=1)
    if fallback['tracks']['items']: return fallback['tracks']['items'][0]['album']['name']
    return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name, orientation="Portrait"):
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
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

    headers = {'User-Agent': 'Mozilla/5.0'}
    cover_img = Image.open(BytesIO(requests.get(cover_url, headers=headers).content)).convert("RGBA")
    
    code_response = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}")
    if code_response.status_code == 200:
        spotify_code_img = Image.open(BytesIO(code_response.content)).convert("RGBA")
        spotify_code_img.putdata([(255, 255, 255, int(sum(item[:3]) / 3)) for item in spotify_code_img.getdata()])
    else: spotify_code_img = Image.new('RGBA', (640, 160), (255, 255, 255, 0))

    def get_safe_font(size):
        font_paths = ["/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
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
        
        code_y = padding + cover_size + 45      
        code_w = int((90 / spotify_code_img.height) * spotify_code_img.width)
        poster.paste(spotify_code_img.resize((code_w, 90)), (padding, code_y), spotify_code_img.resize((code_w, 90)))

        title_size = 34 if len(clean_name) > 30 else (38 if len(clean_name) > 20 else 42)
        artist_size = 45 if len(artist_name) > 35 else (60 if len(artist_name) > 25 else 75)
        
        max_text_width = (poster_w - padding) - (padding + code_w + 20)
        new_y_after_artist = draw_wrapped_text(draw, artist_name.upper(), get_safe_font(artist_size), max_text_width, poster_w - padding, code_y - 12, "white", "right")
        new_y_after_title = draw_wrapped_text(draw, clean_name.upper(), get_safe_font(title_size), max_text_width, poster_w - padding, new_y_after_artist + 5, "white", "right")

        track_y_start = new_y_after_title + 50 
        meta_y, bar_y = poster_h - padding - 45, poster_h - padding + 5
        
        track_lines = max(1, (len(display_tracks) + 1) // 2)
        track_spacing = min(48, (meta_y - track_y_start - 20) // track_lines)
        max_col_width = (poster_w - (padding * 2)) // 2 - 30 
        font_tracks = get_safe_font(34)

        mid_point = (len(display_tracks) + 1) // 2
        for i, track in enumerate(display_tracks[:mid_point]):
            text = truncate_text(f"{i+1}. {track}", font_tracks, max_col_width)
            draw.text((padding, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white")
            
        for i, track in enumerate(display_tracks[mid_point:]):
            text = truncate_text(f"{track} .{mid_point+i+1}", font_tracks, max_col_width)
            draw.text((poster_w - padding, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white", anchor="ra")

        draw.text((padding, meta_y), f"RELEASE DATE: {release_date}", font=get_safe_font(19), fill="#e0e0e0")
        draw.text((poster_w - padding, meta_y), f"ALBUM DURATION: {duration_str}", font=get_safe_font(19), fill="#e0e0e0", anchor="ra")

        segment_w = cover_size // 4
        for i in range(4):
            color = cover_img.crop((i * (cover_img.width // 4), 0, (i + 1) * (cover_img.width // 4), cover_img.height)).resize((1, 1), resample=Image.Resampling.LANCZOS).getpixel((0, 0))
            draw.rectangle([padding + (i * segment_w), bar_y, padding + ((i + 1) * segment_w), bar_y + 20], fill=color)

    else:
        poster_w, poster_h, padding = 1920, 1080, 80
        cover_size = 800 
        
        bg_img = cover_img.resize((poster_w, poster_h)).filter(ImageFilter.GaussianBlur(radius=50))
        poster = Image.alpha_composite(bg_img, Image.new('RGBA', bg_img.size, (0, 0, 0, 160))) 
        draw = ImageDraw.Draw(poster)
        
        draw.rectangle([padding-3, padding-3, padding+cover_size+2, padding+cover_size+2], fill="black")
        poster.paste(cover_img.resize((cover_size, cover_size)), (padding, padding))
        
        text_start_x = padding + cover_size + 80
        code_w = int((100 / spotify_code_img.height) * spotify_code_img.width)
        poster.paste(spotify_code_img.resize((code_w, 100)), (text_start_x, padding), spotify_code_img.resize((code_w, 100)))

        right_edge_x = poster_w - padding
        max_title_width = (poster_w - padding) - (text_start_x + code_w + 40)
        
        artist_size = 70 if len(artist_name) > 25 else 90
        title_size = 40 if len(clean_name) > 30 else 50
        
        new_y_after_artist = draw_wrapped_text(draw, artist_name.upper(), get_safe_font(artist_size), max_title_width, right_edge_x, padding - 10, "white", "right")
        new_y_after_title = draw_wrapped_text(draw, clean_name.upper(), get_safe_font(title_size), max_title_width, right_edge_x, new_y_after_artist + 15, "#e0e0e0", "right")

        track_y_start = new_y_after_title + 70 
        font_tracks = get_safe_font(34)
        meta_y = poster_h - padding - 45
        
        if len(display_tracks) <= 11:
            track_spacing = 45
            max_track_width = right_edge_x - text_start_x
            for i, track in enumerate(display_tracks):
                text = truncate_text(f"{track} .{i+1}", font_tracks, max_track_width)
                draw.text((right_edge_x, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white", anchor="ra")
        else:
            mid_point = (len(display_tracks) + 1) // 2
            track_spacing = min(45, (meta_y - track_y_start - 20) // mid_point) 
            max_col_width = (right_edge_x - text_start_x) // 2 - 20
            
            for i, track in enumerate(display_tracks[:mid_point]):
                text = truncate_text(f"{i+1}. {track}", font_tracks, max_col_width)
                draw.text((text_start_x, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white")
                
            for i, track in enumerate(display_tracks[mid_point:]):
                text = truncate_text(f"{track} .{mid_point+i+1}", font_tracks, max_col_width)
                draw.text((right_edge_x, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white", anchor="ra")

        draw.text((padding, meta_y), f"RELEASE DATE: {release_date}", font=get_safe_font(22), fill="#cccccc")
        draw.text((poster_w - padding, meta_y), f"ALBUM DURATION: {duration_str}", font=get_safe_font(22), fill="#cccccc", anchor="ra")

        bar_y = poster_h - padding + 5
        bar_width = poster_w - (padding * 2)
        segment_w = bar_width // 4
        
        for i in range(4):
            color = cover_img.crop((i * (cover_img.width // 4), 0, (i + 1) * (cover_img.width // 4), cover_img.height)).resize((1, 1), resample=Image.Resampling.LANCZOS).getpixel((0, 0))
            draw.rectangle([padding + (i * segment_w), bar_y, padding + ((i + 1) * segment_w), bar_y + 20], fill=color)

    return poster


# ==========================================
# --- CORE APP LOGIC (ROUTING) ---
# ==========================================

current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    # --- BUG FIX: BANISH THE SIDEBAR ---
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    # --- ONBOARDING / WAITING ROOM ---
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        
        url = f"{FIREBASE_BASE}/pairing_codes/{st.session_state.pair_code}.json"
        requests.put(url, json={
            "status": "waiting", 
            "display_id": st.session_state.temp_display_id,
            "timestamp": time.time()
        })

    code = st.session_state.pair_code
    formatted_code = f"{code[:3]} {code[3:]}"
    
    st.markdown(f"<h3 style='text-align: center; color: #7C3AED; margin-top: 15vh; font-family: sans-serif; letter-spacing: 4px;'>LINK YOUR DISPLAY</h3>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center; font-size: 8rem; color: white; margin-top: -20px;'>{formatted_code}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray; font-size: 1.5rem;'>Enter this code in the Jukebox Funk app.</p>", unsafe_allow_html=True)
    
    time.sleep(2)
    url = f"{FIREBASE_BASE}/pairing_codes/{code}.json"
    try:
        res = requests.get(url, timeout=5).json()
        if res and res.get("status") == "linked" and res.get("venue_id"):
            save_connection(res["venue_id"], st.session_state.temp_display_id)
            requests.delete(url)
            st.rerun() 
    except Exception:
        pass
        
    st.rerun() 

else:
    # --- PAIRED STATE (MAIN APP) ---
    
    if 'live_mode_toggle' not in st.session_state: st.session_state.live_mode_toggle = False
    if 'prev_live_mode' not in st.session_state: st.session_state.prev_live_mode = False

    st.sidebar.markdown("## ⚙️ TV Settings")
    display_orientation = st.sidebar.radio("Display Layout", ["Portrait", "Landscape"], index=1, key="display_layout")
    st.sidebar.markdown("---")
    weather_city = st.sidebar.text_input("Local City for Weather", value="London")
    idle_timeout_mins = st.sidebar.slider("Minutes until Standby Screen", min_value=1, max_value=15, value=5)

    if 'last_orientation' not in st.session_state: st.session_state.last_orientation = display_orientation

    st.sidebar.markdown("---")
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
            
            # --- CLOUD VAULT SYNC ---
            if current_venue_id:
                record_id = str(int(time.time() * 1000))
                timestamp = datetime.now().strftime("%H:%M")
                url = f"{FIREBASE_BASE}/venues/{current_venue_id}/history/{record_id}.json"
                payload = {
                    "id": record_id,
                    "track": st.session_state.manual_album,
                    "artist": st.session_state.manual_artist,
                    "time": timestamp,
                    "type": "manual"
                }
                try:
                    requests.put(url, json=payload, timeout=3)
                except Exception:
                    pass

    st.sidebar.button("Generate Layout", type="primary", on_click=generate_manual_poster)
    
    st.sidebar.markdown("---")
    def unpair_display():
        requests.delete(f"{FIREBASE_BASE}/venues/{current_venue_id}/displays/{current_display_id}.json")
        clear_connection()
        if 'pair_code' in st.session_state: del st.session_state.pair_code
        st.session_state.current_poster = None
        st.session_state.last_track = None
        
    st.sidebar.button("Unpair Display", type="secondary", on_click=unpair_display, use_container_width=True)

    # --- MAIN DISPLAY AREA ---
    if live_mode:
        if st.session_state.is_standby:
            draw_weather_dashboard(weather_city)
        elif st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        else:
            st.markdown(f"<h3 style='color:gray;text-align:center;margin-top:200px;'>Listening to Venue Cloud...<br><span style='font-size:12px;opacity:0.5;'>Venue: {current_venue_id}<br>Display: {current_display_id}</span></h3>", unsafe_allow_html=True)

        @st.fragment(run_every=3)
        def background_listener():
            needs_rerun = False
            
            # 1. THE REGISTRY CHECK
            registry_url = f"{FIREBASE_BASE}/venues/{current_venue_id}/displays/{current_display_id}.json"
            registry_res = requests.get(registry_url)
            if registry_res.status_code == 200 and registry_res.json() is None:
                clear_connection()
                st.toast("Unpaired from Remote App.", icon="🔌")
                st.rerun()

            # 2. THE MUSIC CHECK
            track_found, artist_found = get_current_song_from_cloud(current_venue_id)
            if track_found and artist_found:
                st.session_state.last_heard_time = time.time() 
                
                song_changed = (track_found != st.session_state.last_track)
                layout_changed = (display_orientation != st.session_state.last_orientation)
                
                if song_changed or layout_changed:
                    st.session_state.last_track = track_found
                    st.session_state.last_orientation = display_orientation
                    st.session_state.is_standby = False
                    
                    if song_changed:
                        st.toast(f"Generating poster for: **{track_found}**", icon="🎨")
                    else:
                        st.toast(f"Redrawing layout to **{display_orientation}**...", icon="🔄")
                    
                    album_found = get_album_from_track(track_found, artist_found)
                    if album_found:
                        new_poster = create_poster(album_found, artist_found, display_orientation)
                        if new_poster:
                            st.session_state.current_poster = new_poster
                            if song_changed:
                                st.toast(f"Now Displaying: {album_found}", icon="✅")
                    needs_rerun = True

            time_since_last_song = time.time() - st.session_state.last_heard_time
            if time_since_last_song > (idle_timeout_mins * 60):
                if not st.session_state.is_standby:
                    st.session_state.is_standby = True
                    st.session_state.current_poster = None
                    st.session_state.last_track = None
                    st.toast("💤 Entering Standby Mode", icon="☁️")
                    needs_rerun = True
                    
            if needs_rerun:
                st.rerun()
                
        background_listener()

    else:
        if st.session_state.current_poster:
            st.image(st.session_state.current_poster, use_container_width=True)
        else:
            st.markdown("<h3 style='color:gray;text-align:center;margin-top:200px;'>Manual Mode Active<br><span style='font-size: 0.6em; font-weight: normal;'>Use the sidebar to generate a poster.</span></h3>", unsafe_allow_html=True)
