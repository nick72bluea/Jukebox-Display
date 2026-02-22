import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
import re
import time

# --- 1. SPOTIFY CREDENTIALS ---
SPOTIPY_CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
SPOTIPY_CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]

# --- PAGE SETUP & KIOSK MODE CSS ---
st.set_page_config(
    page_title="Poster Jukebox", 
    page_icon="🎵", 
    layout="centered", 
    initial_sidebar_state="collapsed" # Hide the sidebar by default!
)

# This CSS hides the Streamlit menus, headers, and makes the background pitch black for TVs
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stApp {
                background-color: #000000;
            }
            /* Make the image center beautifully */
            [data-testid="stImage"] {
                display: flex;
                justify-content: center;
                align-items: center;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- INIT SESSION STATE (MEMORY) ---
if 'last_track' not in st.session_state:
    st.session_state.last_track = None
if 'current_poster' not in st.session_state:
    st.session_state.current_poster = None
if 'last_heard_time' not in st.session_state:
    st.session_state.last_heard_time = time.time()
if 'is_standby' not in st.session_state:
    st.session_state.is_standby = False

# --- HELPER: FIREBASE CLOUD LISTENER ---
def get_current_song_from_cloud():
    url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app/now_playing/device_1.json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and 'track' in data and 'artist' in data:
                return data['track'], data['artist']
    except Exception:
        pass # Stay silent on errors to not ruin the TV display
    return None, None

# --- HELPER: WEATHER API (OPEN-METEO) ---
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

# --- HELPER: CLEAN ALBUM & TRACK TITLES ---
def clean_album_title(title):
    keywords = [" (deluxe", " [deluxe", " - deluxe", " (remaster", " [remaster", " - remaster", " (expanded", " [expanded", " - expanded", " (original", " [original", " - original"]
    lower_title = title.lower()
    for kw in keywords:
        if kw in lower_title:
            title = title[:lower_title.index(kw)]
            lower_title = title.lower() 
    return title.strip() if title.strip() else title

def clean_track_title(title):
    cleaned = re.sub(r'[\(\[].*?[\)\]]', '', title).split('-')[0].strip()
    return cleaned

def draw_wrapped_text(draw, text, font, max_width, x_end, start_y, fill):
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
        draw.text((x_end - font.getlength(line), current_y), line, font=font, fill=fill)
        current_y += line_height
    return current_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

# --- HELPER: FIND ALBUM FROM TRACK ---
def get_album_from_track(track_name, artist_name):
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
    results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
    if results['tracks']['items']: return results['tracks']['items'][0]['album']['name']
    fallback_results = sp.search(q=f"{track_name} {artist_name}", type='track', limit=1)
    if fallback_results['tracks']['items']: return fallback_results['tracks']['items'][0]['album']['name']
    desperate_results = sp.search(q=f"{track_name}", type='track', limit=1)
    if desperate_results['tracks']['items']: return desperate_results['tracks']['items'][0]['album']['name']
    return None

# --- POSTER GENERATOR ---
def create_poster(album_name, artist_name):
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
    display_tracks = clean_tracks[:11]
    
    total_ms = sum(track['duration_ms'] for track in album_details['tracks']['items'][:11])
    duration_str = f"{total_ms // 60000}:{(total_ms % 60000) // 1000:02d}"

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    cover_img = Image.open(BytesIO(requests.get(cover_url, headers=headers).content)).convert("RGBA")
    
    code_response = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}")
    if code_response.status_code == 200:
        spotify_code_img = Image.open(BytesIO(code_response.content)).convert("RGBA")
        spotify_code_img.putdata([(255, 255, 255, int(sum(item[:3]) / 3)) for item in spotify_code_img.getdata()])
    else: spotify_code_img = Image.new('RGBA', (640, 160), (255, 255, 255, 0))

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

    font_path = next((path for path in ["/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"] if ImageFont.truetype(path, 10)), None)
    title_size = 34 if len(clean_name) > 30 else (38 if len(clean_name) > 20 else 42)
    artist_size = 45 if len(artist_name) > 35 else (60 if len(artist_name) > 25 else (75 if len(artist_name) > 15 else 95))

    font_artist = ImageFont.truetype(font_path, artist_size) if font_path else ImageFont.load_default()
    font_title = ImageFont.truetype(font_path, title_size) if font_path else ImageFont.load_default()
    font_tracks = ImageFont.truetype(font_path, 34) if font_path else ImageFont.load_default()
    font_meta = ImageFont.truetype(font_path, 19) if font_path else ImageFont.load_default()

    max_text_width = (poster_w - padding) - (padding + code_w + 20)
    new_y_after_artist = draw_wrapped_text(draw, artist_name.upper(), font_artist, max_text_width, poster_w - padding, code_y - 12, "white")
    new_y_after_title = draw_wrapped_text(draw, clean_name.upper(), font_title, max_text_width, poster_w - padding, new_y_after_artist + 5, "white")

    track_y_start = new_y_after_title + 50 
    meta_y, bar_y = poster_h - padding - 45, poster_h - padding + 5
    
    track_lines = max(1, (len(display_tracks) + 1) // 2)
    track_spacing = min(48, (meta_y - track_y_start - 20) // track_lines)
    max_col_width = (poster_w - (padding * 2)) // 2 - 30 

    mid_point = (len(display_tracks) + 1) // 2
    for i, track in enumerate(display_tracks[:mid_point]):
        text = truncate_text(f"{i+1}. {track}", font_tracks, max_col_width)
        draw.text((padding, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white")
        
    for i, track in enumerate(display_tracks[mid_point:]):
        text = truncate_text(f"{track} .{mid_point+i+1}", font_tracks, max_col_width)
        draw.text((poster_w - padding, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white", anchor="ra")

    draw.text((padding, meta_y), f"RELEASE DATE: {release_date}", font=font_meta, fill="#e0e0e0")
    draw.text((poster_w - padding, meta_y), f"ALBUM DURATION: {duration_str}", font=font_meta, fill="#e0e0e0", anchor="ra")

    segment_w = cover_size // 4
    for i in range(4):
        color = cover_img.crop((i * (cover_img.width // 4), 0, (i + 1) * (cover_img.width // 4), cover_img.height)).resize((1, 1), resample=Image.Resampling.LANCZOS).getpixel((0, 0))
        draw.rectangle([padding + (i * segment_w), bar_y, padding + ((i + 1) * segment_w), bar_y + 20], fill=color)

    return poster

# --- STREAMLIT UI ---
# Hide the settings in the sidebar so the main screen is clean!
st.sidebar.markdown("## ⚙️ TV Settings")
weather_city = st.sidebar.text_input("Local City for Weather", value="London", placeholder="e.g. Manchester")
idle_timeout_mins = st.sidebar.slider("Minutes until Standby Screen", min_value=1, max_value=15, value=5)
idle_seconds = idle_timeout_mins * 60
live_mode = st.sidebar.toggle("📺 **CONNECT TO CLOUD REMOTE**", value=True)

if live_mode:
    # We use empty containers so we can cleanly swap between weather and posters
    display_spot = st.empty()
    
    while True:
        time_since_last_song = time.time() - st.session_state.last_heard_time
        
        # 1. STANDBY LOGIC
        if time_since_last_song > idle_seconds:
            if not st.session_state.is_standby:
                st.session_state.is_standby = True
                st.session_state.current_poster = None 
                st.session_state.last_track = None
                st.toast("💤 Entering Standby Mode", icon="☁️")
            with display_spot.container(): 
                draw_weather_dashboard(weather_city)
            
        elif st.session_state.current_poster and not st.session_state.is_standby:
            # Show the poster beautifully centered with no extra text
            display_spot.image(st.session_state.current_poster, use_container_width=True)
            
        # 2. FETCH FROM CLOUD SILENTLY
        track_found, artist_found = get_current_song_from_cloud()
        
        if track_found and artist_found:
            st.session_state.is_standby = False 
            st.session_state.last_heard_time = time.time() 
            
            if track_found != st.session_state.last_track:
                # NEW SONG! Pop up a sleek little notification in the corner
                st.toast(f"Generating poster for: **{track_found}**", icon="🎨")
                st.session_state.last_track = track_found
                
                album_found = get_album_from_track(track_found, artist_found)
                
                if album_found:
                    new_poster = create_poster(album_found, artist_found)
                    
                    if new_poster:
                        st.session_state.current_poster = new_poster
                        display_spot.empty()
                        display_spot.image(new_poster, use_container_width=True)
                        st.toast(f"Now Displaying: {album_found}", icon="✅")
                    else:
                        st.toast("Could not load artwork from Spotify.", icon="❌")
                else: 
                    st.toast("Could not find album info.", icon="❌")

        time.sleep(3)
else:
    st.markdown("<h1 style='color: white; text-align: center;'>🎸 Manual Generator</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: gray; text-align: center;'>Open the sidebar (top left arrow) to reconnect to the Cloud Remote.</p>", unsafe_allow_html=True)
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1: artist_input = st.text_input("Artist Name", placeholder="e.g., Oasis")
    with col2: album_input = st.text_input("Album Name", placeholder="e.g., Definitely Maybe")

    if st.button("Generate from Search", use_container_width=True):
        if artist_input and album_input:
            with st.spinner("Designing poster..."):
                result_img = create_poster(album_input, artist_input)
                if result_img:
                    st.image(result_img, use_container_width=True)
                    buf = BytesIO()
                    result_img.save(buf, format="PNG")
                    st.download_button("Download Image", buf.getvalue(), f"{album_input}_poster.png", "image/png", use_container_width=True)
                else: st.error("Could not find that album.")
