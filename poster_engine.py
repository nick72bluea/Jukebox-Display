import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
import re
import os

# --- CREDENTIALS ---
# Try to get from environment first (for cloud deployment), then fallback to hardcoded for local testing
SPOTIPY_CLIENT_ID = os.environ.get('SPOTIPY_CLIENT_ID', '02c1d6fcc3a149138d815e4036c0c36e')
SPOTIPY_CLIENT_SECRET = os.environ.get('SPOTIPY_CLIENT_SECRET', '7e96739194134d83ba322af5cefd9af4')

# --- TEXT HELPERS ---
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

# --- SPOTIFY HELPERS ---
def get_album_from_track(track_name, artist_name):
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))
    results = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
    if results['tracks']['items']: return results['tracks']['items'][0]['album']['name']
    fallback = sp.search(q=f"{track_name} {artist_name}", type='track', limit=1)
    if fallback['tracks']['items']: return fallback['tracks']['items'][0]['album']['name']
    return None

# --- MAIN GENERATOR ---
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
