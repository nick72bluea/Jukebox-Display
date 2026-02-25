import streamlit as st
import time, random, string
import sys
import os

sys.path.append(os.path.dirname(__file__))

from cloud_utils import init_firebase, get_current_song, get_secret, log_manual_history
from poster_engine import create_poster, get_album_from_track
from weather_utils import draw_weather_dashboard
from firebase_admin import db

st.set_page_config(page_title="Jukebox TV", layout="wide")

st.markdown("""
<style>
[data-testid='stToolbar'], footer {display: none !important;}
[data-testid="stHeader"] {background: transparent !important;}
</style>
""", unsafe_allow_html=True)

if not init_firebase():
    st.warning("📡 Awaiting Firebase...")
    st.stop()

CID = get_secret("SPOTIPY_CLIENT_ID")
SEC = get_secret("SPOTIPY_CLIENT_SECRET")

v_id = st.query_params.get("venue_id")
d_id = st.query_params.get("display_id")

if not v_id:
    if 'pair_code' not in st.session_state:
        st.session_state.pair_code = ''.join(random.choices(string.digits, k=6))
        st.session_state.temp_id = 'disp_' + ''.join(random.choices(string.ascii_lowercase, k=8))
        db.reference(f"pairing_codes/{st.session_state.pair_code}").set({
            "status": "waiting", "display_id": st.session_state.temp_id, "timestamp": time.time()
        })
    
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
    if 'current_poster' not in st.session_state: st.session_state.current_poster = None
    if 'last_track' not in st.session_state: st.session_state.last_track = None
    if 'is_standby' not in st.session_state: st.session_state.is_standby = False
    if 'last_heard_time' not in st.session_state: st.session_state.last_heard_time = time.time()

    orient = st.sidebar.radio("Layout", ["Portrait", "Landscape"], index=1)
    weather_city = st.sidebar.text_input("Weather City", "London")
    idle_mins = st.sidebar.slider("Standby Timeout", 1, 15, 5)

    @st.fragment(run_every=3)
    def sync_listener():
        t, a = get_current_song(v_id)
        if t and t != st.session_state.last_track:
            st.session_state.last_track = t
            st.session_state.is_standby = False
            st.session_state.last_heard_time = time.time()
            alb = get_album_from_track(t, a, CID, SEC) or t
            img = create_poster(alb, a, orient, CID, SEC)
            if img:
                st.session_state.current_poster = img
                st.rerun()
    sync_listener()

    if st.session_state.current_poster:
        st.image(st.session_state.current_poster, use_container_width=True)
