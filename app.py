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
    check_if_unpaired, unpair_from_cloud
)

# --- PAGE SETUP & KIOSK MODE CSS ---
st.set_page_config(page_title="SoundScreen TV", layout="wide", initial_sidebar_state="collapsed")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header[data-testid="stHeader"] { background: rgba(0,0,0,0) !important; }
            .stApp { background-color: #000000; }
            [data-testid="stImage"] { display: flex; justify-content: center; align-items: center; }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CLOUD PERSISTENCE HELPERS (URL PARAMETERS) ---
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

# ==========================================
# --- CORE APP LOGIC (ROUTING) ---
# ==========================================
current_venue_id = get_saved_venue()
current_display_id = get_saved_display()

if not current_venue_id or not current_display_id:
    # Hide sidebar during pairing
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_display_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        init_pairing_code(st.session_state.pair_code, st.session_state.temp_display_id)

    code = st.session_state.pair_code
    formatted_code = f"{code[:3]} {code[3:]}"
    
    st.markdown(f"<h3 style='text-align: center; color: #7C3AED; margin-top: 15vh; font-family: sans-serif; letter-spacing: 4px;'>LINK YOUR DISPLAY</h3>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center; font-size: 8rem; color: white; margin-top: -20px;'>{formatted_code}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray; font-size: 1.5rem;'>Enter this code in the Jukebox Funk app.</p>", unsafe_allow_html=True)
    
    time.sleep(2)
    linked_venue = check_pairing_status(code)
    if linked_venue:
        save_connection(linked_venue, st.session_state.temp_display_id)
        st.rerun() 
        
    st.rerun() 

else:
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
            if current_venue_id:
                log_manual_history(current_venue_id, st.session_state.manual_album, st.session_state.manual_artist)

    st.sidebar.button("Generate Layout", type="primary", on_click=generate_manual_poster)
    
    st.sidebar.markdown("---")
    def unpair_display():
        unpair_from_cloud(current_venue_id, current_display_id)
        clear_connection()
        if 'pair_code' in st.session_state: del st.session_state.pair_code
        st.session_state.current_poster = None
        st.session_state.last_track = None
        
    st.sidebar.button("Unpair Display", type="secondary", on_click=unpair_display, use_container_width=True)

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
            
            if check_if_unpaired(current_venue_id, current_display_id):
                clear_connection()
                st.toast("Unpaired from Remote App.", icon="🔌")
                st.rerun()

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
