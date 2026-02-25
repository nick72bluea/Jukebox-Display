import streamlit as st
import requests
from datetime import datetime

def get_weather(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&format=json"
        geo_data = requests.get(geo_url).json()
        if not geo_data.get('results'): return None
        lat, lon, resolved_name = geo_data['results'][0]['latitude'], geo_data['results'][0]['longitude'], geo_data['results'][0]['name']
        
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        weather_data = requests.get(weather_url).json()
        temp, code = weather_data['current']['temperature_2m'], weather_data['current']['weather_code']
        
        emoji, condition = "☀️", "Clear"
        if code in [1, 2, 3]: emoji, condition = "⛅️", "Partly Cloudy"
        elif code in [45, 48]: emoji, condition = "🌫️", "Fog"
        elif code in [51, 53, 55, 56, 57]: emoji, condition = "🌧️", "Drizzle"
        elif code in [61, 63, 65, 66, 67]: emoji, condition = "🌧️", "Rain"
        elif code in [71, 73, 75, 77]: emoji, condition = "❄️", "Snow"
        elif code in [80, 81, 82]: emoji, condition = "🌦️", "Showers"
        elif code in [95, 96, 99]: emoji, condition = "⛈️", "Thunderstorm"
        
        return {"temp": temp, "emoji": emoji, "condition": condition, "name": resolved_name}
    except Exception: return None

def draw_weather_dashboard(city):
    weather = get_weather(city)
    current_time = datetime.now().strftime("%H:%M")
    current_date = datetime.now().strftime("%A, %B %d")
    html = f"<div style='text-align: center; padding: 150px 20px; font-family: \"Helvetica Neue\", Helvetica, Arial, sans-serif; color: white; background: #000000; height: 100vh;'>"
    html += f"<h1 style='font-size: 10rem; margin: 0; font-weight: 200; letter-spacing: -5px;'>{current_time}</h1>"
    html += f"<p style='font-size: 2rem; margin: 0 0 60px 0; font-weight: 300; opacity: 0.6;'>{current_date}</p>"
    if weather:
        html += f"<div style='display: inline-block; background: rgba(255,255,255,0.05); padding: 40px 60px; border-radius: 30px;'>"
        html += f"<h2 style='font-size: 6rem; margin: 0;'>{weather['emoji']} {weather['temp']}°C</h2>"
        html += f"<p style='font-size: 1.8rem; margin: 15px 0 0 0; font-weight: 300; opacity: 0.8;'>{weather['condition']} in {weather['name']}</p></div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
