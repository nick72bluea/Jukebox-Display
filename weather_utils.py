import streamlit as st
import requests
from datetime import datetime

# --- FREE & FAST WEATHER CACHE ---
# We cache this for 30 mins so we don't spam the weather API and slow down the TV
@st.cache_data(ttl=1800, show_spinner=False) 
def get_weather(city):
    try:
        # Using wttr.in as it is a highly reliable, free, keyless API
        res = requests.get(f"https://wttr.in/{city}?format=j1", timeout=3)
        data = res.json()
        temp = data['current_condition'][0]['temp_C']
        desc = data['current_condition'][0]['weatherDesc'][0]['value']
        
        # Smart Emoji Mapper
        desc_lower = desc.lower()
        if "sun" in desc_lower or "clear" in desc_lower: icon = "☀️"
        elif "rain" in desc_lower or "drizzle" in desc_lower or "shower" in desc_lower: icon = "🌧️"
        elif "cloud" in desc_lower or "overcast" in desc_lower: icon = "☁️"
        elif "snow" in desc_lower or "ice" in desc_lower: icon = "❄️"
        elif "thunder" in desc_lower or "storm" in desc_lower: icon = "⛈️"
        else: icon = "🌡️"
        
        return f"{temp}°C", desc, icon
    except Exception:
        return "--°C", "Weather Unavailable", "☁️"


def draw_weather_dashboard(city="London", layout="Landscape"):
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%A, %B %d").upper()
    
    temp, desc, icon = get_weather(city)
    
    # --- SMART ROTATION CSS ---
    if layout == "Portrait (Sideways TV)":
        # ⚡️ FIXED: Flipped to -90deg so it rotates the correct way for your TV mount! ⚡️
        wrapper_style = "position: fixed; top: 50%; left: 50%; width: 100vh; height: 100vw; transform: translate(-50%, -50%) rotate(-90deg); display: flex; flex-direction: column; justify-content: center; align-items: center; background-color: #000000; color: white; font-family: sans-serif; z-index: 10;"
        time_size, date_size, icon_size, temp_size, meta_size, brand_size = "18vw", "3vw", "6vw", "5vw", "1.5vw", "3vw"
    
    elif layout == "Portrait": # Native tablet/smart display
        wrapper_style = "position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; background-color: #000000; color: white; font-family: sans-serif; z-index: 10;"
        time_size, date_size, icon_size, temp_size, meta_size, brand_size = "18vw", "3vw", "6vw", "5vw", "1.5vw", "3vw"
        
    else: # Standard Landscape
        wrapper_style = "position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; background-color: #000000; color: white; font-family: sans-serif; z-index: 10;"
        time_size, date_size, icon_size, temp_size, meta_size, brand_size = "12vw", "2vw", "4vw", "3vw", "1vw", "2vw"

    # --- HTML INJECTION ---
    # ZERO indentation allowed here to prevent Streamlit from creating code blocks
    html = f"""<div style="{wrapper_style}">
<div style="font-size: {time_size}; font-weight: 900; letter-spacing: -2px; margin-bottom: -2vh; line-height: 1;">{time_str}</div>
<div style="font-size: {date_size}; color: #888888; letter-spacing: 4px; font-weight: 700; margin-bottom: 8vh;">{date_str}</div>
<div style="display: flex; align-items: center; gap: 2vw; background-color: #0A0A0A; padding: 3vh 4vw; border-radius: 2vw; border: 2px solid #1A1A1A;">
<div style="font-size: {icon_size};">{icon}</div>
<div>
<div style="font-size: {temp_size}; font-weight: bold; line-height: 1;">{temp}</div>
<div style="font-size: {meta_size}; color: #666666; text-transform: uppercase; letter-spacing: 2px; margin-top: 0.5vh;">{city} • {desc}</div>
</div>
</div>
<div style="position: absolute; bottom: 8vh; text-align: center;">
<div style="font-size: {brand_size}; font-weight: 900; letter-spacing: 3px;">SOUND<span style="color: #7C3AED;">SCREEN</span></div>
<div style="font-size: {meta_size}; color: #444444; letter-spacing: 4px; margin-top: 1vh; font-weight: 800;">LISTENING FOR MUSIC...</div>
</div>
</div>"""

    st.markdown(html, unsafe_allow_html=True)
