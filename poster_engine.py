import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
import re

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

def get_safe_font(size):
    font_paths = ["/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for path in font_paths:
        try: return ImageFont.truetype(path, size)
        except IOError: continue
    return ImageFont.load_default()

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
        x = x_anchor - font.getlength(line) if align == "right" else x_anchor
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += line_height
    return current_y

def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width: return text
    while font.getlength(text + "...") > max_width and len(text) > 0: text = text[:-1]
    return text.strip() + "..."

def get_album_from_track(track_name, artist_name, client_id, client_secret):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
        res = sp.search(q=f"track:{track_name} artist:{artist_name}", type='track', limit=1)
        return res['tracks']['items'][0]['album']['name'] if res['tracks']['items'] else None
    except: return None

def create_poster(album_name, artist_name, orientation, client_id, client_secret):
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
        results = sp.search(q=f"album:{album_name} artist:{artist_name}", type='album', limit=1)
        if not results['albums']['items']: return None
        
        album = results['albums']['items'][0]
        album_details = sp.album(album['id'])
        clean_name = clean_album_title(album['name'])
        cover_url, uri = album['images'][0]['url'], album['uri'] 

        try: release_date = datetime.strptime(album_details['release_date'], '%Y-%m-%d').strftime('%b %d, %Y').upper()
        except: release_date = album_details['release_date']
        
        clean_tracks = [clean_track_title(t['name'].upper()) for t in album_details['tracks']['items']]
        display_tracks = clean_tracks[:22]
        total_ms = sum(t['duration_ms'] for t in album_details['tracks']['items'])
        duration_str = f"{total_ms // 60000}:{(total_ms % 60000) // 1000:02d}"

        cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")
        code_res = requests.get(f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}")
        spotify_code_img = Image.open(BytesIO(code_res.content)).convert("RGBA")

        if orientation == "Portrait":
            w, h, pad = 1200, 1800, 70
            c_size = w - (pad * 2)
            bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(40))
            poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 130)))
            draw = ImageDraw.Draw(poster)
            draw.rectangle([pad-3, pad-3, pad+c_size+2, pad+c_size+2], fill="black")
            poster.paste(cover_img.resize((c_size, c_size)), (pad, pad))
            code_y = pad + c_size + 45
            code_w = int((90 / spotify_code_img.height) * spotify_code_img.width)
            poster.paste(spotify_code_img.resize((code_w, 90)), (pad, code_y), spotify_code_img.resize((code_w, 90)))
            y_art = draw_wrapped_text(draw, artist_name.upper(), get_safe_font(75), w-pad-code_w-150, w-pad, code_y-12, "white")
            y_tit = draw_wrapped_text(draw, clean_name.upper(), get_safe_font(42), w-pad-code_w-150, w-pad, y_art+5, "white")
            mid = (len(display_tracks) + 1) // 2
            f_tracks = get_safe_font(34)
            for i, t in enumerate(display_tracks[:mid]):
                draw.text((pad, y_tit+50+(i*48)), truncate_text(f"{i+1}. {t}", f_tracks, 500), font=f_tracks, fill="white")
            for i, t in enumerate(display_tracks[mid:]):
                draw.text((w-pad, y_tit+50+(i*48)), truncate_text(f"{t} .{mid+i+1}", f_tracks, 500), font=f_tracks, fill="white", anchor="ra")
        else:
            w, h, pad = 1920, 1080, 80
            c_size = 800
            bg = cover_img.resize((w, h)).filter(ImageFilter.GaussianBlur(50))
            poster = Image.alpha_composite(bg, Image.new('RGBA', bg.size, (0, 0, 0, 160)))
            draw = ImageDraw.Draw(poster)
            draw.rectangle([pad-3, pad-3, pad+c_size+2, pad+c_size+2], fill="black")
            poster.paste(cover_img.resize((c_size, c_size)), (pad, pad))
            tx = pad + c_size + 80
            code_w = int((100 / spotify_code_img.height) * spotify_code_img.width)
            poster.paste(spotify_code_img.resize((code_w, 100)), (tx, pad), spotify_code_img.resize((code_w, 100)))
            y_art = draw_wrapped_text(draw, artist_name.upper(), get_safe_font(90), w-tx-pad, w-pad, pad-10, "white")
            y_tit = draw_wrapped_text(draw, clean_name.upper(), get_safe_font(50), w-tx-pad, w-pad, y_art+15, "#e0e0e0")
            mid = (len(display_tracks) + 1) // 2
            f_tracks = get_safe_font(34)
            for i, t in enumerate(display_tracks[:mid]):
                draw.text((tx, y_tit+70+(i*45)), truncate_text(f"{i+1}. {t}", f_tracks, 500), font=f_tracks, fill="white")
            for i, t in enumerate(display_tracks[mid:]):
                draw.text((w-pad, y_tit+70+(i*45)), truncate_text(f"{t} .{mid+i+1}", f_tracks, 500), font=f_tracks, fill="white", anchor="ra")

        # Color bar logic
        bar_y, seg_w = h - pad + 5, (w - pad*2) // 4
        for i in range(4):
            color = cover_img.crop((i*(cover_img.width//4), 0, (i+1)*(cover_img.width//4), cover_img.height)).resize((1,1)).getpixel((0,0))
            draw.rectangle([pad+(i*seg_w), bar_y, pad+((i+1)*seg_w), bar_y+20], fill=color)

        return poster
    except: return None
