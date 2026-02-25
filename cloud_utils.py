import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import os
import time
from datetime import datetime

def get_secret(key, default=None):
    if key in os.environ:
        return os.environ.get(key)
    try:
        return st.secrets[key]
    except Exception:
        return default

def init_firebase():
    if firebase_admin._apps:
        return True
    
    # HARDCODED TEST - Paste your key exactly as it appears in the JSON
    test_key = """-----BEGIN PRIVATE KEY-----
\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC/9lBnwRqZrU1P\ncLK2CMyxIOuIIpzz1YLtyi7t3yJTPXAXylwkQP9sr6Qwfd4AxY+5BzoQw5QX+jdC\nceTYnQn28U0kI05uuVEl3e5GLnWM8cVh7E0YQB50yOSK81yzU25h/yZOoQJuFd8z\n/n5w4LJhUSa3FxXsx4Tf3tHhPGtSiXRd6OPScSomN/UXSZeGb2dbXFwtLjtPyUhY\nXCHc8gmyQEkJ2SzplnzgniWW4MrimhJ5MZ7zU6uzZFgc4lRLkRL4k/jMJZVo/kaA\nLI5Lv/9m+8al8x5ZAhJLQqZnmr5G2ia8HMWhK5OBowaY9wvsDSSshcixlqsQ3J2t\n7HQlqafrAgMBAAECggEAV8u6HpoNJnhCwbCTq/n+VIzv7IWYL1VZ2pP8PsMtGdEh\nsV/WIKaxq+3xNFR88vFouIF7pyssUoMYPwWEWyYH5q+aTorvVmjfmmgUkHizPtFd\nK1o+MHcy9sri7EI+Ba6E78EYriGp0NukCE2/WrUKIMRS5q5iUrc2KIXqjA9sLoTw\nrM4LtWdgO5cmDSmB8Dh+WDbeE0JVCCZ8IG+OBvAU0ZHrD9QU+v7rIznE1XxorG3W\nhOZ6ZBz8TR/+kdYpFB39cFx4gsvSr091QQspSbYPJU/0NVc0BTZxNtF25s+4KVSE\nz8DoPGLqczwQgXU+c6VgzQcvlhOtTU/+io6lpuwXYQKBgQDhBOrfx1NSNnohs21w\neHTixyTAffewGrqz/GWbcuYmE9rEiZGzhTWhXW6ufWr5vABk/XXntTuKOpdMiWoP\nhUvf+f3Ia+n+KIATBnnrS97o8AW4tq5/bT3vg5i92MeMD94ZCNWbbXcFVa5e/xTK\n0OqD3IJQOCzpylFvhCxUGTNYSQKBgQDaZEKGcrTYyEWBxawXzZymfymZTxv2aAyc\n4AFm6WwK9djugsfIhXdNJ3v9Xb3HpXXDqnWrtR+OwhhTbBLdf1+CKgIwCmDiVReN\nvyXDU8n8fTh9BX7+XmD9yaxr+vrD/wUWoa+82jkD2Dwo8jJ4PMUnkJcVW1bEBGkE\nxR0HjrpGkwKBgQDA9f6UN9HzxlOlYsCOmj1h23RgvaURl1pTzjUzwKwsKwqHT5Fq\naOk8n2qyp0p9LgMIl3HsaTXNq8DjGVOiS6RtRWuj2yallQV/SyZx6HYXOv0tETtC\neuOJ6UeqRaOZMGI9BZ5n0s8l+/uz6vphkhYJTadSM1oQgjajcqyw0Yt+QQKBgEM7\nun9JsQNMJJnfESwC0McxPs1D3YfuYHOrQsM7+VcmeLJ08Kx66k+GaFWIFnTwK2Eh\niThjemOovXRxQR2PqQeZhzLi/xCuwaGRxz5q/TQOGOXkW0RUKef3vm0/xxOv3xEo\nlcG+LO9SErNIXOFHVCrqCJk6lWujL/GX/WfmONKhAoGBAIEl1xF2HGmqtiHbbQTt\nuwHGPb0f9mJL+rv+KWQZDwHoEHsmPVqLFzqR1uNsm4X1AgOYSMHxLp6U4c5kNmrk\n2mZpzSiSVP8H3wJKll+lIhzEfcMWLz9AcFJNBPAzfOTHQGgVCu/MXKk2fNQkBmwU\niFtfrfnZaA44qXNHhBa3CorQ\n
-----END PRIVATE KEY-----"""

    cert_dict = {
        "type": "service_account",
        "project_id": "posterjukebox",
        "private_key_id": "5dfa6f9688d66a95835e469005de46d325ab5615",
        "private_key": test_key,
        "client_email": "firebase-adminsdk-fbsvc@posterjukebox.iam.gserviceaccount.com",
        "client_id": "102973933404996152824",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40posterjukebox.iam.gserviceaccount.com"
    }
    
    db_url = "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app"

    try:
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        return True
    except Exception as e:
        st.error(f"HARDCODE TEST FAILED: {e}")
        return False


def get_current_song(venue_id):
    try:
        ref = db.reference(f"venues/{venue_id}/now_playing")
        data = ref.get()
        if data:
            return data.get('track'), data.get('artist')
    except:
        pass
    return None, None

def log_manual_history(venue_id, album, artist):
    try:
        record_id = str(int(time.time() * 1000))
        db.reference(f"venues/{venue_id}/history/{record_id}").set({
            "id": record_id, "track": album, "artist": artist,
            "time": datetime.now().strftime("%H:%M"), "type": "manual"
        })
    except:
        pass
