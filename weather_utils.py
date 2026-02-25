import streamlit as st
import requests
from datetime import datetime

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_res = requests.get(geo_url, timeout=5).json()
        if not geo_res.get('results'): return None
        lat, lon, res_name = geo_res['results'][0]['latitude'], geo_res['results'][0]['longitude'], geo_res['results'][0]['name']
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        w_data = requests.get(w_url, timeout=5).json()
        return {"temp": w_data['current']['temperature_2m'], "emoji": "☀️", "name": res_name}
    except: return None

def draw_weather_dashboard(city):
    w = get_weather(city)
    now_t = datetime.now().strftime("%H:%M")
    now_d = datetime.now().strftime("%A, %B %d")
    html = f"<div style='text-align: center; padding: 150px; color: white; background: black; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem; margin: 0;'>{now_t}</h1><p style='font-size: 2rem; opacity: 0.6;'>{now_d}</p>"
    if w: html += f"<h2 style='font-size: 6rem;'>{w['emoji']} {w['temp']}°C in {w['name']}</h2>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
