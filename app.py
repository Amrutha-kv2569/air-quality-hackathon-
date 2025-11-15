import streamlit as st
import pandas as pd
import numpy as np
import requests
import pydeck as pdk
import plotly.express as px
from datetime import datetime, timedelta
# Assuming krigging.py is available in the same directory
from krigging import perform_kriging_correct
import geopandas as gpd
from shapely.geometry import Point, Polygon
import pyproj
from shapely.ops import transform


# --- Utility Functions (Geolocation and SMS77 kept as provided) ---

def get_user_geolocation():
    """
    Gets user location using browser geolocation.
    On the first run, JS runs and asks for location.
    On reload, lat/lon appear in query params.
    """
    query = st.experimental_get_query_params()

    if "lat" in query and "lon" in query:
        try:
            lat = float(query["lat"][0])
            lon = float(query["lon"][0])
            return lat, lon
        except:
            return None

    # Ask browser for location (JavaScript)
    st.markdown("""
        <script>
        // Use a function to ensure this is run only once if needed
        function getLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (pos) => {
                        const lat = pos.coords.latitude;
                        const lon = pos.coords.longitude;
                        const params = new URLSearchParams(window.location.search);
                        params.set("lat", lat);
                        params.set("lon", lon);
                        window.location.search = params.toString();
                    },
                    (err) => {
                        console.log("Geolocation blocked:", err);
                    }
                );
            }
        }
        getLocation();
        </script>
    """, unsafe_allow_html=True)

    return None

# Placeholder API Key (Replace this with your real key)
SMS77_API_KEY = "YOUR_SMS77_API_KEY"

def send_sms_sms77(phone, text):
    """Sends SMS using SMS77.io API."""
    url = "https://gateway.sms77.io/api/sms"

    payload = {
        "to": phone,
        "text": text,
        "from": "AQIAlert",
        "json": "1"
    }

    headers = {
        # NOTE: API key is currently hardcoded and exposed here. 
        # In production, use environment variables (st.secrets) or a secure backend.
        "X-Api-Key": "ce9196b9famsh41c38d8b9917c08p11f8e0jsnd367c1038fa7" 
    }

    try:
        r = requests.post(url, data=payload, headers=headers)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def get_aqi_from_kriging_point(user_lon, user_lat, lon_grid, lat_grid, z_grid):
    """
    Returns interpolated AQI from the kriging grid at the user's exact location
    by finding the nearest grid point.
    """
    dist = (lon_grid - user_lon)**2 + (lat_grid - user_lat)**2
    idx = np.unravel_index(np.argmin(dist), dist.shape)

    value = z_grid[idx]
    if np.isnan(value):
        return None
    return float(value)


# ==========================
# PAGE CONFIGURATION
# ==========================
st.set_page_config(
    layout="wide",
    page_title="Delhi Air Quality Dashboard",
    page_icon="💨"
)

# ==========================
# STATIC CONFIG
# ==========================
API_TOKEN = "97a0e712f47007556b57ab4b14843e72b416c0f9"
DELHI_BOUNDS = "28.404,76.840,28.883,77.349"
DELHI_LAT = 28.6139
DELHI_LON = 77.2090

DELHI_GEOJSON_URL = "https://raw.githubusercontent.com/shuklaneerajdev/IndiaStateTopojsonFiles/master/Delhi.geojson"

# Twilio Configuration (kept for legacy/error messages)
TWILIO_ACCOUNT_SID = "AC2cc57109fc63de336609901187eca69d"
TWILIO_AUTH_TOKEN = "62b791789bb490f91879e89fa2ed959d"
TWILIO_PHONE_NUMBER = "+13856005348"

# **COLORS BASED ON "TOPIC" TEMPLATE**
TOPIC_TEAL_LIGHT = "#63B4B8"
TOPIC_BLUE_DARK = "#286D87"
TOPIC_ACCENT_GREEN = "#5DC3A5"
TOPIC_GRADIENT_START = "#63B4B8"
TOPIC_GRADIENT_END = "#36768D"
TOPIC_CARD_TEXT = "#1A1A1A"


