import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
import re
import os
import streamlit as st

# --- SECURE CREDENTIAL FETCHER ---
def get_cred(key):
    # Try Railway/Server environment variables first
    if key in os.environ:
        return os.environ[key]
    # Fallback to local Streamlit secrets
    try:
        return st.secrets[key]
    except Exception:
        return None

# --- CREDENTIALS ---
SPOTIPY_CLIENT_ID = get_cred("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = get_cred("SPOTIPY_CLIENT_SECRET")

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

    def get_safe_font(size):
        # We try Arial Narrow first, then fallback gracefully.
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf", 
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 
            "/Library/Fonts/Arial Bold.ttf", 
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        ]
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

        # --- DYNAMIC TRACK SPACING FIX ---
        track_y_start = new_y_after_title + 60 
        meta_y, bar_y = poster_h - padding - 45, poster_h - padding + 5
        
        available_space = meta_y - track_y_start - 30
        track_lines = max(1, (len(display_tracks) + 1) // 2)
        
        # Calculate optimal spacing, but enforce a minimum so text NEVER overlaps
        optimal_spacing = available_space // track_lines if track_lines > 0 else 50
        track_spacing = min(40, optimal_spacing)
        
        # If tracks are squishing too hard (less than 35px), we trim the tracklist for a clean aesthetic
        if track_spacing < 35:
            display_tracks = display_tracks[:18]  # Limit to 18 tracks to keep it legible
            track_lines = max(1, (len(display_tracks) + 1) // 2)
            track_spacing = min(50, available_space // track_lines) if track_lines > 0 else 50

        # Restore the middle gap and significantly reduce the font size
        max_col_width = (poster_w - (padding * 2)) // 2 - 20 
        font_tracks = get_safe_font(22)

        mid_point = (len(display_tracks) + 1) // 2
        for i, track in enumerate(display_tracks[:mid_point]):
            text = truncate_text(f"{i+1}. {track}", font_tracks, max_col_width)
            draw.text((padding, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white")
            
        for i, track in enumerate(display_tracks[mid_point:]):
            text = truncate_text(f"{track} .{mid_point+i+1}", font_tracks, max_col_width)
            draw.text((poster_w - padding, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white", anchor="ra")

        # Give the meta text slightly larger fonts to match your reference image
        draw.text((padding, meta_y), f"RELEASE DATE: {release_date}", font=get_safe_font(22), fill="#e0e0e0")
        draw.text((poster_w - padding, meta_y), f"ALBUM DURATION: {duration_str}", font=get_safe_font(22), fill="#e0e0e0", anchor="ra")

        segment_w = cover_size // 4
        for i in range(4):
            color = cover_img.crop((i * (cover_img.width // 4), 0, (i + 1) * (cover_img.width // 4), cover_img.height)).resize((1, 1), resample=Image.Resampling.LANCZOS).getpixel((0, 0))
            draw.rectangle([padding + (i * segment_w), bar_y, padding + ((i + 1) * segment_w), bar_y + 20], fill=color)

    else:
        # --- LANDSCAPE LOGIC ---
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
        
        # --- REDUCED TEXT SIZE & TIGHTER SPACING FOR LANDSCAPE ---
        font_tracks = get_safe_font(24) # Shrunk from 34 to 24
        meta_y = poster_h - padding - 45
        
        if len(display_tracks) <= 11:
            track_spacing = 40 # Tightened from 45
            max_track_width = right_edge_x - text_start_x
            for i, track in enumerate(display_tracks):
                text = truncate_text(f"{track} .{i+1}", font_tracks, max_track_width)
                draw.text((right_edge_x, track_y_start + (i * track_spacing)), text, font=font_tracks, fill="white", anchor="ra")
        else:
            mid_point = (len(display_tracks) + 1) // 2
            
            available_space = meta_y - track_y_start - 20
            optimal_spacing = available_space // mid_point if mid_point > 0 else 40
            track_spacing = min(40, optimal_spacing) # Tightened from 45
            
            # Anti-squish logic for Landscape
            if track_spacing < 30:
                display_tracks = display_tracks[:18]
                mid_point = (len(display_tracks) + 1) // 2
                track_spacing = min(40, available_space // mid_point) if mid_point > 0 else 40
                
            # Keep a nice clean gutter in the middle of the columns
            max_col_width = (right_edge_x - text_start_x) // 2 - 30 
            
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
