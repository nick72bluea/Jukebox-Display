import streamlit as st
import time
import random
import string

# --- OUR NEW MODULES ---
from weather_utils import draw_weather_dashboard
from poster_engine import create_poster, get_album_from_track
from cloud_utils import (
    get_current_song_from_cloud, log_manual_history, 
    init_pairing_code, check_pairing_status, 
    check_if_unpaired, unpair_from_cloud, check_subscription_status,
    get_display_layout 
)

# --- PAGE SETUP & KIOSK MODE CSS ---
st.set_page_config(page_title="SoundScreen TV", layout="wide", initial_sidebar_state="collapsed")

hide_st_style = """
            <style>
            /* KILL THE SCROLLBAR FOREVER */
            html, body {
                overflow: hidden !important; 
                width: 100vw !important; 
                height: 100vh !important;
                margin: 0 !important;
                padding: 0 !important;
            }

            /* HIDE ALL STREAMLIT MENUS AND HEADERS */
            [data-testid="stToolbar"] { display: none !important; }
            footer { display: none !important; }
            header[data-testid="stHeader"] { display: none !important; }
            [data-testid="collapsedControl"] { display: none !important; } 

            .stApp, .main { background-color: #000000 !important; }
            
            /* NUKE ALL STREAMLIT PADDING */
            .block-container {
                padding: 0px !important;
                max-width: 100% !important;
                margin: 0px !important;
            }
            
            /* PIN IMAGE TO SCREEN CORNERS */
            [data-testid="stImage"] {
                position: fixed !important;
                top: 0px !important;
                left: 0px !important;
                width: 100vw !important;
                height: 100vh !important;
                display: flex;
                justify-content: center;
                align-items: center;
                background-color: #000000 !important;
                z-index: 1 !important;
            }
            [data-testid="stImage"] img {
                object-fit: contain !important; 
                width: 100% !important;
                height: 100% !important;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS ---
def get_saved_venue(): return st.query_params.get("venue_id", None)
def get_saved_display(): return st.query_params.get("display_id", None)
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
if 'last_orientation' not in st.session_state: st.session_state.last_orientation = "Landscape"

# ==========================================
# --- CORE APP LOGIC (ROUTING) ---
# ==========================================
current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    # --- PAIRING SCREEN ---
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        init_pairing_code(st.session_state.pair_code, st.session_state.temp_display_id)

    code = st.session_state.pair_code
    formatted_code = f"{code[:3]} {code[3:]}"
    
    st.markdown("""
        <div style='text-align: center; margin-top: 12vh;'>
            <h1 style='color: #FFFFFF; font-size: 3.5rem; font-weight: 900; letter-spacing: 2px; margin-bottom: 0px;'>SOUND<span style='color: #7C3AED;'>SCREEN</span></h1>
            <p style='color: #888888; font-size: 1rem; font-weight: 800; letter-spacing: 4px; margin-top: -15px;'>THE LIVE MUSIC POSTER</p>
            <h3 style='color: #7C3AED; margin-top: 8vh; font-family: sans-serif; letter-spacing: 4px; font-size: 1.2rem;'>LINK YOUR DISPLAY</h3>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"<h1 style='text-align: center; font-size: 9rem; color: white; margin-top: -30px; font-weight: bold; letter-spacing: 8px;'>{formatted_code}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray; font-size: 1.5rem;'>Enter this code in the SoundScreen control app.</p>", unsafe_allow_html=True)
    
    time.sleep(2)
    linked_venue = check_pairing_status(code)
    if linked_venue:
        save_connection(linked_venue, st.session_state.temp_display_id)
        st.rerun() 
        
    st.rerun() 

else:
    # 🛑 THE SUBSCRIPTION CHECK 🛑
    is_pro = check_subscription_status(current_venue_id)
    
    if not is_pro:
        st.markdown("""
            <div style='display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; background-color: #000; color: #FFF; font-family: sans-serif; text-align: center; padding: 50px;'>
                <h1 style='font-size: 4rem; margin-bottom: 20px; font-weight: 900;'><span style='color: #FFF;'>SOUND</span><span style='color: #7C3AED;'>SCREEN</span></h1>
                <div style='background-color: #111; padding: 40px; border-radius: 20px; border: 2px solid #7C3AED; max-width: 800px;'>
                    <h2 style='font-size: 2.5rem; margin-bottom: 20px;'>Display Inactive 📺</h2>
                    <p style='font-size: 1.5rem; color: #AAA; line-height: 1.5;'>This venue's SoundScreen Pro subscription has ended.</p>
                    <p style='font-size: 1.5rem; color: #AAA; line-height: 1.5; margin-top: 10px;'>Please open the control app on your phone and renew your subscription to reactivate this display.</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        time.sleep(10)
        st.rerun()

    else:
        # ✅ DUMB GLASS MODE ✅
        weather_city = "London"
        # ⚡️ TEMPORARILY DROPPED TO 1 MINUTE FOR TESTING ⚡️
        idle_timeout_mins = 1

        if st.session_state.is_standby:
            draw_weather_dashboard(weather_city, st.session_state.last_orientation)
        elif st.session_state.current_poster:
            st.image(st.session_state.current_poster.convert('RGB'), use_container_width=True, output_format="JPEG")
        else:
            st.markdown(f"<h3 style='color:gray;text-align:center;margin-top:200px;'>Listening to Venue Cloud...<br><span style='font-size:12px;opacity:0.5;'>Venue: {current_venue_id}<br>Display: {current_display_id}</span></h3>", unsafe_allow_html=True)

        @st.fragment(run_every=1)
        def background_listener():
            needs_rerun = False
            
            if check_if_unpaired(current_venue_id, current_display_id):
                clear_connection()
                st.rerun()

            if not check_subscription_status(current_venue_id):
                st.rerun()

            current_layout = get_display_layout(current_venue_id, current_display_id)
            if current_layout not in ["Landscape", "Portrait", "Portrait (Sideways TV)"]:
                current_layout = "Landscape"

            track_found, artist_found = get_current_song_from_cloud(current_venue_id)
            
            if track_found and artist_found:
                
                # Check if the song or layout changed
                song_changed = (track_found != st.session_state.last_track)
                layout_changed = (current_layout != st.session_state.last_orientation)
                
                # ⚡️ THE BUG FIX: Only reset the timer if a completely NEW song plays ⚡️
                if song_changed:
                    st.session_state.last_heard_time = time.time()
                
                if song_changed or layout_changed:
                    if layout_changed:
                        st.toast(f"Cloud Sync: Screen is now {current_layout} 📲", icon="🔄")
                        st.cache_data.clear() 

                    album_found = get_album_from_track(track_found, artist_found)
                    if album_found:
                        new_poster = create_poster(album_found, artist_found, current_layout)
                        
                        if new_poster:
                            st.session_state.current_poster = new_poster
                            st.session_state.last_track = track_found
                            st.session_state.last_orientation = current_layout
                            st.session_state.is_standby = False
                                
                    needs_rerun = True

            time_since_last_song = time.time() - st.session_state.last_heard_time
            if time_since_last_song > (idle_timeout_mins * 60):
                if not st.session_state.is_standby:
                    st.session_state.is_standby = True
                    st.session_state.current_poster = None
                    # We NO LONGER clear last_track here, so it remembers the old song and won't re-trigger it
                    needs_rerun = True
                    
            if needs_rerun:
                st.rerun()
                
        background_listener()