# ==========================
# CUSTOM CSS FOR STYLING (TOPIC GRADIENT THEME)
# ==========================
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    
    html, body, [class*="st-"] {{
        font-family: 'Inter', sans-serif;
    }}

    /* Main background - Teal/Blue Gradient (Matches image) */
    .stApp {{
        background: linear-gradient(135deg, {TOPIC_GRADIENT_START} 0%, {TOPIC_GRADIENT_END} 100%);
    }}

    /* Hide Streamlit's default header and footer */
    header, footer, #MainMenu {{
        visibility: hidden;
    }}
    
    /* Main title styling */
    .main-title {{
        font-size: 3.5rem;
        font-weight: 900;
        color: white; 
        padding: 1.5rem 0 0.5rem 0;
        text-align: center;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.3);
        letter-spacing: -1px;
    }}

    /* Subtitle styling */
    .subtitle {{
        font-size: 1.2rem;
        color: #E0FFFF; /* Light contrast on gradient */
        text-align: center;
        padding-bottom: 1.5rem;
        font-weight: 500;
    }}

    /* Metric cards styling (White cards with large rounding) */
    .metric-card {{
        background-color: #FFFFFF;
        border-radius: 20px; 
        padding: 1.5rem;
        border: 1px solid #E0E0E0;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        text-align: center;
        height: 100%;
    }}
    .metric-card-label {{
        font-size: 1rem;
        font-weight: 600;
        color: {TOPIC_BLUE_DARK};
        margin-bottom: 0.5rem;
    }}
    .metric-card-value {{
        font-size: 2.5rem;
        font-weight: 900;
        color: {TOPIC_ACCENT_GREEN}; 
        margin: 0.5rem 0;
    }}
    .metric-card-delta {{
        font-size: 0.9rem;
        color: {TOPIC_CARD_TEXT};
        font-weight: 500;
    }}

    /* Weather widget styling */
    .weather-widget {{
        background-color: #FFFFFF;
        border-radius: 20px; 
        padding: 1.5rem;
        border: 1px solid #E0E0E0;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        height: 100%;
    }}
    .weather-temp {{
        font-size: 2.5rem;
        font-weight: 900;
        color: {TOPIC_BLUE_DARK};
    }}

    /* Styling for Streamlit tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0.75rem;
        background-color: transparent;
        padding: 1rem 0;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        font-size: 1rem;
        font-weight: 600;
        background-color: white;
        border-radius: 10px; 
        padding: 0.75rem 1.5rem;
        border: 1px solid {TOPIC_TEAL_LIGHT};
        color: {TOPIC_BLUE_DARK};
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }}
    
    .stTabs [data-baseweb="tab"]:hover {{
        background-color: #F0F8FF;
        border-color: {TOPIC_ACCENT_GREEN};
    }}
    
    .stTabs [aria-selected="true"] {{
        background-color: {TOPIC_ACCENT_GREEN}; 
        color: white !important;
        border-color: {TOPIC_ACCENT_GREEN};
    }}

    /* General card for content (Main dashboard sections) */
    .content-card {{
        background-color: #FFFFFF;
        padding: 2.5rem;
        border-radius: 25px; 
        border: 1px solid #E0E0E0;
        box-shadow: 0 15px 35px rgba(0, 0, 0, 0.15);
        margin-top: 1.5rem;
    }}

    /* Section headers */
    .section-header {{
        font-size: 1.6rem;
        font-weight: 800;
        color: {TOPIC_BLUE_DARK};
        margin-bottom: 1.5rem;
        padding-bottom: 0.5rem;
        border-bottom: 3px solid {TOPIC_TEAL_LIGHT};
    }}

    /* Primary buttons (Search button style) */
    .stButton > button {{
        background-color: {TOPIC_ACCENT_GREEN};
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.6rem 1.2rem;
        font-weight: 700;
        box-shadow: 0 4px 10px rgba(93, 195, 165, 0.4);
        transition: background-color 0.2s;
    }}
    .stButton > button:hover {{
        background-color: #4CAF92;
    }}
    
    /* Info box styling */
    div[data-testid="stAlert"] {{
        background-color: white;
        border-left: 5px solid {TOPIC_TEAL_LIGHT};
        border-radius: 10px;
        color: {TOPIC_BLUE_DARK};
    }}
    
    /* --- ALERT CARD STYLES (MATCHING THE RED/ORANGE IMAGE FORMAT) --- */
    .alert-card {{
        padding: 1rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 0.75rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        color: white;
        font-weight: 600;
        transition: transform 0.1s;
    }}
    .alert-card:hover {{
        transform: translateY(-2px);
    }}

    /* Hazardous (Red) */
    .alert-hazardous {{
        background: linear-gradient(90deg, #E53935 0%, #C62828 100%); /* Deep Red Gradient */
        box-shadow: 0 4px 12px rgba(198, 40, 40, 0.4);
    }}

    /* Very Unhealthy (Dark Orange/Purple) */
    .alert-very-unhealthy {{
        background: linear-gradient(90deg, #F57C00 0%, #D84315 100%); /* Orange Gradient */
        box-shadow: 0 4px 12px rgba(245, 124, 0, 0.4);
    }}

    /* Unhealthy (Light Orange/Amber) */
    .alert-unhealthy {{
        background: linear-gradient(90deg, #FFA000 0%, #FF8F00 100%); /* Amber Gradient */
        box-shadow: 0 4px 12px rgba(255, 152, 0, 0.4);
    }}
    /* --- END ALERT CARD STYLES --- */

    /* Success/Warning/Error boxes */
    div[data-testid="stSuccess"], div[data-testid="stWarning"], div[data-testid="stError"] {{
        background-color: white;
        color: {TOPIC_CARD_TEXT};
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }}
    div[data-testid="stSuccess"] {{ border-left: 5px solid #4CAF50; }}
    div[data-testid="stWarning"] {{ border-left: 5px solid #FFC107; }}
    div[data-testid="stError"] {{ border-left: 5px solid #E53935; }}


</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner="Loading Delhi boundary...")
def load_delhi_boundary_from_url():
    """
    Loads, caches the Delhi boundary GeoJSON (WGS84), and returns the UTM 
    transformed polygon for Kriging calculation.
    """
    try:
        # 1. Load GeoJSON, convert to WGS84
        gdf = gpd.read_file(DELHI_GEOJSON_URL)
        gdf = gdf.to_crs(epsg=4326)
        
        # 2. Combine all geometries into one single polygon (WGS84)
        delhi_polygon_wgs84 = gdf.unary_union
        
        # 3. Define UTM projection transformer (Delhi = UTM Zone 43N)
        project_to_utm = pyproj.Transformer.from_crs(
             "epsg:4326", "epsg:32643", always_xy=True
        ).transform
        
        # 4. Apply transformation to the polygon
        delhi_polygon_utm = transform(project_to_utm, delhi_polygon_wgs84)
        
        # Return the GeoDataFrame (for filtering) and the UTM Polygon (for Kriging)
        return gdf, delhi_polygon_utm
    except Exception:
        # Use an empty Polygon for robustness if GeoPandas fails
        return None, Polygon()

@st.cache_data(ttl=600, show_spinner="Fetching Air Quality Data...")
def fetch_live_data():
    """Fetches and processes live AQI data from the WAQI API."""
    url = f"https://api.waqi.info/map/bounds/?latlng={DELHI_BOUNDS}&token={API_TOKEN}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "ok":
            df = pd.DataFrame(data["data"])
            df = df[df['aqi'] != "-"]
            df['aqi'] = pd.to_numeric(df['aqi'], errors='coerce')
            df = df.dropna(subset=['aqi'])

            def safe_get_name(x):
                if isinstance(x, dict):
                    return x.get('name', 'N/A')
                elif isinstance(x, str):
                    return x
                else:
                    return 'N/A'

            def safe_get_time(x):
                if isinstance(x, dict):
                    time_data = x.get('time', {})
                    if isinstance(time_data, dict):
                        return time_data.get('s', 'N/A')
                    elif isinstance(time_data, str):
                        return time_data
                    else:
                        return 'N/A'
                else:
                    return 'N/A'

            df['station_name'] = df['station'].apply(safe_get_name)
            df['last_updated'] = df['station'].apply(safe_get_time)
            df[['category', 'color', 'emoji', 'advice']] = df['aqi'].apply(
                get_aqi_category).apply(pd.Series)
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
            df = df.dropna(subset=['lat', 'lon'])
            return df
        return pd.DataFrame()
    except requests.RequestException:
        return pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner="Fetching Weather Data...")
def fetch_weather_data():
    """Fetches current weather data from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={DELHI_LAT}&longitude={DELHI_LON}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=Asia/Kolkata"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def get_aqi_category(aqi):
    """Categorizes AQI value and provides color, emoji, and health advice."""
    if aqi <= 50:
        return "Good", [0, 158, 96], "✅", "Enjoy outdoor activities."
    elif aqi <= 100:
        return "Moderate", [255, 214, 0], "🟡", "Unusually sensitive people should consider reducing prolonged or heavy exertion."
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups", [249, 115, 22], "🟠", "Sensitive groups should reduce prolonged or heavy exertion."
    elif aqi <= 200:
        return "Unhealthy", [220, 38, 38], "🔴", "Everyone may begin to experience health effects."
    elif aqi <= 300:
        return "Very Unhealthy", [147, 51, 234], "🟣", "Health alert: everyone may experience more serious health effects."
    else:
        return "Hazardous", [126, 34, 206], "☠️", "Health warnings of emergency conditions. The entire population is more likely to be affected."

def render_kriging_tab(df):

    st.markdown('<div class="section-header">🔥 Kriging Heatmap (Interpolated)</div>',
                unsafe_allow_html=True) 

    delhi_bounds_tuple = (28.40, 28.88, 76.84, 77.35)

    # Note: We retrieve the UTM polygon for the Kriging calculation
    _, delhi_polygon_utm = load_delhi_boundary_from_url()

    if isinstance(delhi_polygon_utm, Polygon) and delhi_polygon_utm.area == 0:
         st.error("Kriging dependencies are missing or boundary loading failed. Ensure `geopandas`, `pyproj`, and `pykrige` are installed.", icon="⚠️")
         return
    
    if df.empty or df["aqi"].nunique() < 2 or len(df) < 4 or df[['lat','lon']].duplicated().any():
        st.error("Kriging cannot proceed due to insufficient, identical, or invalid station data (Need at least 4 unique points).")
        return

    with st.spinner("Performing spatial interpolation..."):
        # The krigging module handles UTM conversion internally for the grid calculation
        lon_grid, lat_grid, z = perform_kriging_correct(
            df,
            delhi_bounds_tuple,
            polygon=delhi_polygon_utm, 
            resolution=200
        )
        
    # ❗ SAVE THE RESULT FOR SMS TAB
    st.session_state["kriging_result"] = (lon_grid, lat_grid, z)
    st.success("Kriging analysis complete and result stored for point lookups!", icon="💾")


    # Create Heatmap
    heatmap_df = pd.DataFrame({
        "lon": lon_grid.flatten(),
        "lat": lat_grid.flatten(),
        "aqi": z.flatten()
    })
    
    heatmap_df = heatmap_df.dropna() # Remove NaNs introduced by polygon masking

    fig = px.density_mapbox(
        heatmap_df,
        lat="lat",
        lon="lon",
        z="aqi",
        radius=10,
        center=dict(lat=DELHI_LAT, lon=DELHI_LON),
        zoom=9,
        mapbox_style="carto-positron",
        color_continuous_scale=[
            "#009E60", "#FFD600", "#F97316",
            "#DC2626", "#9333EA", "#7E22CE"
        ]
    )

    fig.update_layout(
        title_text='Interpolated AQI Heatmap',
        title_font_color=TOPIC_CARD_TEXT,
        paper_bgcolor='white',
        plot_bgcolor='white',
        font_color=TOPIC_CARD_TEXT
    )
    st.plotly_chart(fig, use_container_width=True)


def get_weather_info(code):
    """Converts WMO weather code to a description and icon."""
    codes = {
        0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"),
        3: ("Overcast", "☁️"), 45: ("Fog", "🌫️"), 48: ("Depositing rime fog", "🌫️"),
        51: ("Light drizzle", "💧"), 53: ("Moderate drizzle", "💧"), 55: ("Dense drizzle", "💧"),
        61: ("Slight rain", "🌧️"), 63: ("Moderate rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
        80: ("Slight rain showers", "🌦️"), 81: ("Moderate rain showers", "🌦️"),
        82: ("Violent rain showers", "⛈️"), 95: ("Thunderstorm", "⚡"),
        96: ("Thunderstorm, slight hail", "⛈️"), 99: ("Thunderstorm, heavy hail", "⛈️")
    }
    return codes.get(code, ("Unknown", "❓"))


def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates using Haversine formula."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371  # Earth's radius in kilometers

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c

    return distance


def get_nearby_stations(df, user_lat, user_lon, radius_km=10):
    """Get stations within specified radius of user location."""
    df['distance'] = df.apply(
        lambda row: calculate_distance(
            user_lat, user_lon, row['lat'], row['lon']),
        axis=1
    )
    nearby = df[df['distance'] <= radius_km].sort_values('distance')
    return nearby


def render_header(df):
    """Renders the main header with summary metrics and weather."""
    st.markdown('<div class="main-title">🌍 Delhi Air Quality Dashboard</div>',
                unsafe_allow_html=True)
    last_update_time = df['last_updated'].max(
    ) if not df.empty and 'last_updated' in df.columns else "N/A"
    st.markdown(
        f'<p class="subtitle">Real-time monitoring • Last updated: {last_update_time}</p>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    if not df.empty:
        with c1:
            st.markdown(
                f'<div class="metric-card"><div class="metric-card-label">Average AQI</div><div class="metric-card-value">{df["aqi"].mean():.1f}</div><div class="metric-card-delta">{get_aqi_category(df["aqi"].mean())[0]}</div></div>', unsafe_allow_html=True)
        with c2:
            min_station = df.loc[df["aqi"].idxmin()]["station_name"]
            st.markdown(
                f'<div class="metric-card"><div class="metric-card-label">Minimum AQI</div><div class="metric-card-value">{df["aqi"].min():.0f}</div><div class="metric-card-delta">{min_station}</div></div>', unsafe_allow_html=True)
        with c3:
            max_station = df.loc[df["aqi"].idxmax()]["station_name"]
            st.markdown(
                f'<div class="metric-card"><div class="metric-card-label">Maximum AQI</div><div class="metric-card-value">{df["aqi"].max():.0f}</div><div class="metric-card-delta">{max_station}</div></div>', unsafe_allow_html=True)

    with c4:
        weather_data = fetch_weather_data()
        if weather_data and 'current' in weather_data:
            current = weather_data['current']
            desc, icon = get_weather_info(current.get('weather_code', 0))
            st.markdown(f"""
            <div class="weather-widget">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div>
                        <div class="metric-card-label">Current Weather</div>
                        <div class="weather-temp">{current['temperature_2m']:.1f}°C</div>
                    </div>
                    <div style="font-size: 3rem;">{icon}</div>
                </div>
                <div style="text-align: left; font-size: 0.9rem; color: {TOPIC_BLUE_DARK}; margin-top: 1rem; font-weight: 500;">
                    {desc}<br/>Humidity: {current['relative_humidity_2m']}%<br/>Wind: {current['wind_speed_10m']} km/h
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="weather-widget">
                <div class="metric-card-label">Current Weather</div>
                <div style="color: {TOPIC_BLUE_DARK}; margin-top: 1rem;">Weather data unavailable</div>
            </div>
            """, unsafe_allow_html=True)


def render_map_tab(df):
    """Renders the interactive map of AQI stations."""
    st.markdown('<div class="section-header">📍 Interactive Air Quality Map</div>',
                unsafe_allow_html=True)

    # Add Legend (Uses new colors for styling)
    st.markdown(f"""
    <div style="background-color: white; padding: 1rem; border-radius: 15px; border: 1px solid #E0E0E0; margin-bottom: 1rem;">
        <div style="font-weight: 700; color: {TOPIC_BLUE_DARK}; margin-bottom: 0.75rem; font-size: 1.1rem;">AQI Color Legend</div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <div style="width: 20px; height: 20px; border-radius: 50%; background-color: rgb(0, 158, 96);"></div>
                <span style="color: {TOPIC_CARD_TEXT}; font-weight: 500;">Good (0-50)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <div style="width: 20px; height: 20px; border-radius: 50%; background-color: rgb(255, 214, 0);"></div>
                <span style="color: {TOPIC_CARD_TEXT}; font-weight: 500;">Moderate (51-100)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <div style="width: 20px; height: 20px; border-radius: 50%; background-color: rgb(249, 115, 22);"></div>
                <span style="color: {TOPIC_CARD_TEXT}; font-weight: 500;">Unhealthy for Sensitive (101-150)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <div style="width: 20px; height: 20px; border-radius: 50%; background-color: rgb(220, 38, 38);"></div>
                <span style="color: {TOPIC_CARD_TEXT}; font-weight: 500;">Unhealthy (151-200)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <div style="width: 20px; height: 20px; border-radius: 50%; background-color: rgb(147, 51, 234);"></div>
                <span style="color: {TOPIC_CARD_TEXT}; font-weight: 500;">Very Unhealthy (201-300)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <div style="width: 20px; height: 20px; border-radius: 50%; background-color: rgb(126, 34, 206);"></div>
                <span style="color: {TOPIC_CARD_TEXT}; font-weight: 500;">Hazardous (300+)</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.pydeck_chart(pdk.Deck(
        map_style="light", 
        initial_view_state=pdk.ViewState(
            latitude=DELHI_LAT, longitude=DELHI_LON, zoom=9.5, pitch=50),
        layers=[pdk.Layer(
            "ScatterplotLayer",
            data=df, 
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius=250,
            pickable=True,
            opacity=0.8,
            stroked=True,
            get_line_color=[0, 0, 0, 100],
            line_width_min_pixels=1,
        )],
        tooltip={"html": "<b>{station_name}</b><br/>AQI: {aqi}<br/>Category: {category}<br/>Last Updated: {last_updated}",
                 "style": {"color": "white"}}
    ))


def render_alerts_tab(df):
    """Renders health alerts and advice based on current AQI levels."""
    st.markdown('<div class="section-header">🔔 Health Alerts & Recommendations</div>',
                unsafe_allow_html=True)
    
    max_aqi = df['aqi'].max()
    advice = get_aqi_category(max_aqi)[3]
    st.info(
        f"**Current Situation:** Based on the highest AQI of **{max_aqi:.0f}**, the recommended action is: **{advice}**", icon="ℹ️")

    # Define alert levels and their CSS classes
    alerts = {
        "Hazardous": (df[df['aqi'] > 300], "alert-hazardous"),
        "Very Unhealthy": (df[(df['aqi'] > 200) & (df['aqi'] <= 300)], "alert-very-unhealthy"),
        "Unhealthy": (df[(df['aqi'] > 150) & (df['aqi'] <= 200)], "alert-unhealthy")
    }
    
    has_alerts = False
    for level, (subset, card_class) in alerts.items():
        if not subset.empty:
            has_alerts = True
            # Use the emoji of the first (highest AQI) station in the subset
            emoji = subset.iloc[0]['emoji']
            
            st.markdown(f"**{emoji} {level} Conditions Detected**")
            
            # Render each station using the custom HTML/CSS alert-card
            for _, row in subset.sort_values('aqi', ascending=False).iterrows():
                st.markdown(
                    f'<div class="alert-card {card_class}"><span style="font-weight: 600;">{row["station_name"]}</span> <span style="font-weight: 700; font-size: 1.2rem;">AQI {row["aqi"]:.0f}</span></div>', 
                    unsafe_allow_html=True
                )

    if not has_alerts:
        st.success("✅ No significant air quality alerts at the moment. AQI levels are currently within the good to moderate range for most areas.", icon="✅")


def render_alert_subscription_tab(df):
    st.markdown('<div class="section-header">📱 SMS Alert Subscription</div>', unsafe_allow_html=True)

    st.info("Your location will be detected automatically. You can still edit it manually. **Requires Kriging Heatmap tab to be viewed first.**", icon="📍")

    # --- AUTO GPS DETECTION ---
    geo = get_user_geolocation()
    if geo:
        auto_lat, auto_lon = geo
    else:
        auto_lat, auto_lon = 28.6139, 77.2090

    # --- USER INPUT ---
    col1, col2 = st.columns(2)

    with col1:
        location_name = st.text_input(
            "📍 Your Location Name",
            placeholder="Connaught Place, Delhi",
            value="My Current Location" if geo else "",
        )

        user_lat = st.number_input(
            "Latitude",
            value=auto_lat,
            step=0.0001,
            format="%.6f"
        )

        user_lon = st.number_input(
            "Longitude",
            value=auto_lon,
            step=0.0001,
            format="%.6f"
        )

    with col2:
        phone_number = st.text_input(
            "📱 Phone Number (SMS77.io)",
            placeholder="+91XXXXXXXXXX"
        )

        radius = st.slider("Search Radius (km)", 1, 20, 10)

        st.markdown("<br>", unsafe_allow_html=True)
        send_button = st.button("📤 Send Alert Now", use_container_width=True)

    # --- PROCESS ACTION ---
    if send_button:
        if not phone_number.startswith("+"):
            st.error("Phone number must include country code. Example: +919876543210")
            return
            
        if location_name.strip() == "":
            st.error("Please enter your location name.")
            return

        # --- Use KRIGING GRID instead of station data ---
        with st.spinner("Calculating interpolated AQI for your location..."):
            lon_grid, lat_grid, z_grid = st.session_state.get("kriging_result", (None,None,None))

            if lon_grid is None:
                st.error("Kriging results are unavailable. Please navigate to the Kriging Heatmap tab first.", icon="❌")
                return

            # Get AQI at user's exact location
            aqi_value = get_aqi_from_kriging_point(
                user_lon, user_lat, lon_grid, lat_grid, z_grid
            )

            if aqi_value is None:
                st.error("Your location falls outside the interpolated area for Delhi.", icon="❌")
                return

            # Weather
            weather = fetch_weather_data()
            if not weather:
                weather_desc = "N/A"
                temp = 25.0
            else:
                weather_desc, _ = get_weather_info(weather["current"]["weather_code"])
                temp = weather["current"]["temperature_2m"]

            # Create message
            category, _, emoji, advice = get_aqi_category(aqi_value)

            message = f"""
📍 Air Quality Alert — {location_name}

{emoji} AQI: {aqi_value:.0f} ({category})
🌡️ Temp: {temp:.1f} অক্ষরে സെൽഷ്യസ്
🌤️ Weather: {weather_desc}

💡 Advice: {advice}

Stay safe!
"""

        # SEND SMS (SMS77.io)
        api_response = send_sms_sms77(phone_number, message)

        st.markdown("### 📄 Alert Preview")
        st.info(message)
        
        if api_response.get('success'):
             st.success(f"SMS sent successfully! Status: {api_response.get('success_code')}", icon="✅")
        else:
             st.error(f"SMS failed. Status: {api_response.get('error') or api_response.get('messages', ['Unknown error'])[0]}", icon="❌")
             st.json(api_response)


def render_dummy_forecast_tab():
    """Render a dummy 24-hour AQI forecast using simulated data."""
    st.markdown('<div class="section-header">📈 24-Hour AQI Forecast (Sample)</div>',
                unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background-color: white; padding: 1rem; border-radius: 10px; border-left: 4px solid {TOPIC_TEAL_LIGHT}; margin-bottom: 1rem;">
        <p style="color: {TOPIC_BLUE_DARK}; margin: 0; font-weight: 500;">
        This sample forecast simulates how the Air Quality Index (AQI) may change over the next 24 hours.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Simulate a smooth AQI forecast for 24 hours
    hours = np.arange(0, 24)
    base_aqi = 120 + 40 * np.sin(hours / 3) + np.random.normal(0, 5, size=24)
    timestamps = [datetime.now() + timedelta(hours=i) for i in range(24)]
    forecast_df = pd.DataFrame({
        "timestamp": timestamps,
        "forecast_aqi": np.clip(base_aqi, 40, 300)
    })

    # Plot forecast trend
    fig = px.line(
        forecast_df,
        x="timestamp",
        y="forecast_aqi",
        title="Predicted AQI Trend for Next 24 Hours (Simulated)",
        markers=True,
        line_shape="spline"
    )
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Predicted AQI",
        showlegend=False,
        margin=dict(t=40, b=20, l=0, r=20),
        paper_bgcolor='white',
        plot_bgcolor='white',
        title_font_color=TOPIC_BLUE_DARK,
        font_color=TOPIC_CARD_TEXT,
        xaxis=dict(gridcolor='#F0F0F0'),
        yaxis=dict(gridcolor='#F0F0F0')
    )

    st.plotly_chart(fig, use_container_width=True)

    # Display summary
    avg_aqi = forecast_df["forecast_aqi"].mean()
    max_aqi = forecast_df["forecast_aqi"].max()
    min_aqi = forecast_df["forecast_aqi"].min()

    st.markdown(f"""
    <div style="background-color: white; padding: 1rem; border-radius: 10px; border-left: 5px solid {TOPIC_BLUE_DARK}; margin-top: 1rem; color: {TOPIC_CARD_TEXT};">
        <b>Average Forecasted AQI:</b> {avg_aqi:.1f}  
        <br><b>Expected Range:</b> {min_aqi:.1f} – {max_aqi:.1f}
        <br><b>Air Quality Outlook:</b> Moderate to Unhealthy range over the next day.
    </div>
    """, unsafe_allow_html=True)

def render_analytics_tab(df):
    """Renders charts and data analytics."""
    st.markdown('<div class="section-header">📊 Data Analytics</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown("**AQI Category Distribution**")
        category_counts = df['category'].value_counts()
        fig = px.pie(
            values=category_counts.values, names=category_counts.index, hole=0.4,
            color=category_counts.index,
            color_discrete_map={
                "Good": "#009E60", "Moderate": "#FFD600", "Unhealthy for Sensitive Groups": "#F97316",
                "Unhealthy": "#DC2626", "Very Unhealthy": "#9333EA", "Hazardous": "#7E22CE"
            }
        )
        fig.update_traces(textinfo='percent+label',
                          pull=[0.05]*len(category_counts.index))
        fig.update_layout(
            showlegend=False,
            margin=dict(t=0, b=0, l=0, r=0),
            paper_bgcolor='white',
            plot_bgcolor='white',
            font_color=TOPIC_CARD_TEXT
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("**Top 10 Most Polluted Stations**")
        top_10 = df.nlargest(10, 'aqi').sort_values('aqi', ascending=True)
        fig = px.bar(
            top_10, x='aqi', y='station_name', orientation='h',
            color='aqi', color_continuous_scale=px.colors.sequential.Reds
        )
        fig.update_layout(
            xaxis_title="AQI",
            yaxis_title="",
            showlegend=False,
            margin=dict(t=20, b=20, l=0, r=20),
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(gridcolor='#F0F0F0'),
            yaxis=dict(gridcolor='#F0F0F0'),
            font_color=TOPIC_CARD_TEXT
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Full Station Data**")
    display_df = df[['station_name', 'aqi', 'category',
                     'last_updated']].sort_values('aqi', ascending=False)
    st.dataframe(display_df, use_container_width=True, hide_index=True)


# ==========================
# MAIN APP EXECUTION
# ==========================
aqi_data_raw = fetch_live_data()

if aqi_data_raw.empty:
    st.error("⚠️ **Could not fetch live AQI data.** The API may be down or there's a network issue. Please try again later.", icon="🚨")
    # Render header with empty data to avoid crashing
    render_header(aqi_data_raw) 
else:
    # 1. Load the Delhi boundary (WGS84 GDF & UTM Polygon)
    delhi_gdf, delhi_polygon_utm = load_delhi_boundary_from_url()
    
    aqi_data_filtered = pd.DataFrame() 
    
    if delhi_gdf is not None and not delhi_gdf.empty:
        # 2. Convert raw station data to a GeoDataFrame
        geometry = [Point(xy) for xy in zip(aqi_data_raw['lon'], aqi_data_raw['lat'])]
        stations_gdf = gpd.GeoDataFrame(aqi_data_raw, crs="epsg:4326", geometry=geometry)
        
        # 3. Clip stations to keep only those INSIDE the Delhi polygon
        delhi_polygon_wgs84 = delhi_gdf.unary_union # Re-derive WGS84 polygon from GDF
        
        # Clip stations_gdf to the boundary polygon
        try:
             aqi_data_filtered_gdf = gpd.clip(stations_gdf, delhi_polygon_wgs84)
             aqi_data_filtered = pd.DataFrame(aqi_data_filtered_gdf.drop(columns='geometry'))
        except Exception:
             # Fallback if clipping fails (e.g., if stations_gdf is empty after geometry conversion)
             aqi_data_filtered = pd.DataFrame()


    
    if aqi_data_filtered.empty:
        st.info("⚠️ **No monitoring stations found *inside* the Delhi boundary.** Using data from the broader region.", icon="ℹ️")
        # Fallback to raw data if filtering fails or finds nothing
        aqi_data_to_display = aqi_data_raw
    else:
        st.success(f"✅ Loaded {len(aqi_data_filtered)} monitoring stations inside the Delhi boundary.", icon="🛰️")
        aqi_data_to_display = aqi_data_filtered
    

    # 4. Render all components using the (now filtered) data
    render_header(aqi_data_to_display)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["🗺️ Live Map", "🔔 Alerts & Health",
         "📊 Analytics", "📱 SMS Alerts","📈 Forecast","🔥 Kriging Heatmap"])

    with tab1:
        with st.container():
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            # Pass the filtered data
            render_map_tab(aqi_data_to_display) 
            st.markdown('</div>', unsafe_allow_html=True)
    with tab2:
        with st.container():
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            # Pass the filtered data
            render_alerts_tab(aqi_data_to_display)
            st.markdown('</div>', unsafe_allow_html=True)
    with tab3:
        with st.container():
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            # Pass the filtered data
            render_analytics_tab(aqi_data_to_display)
            st.markdown('</div>', unsafe_allow_html=True)
    with tab4:
        with st.container():
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            # Pass the filtered data (for nearby calculations)
            render_alert_subscription_tab(aqi_data_to_display)
            st.markdown('</div>', unsafe_allow_html=True)
    with tab5:
        with st.container():
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            render_dummy_forecast_tab()
            st.markdown('</div>', unsafe_allow_html=True)
    with tab6:
        with st.container():
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            # Pass the filtered data
            render_kriging_tab(aqi_data_to_display) 
            st.markdown('</div>', unsafe_allow_html=True)
