import sys
import os

# Ensure the app can see local modules in the current directory
sys.path.append(os.path.dirname(__file__))

import streamlit as st
import time, random, string
from cloud_utils import init_firebase, get_current_song, get_secret, log_manual_history
from poster_engine import create_poster, get_album_from_track
from weather_utils import draw_weather_dashboard
from firebase_admin import db

# 1. SETUP & INIT (Must be the very first Streamlit command)
st.set_page_config(page_title="Jukebox Funk TV", layout="wide")

# Hide Streamlit UI elements
st.markdown("""
    <style>
    [data-testid='stToolbar'], footer {display: none !important;}
    [data-testid="stHeader"] {background: transparent !important;}
    </style>
""", unsafe_allow_html=True)

# Initialize Firebase and STOP if it fails
if not init_firebase():
    st.warning("📡 Awaiting Firebase connection... Please check your Streamlit Secrets.")
    st.stop()

# Get Spotify Credentials
CID = get_secret("SPOTIPY_CLIENT_ID")
SEC = get_secret("SPOTIPY_CLIENT_SECRET")

# 2. ROUTING DATA
v_id = st.query_params.get("venue_id")
d_id = st.query_params.get("display_id")

# 3. APP LOGIC
if not v_id:
    # --- ONBOARDING ROOM ---
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=8))
        try:
            db.reference(f"pairing_codes/{st.session_state.pair_code}").set({
                "status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()
            })
        except Exception as e:
            st.error(f"Database Error: {e}")
    
    st.markdown(f"<h1 style='text-align:center; font-size:10rem; margin-top:20vh;'>{st.session_state.pair_code}</h1>", unsafe_allow_html=True)
    
    res = db.reference(f"pairing_codes/{st.session_state.pair_code}").get()
    if res and res.get("status") == "linked":
        st.query_params["venue_id"] = res["venue_id"]
        st.query_params["display_id"] = st.session_state.temp_id
        db.reference(f"pairing_codes/{st.session_state.pair_code}").delete()
        st.rerun()
    time.sleep(2)
    st.rerun()

else:
    # --- PAIRED STATE ---
    if 'current_poster' not in st.session_state: st.session_state.current_poster = None
    if 'last_track' not in st.session_state: st.session_state.last_track = None
    if 'is_standby' not in st.session_state: st.session_state.is_standby = False
    if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()

    # --- SIDEBAR UI ---
    st.sidebar.markdown("## ⚙️ TV Settings")
    orient = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    weather_city = st.sidebar.text_input("Weather City", "London")
    idle_mins = st.sidebar.slider("Standby Timeout (Mins)", 1, 15, 5)
    
    st.sidebar.markdown("---")
    live_mode = st.sidebar.toggle("📺 CONNECT TO CLOUD REMOTE", value=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎸 Manual Search")
    m_art = st.sidebar.text_input("Artist", "Oasis")
    m_alb = st.sidebar.text_input("Album", "Definitely Maybe")
    
    if st.sidebar.button("Generate Layout", type="primary"):
        img = create_poster(m_alb, m_art, orient, CID, SEC)
        if img:
            st.session_state.current_poster = img
            st.session_state.is_standby = False
            log_manual_history(v_id, m_alb, m_art)

    st.sidebar.markdown("---")
    if st.sidebar.button("Unpair Display", type="secondary"):
        db.reference(f"venues/{v_id}/displays/{d_id}").delete()
        st.query_params.clear()
        st.rerun()

    # --- BACKGROUND SYNC (The Fragment) ---
    @st.fragment(run_every=3)
    def sync_listener():
        # Check for remote unpairing
        check = db.reference(f"venues/{v_id}/displays/{d_id}").get()
        if check is None:
            st.query_params.clear()
            st.rerun()
            
        if live_mode:
            t, a = get_current_song(v_id)
            if t:
                st.session_state.last_heard_time = time.time()
                if t != st.session_state.last_track:
                    st.session_state.last_track = t
                    st.session_state.is_standby = False
                    alb = get_album_from_track(t, a, CID, SEC) or t
                    img = create_poster(alb, a, orient, CID, SEC)
                    if img:
                        st.session_state.current_poster = img
                        st.rerun()
            
            # Standby logic
            if (time.time() - st.session_state.last_heard_time) > (idle_mins * 60):
                if not st.session_state.is_standby:
                    st.session_state.is_standby = True
                    st.rerun()

    sync_listener()

    # --- MAIN STAGE RENDERING ---
    if st.session_state.is_standby:
        draw_weather_dashboard(weather_city)
    elif st.session_state.current_poster:
        st.image(st.session_state.current_poster, use_container_width=True)
    else:
        st.markdown("<h3 style='color:gray;text-align:center;margin-top:20vh;'>Waiting for music...</h3>", unsafe_allow_html=True)
