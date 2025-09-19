import streamlit as st
import geopandas as gpd
import boto3
from shapely.geometry import Point
import pydeck as pdk
import requests
import time

# =====================
# Password protection
# =====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pw = st.text_input("Enter password:", type="password")
    if st.button("Login"):
        if pw == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.success("Access granted")
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()

# =====================
# App starts here
# =====================
st.title("Address Boundary Checker (Test)")

# Load boundary file
boundary = gpd.read_file("data/eligible_areas_dissolved.geojson")
boundary = boundary.to_crs(epsg=4326)

# Initialize AWS Location client
aws_available = False
client = None
index_name = None

try:
    required_secrets = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "PLACE_INDEX_NAME"]
    missing_secrets = [s for s in required_secrets if s not in st.secrets]

    if missing_secrets:
        st.warning(f"⚠️ Missing AWS secrets: {', '.join(missing_secrets)}")
    else:
        client = boto3.client(
            "location",
            aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
            region_name=st.secrets["AWS_DEFAULT_REGION"],
        )
        index_name = st.secrets["PLACE_INDEX_NAME"]

        # Test by searching a harmless string (instead of list indexes)
        try:
            client.search_place_index_for_text(IndexName=index_name, Text="test", MaxResults=1)
            aws_available = True
            st.success("✅ AWS Location Service connected")
        except Exception as e:
            st.warning(f"⚠️ AWS Location Service test failed: {type(e).__name__}")
            st.info("Falling back to free geocoding service")
            st.write(str(e))

except Exception as e:
    st.error(f"❌ AWS setup failed: {type(e).__name__}")
    st.info("Falling back to free geocoding service")

# =====================
# Geocoding functions
# =====================
def geocode_address_aws(address: str):
    try:
        response = client.search_place_index_for_text(
            IndexName=index_name,
            Text=address,
            MaxResults=1
        )
        results = response.get("Results", [])
        if not results:
            return None, "No results found"
        coords = results[0]["Place"]["Geometry"]["Point"]  # [lon, lat]
        return (coords[1], coords[0]), None
    except Exception as e:
        return None, f"AWS error: {str(e)}"

def geocode_address_fallback(address: str):
    try:
        time.sleep(1)  # respect Nominatim rate limits
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "SD-Solar-Boundary-Checker/1.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None, "No results from fallback"
        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
        return (lat, lon), None
    except Exception as e:
        return None, f"Fallback geocoding failed: {str(e)}"

# =====================
# User Input
# =====================
address = st.text_input("Enter an address to check if it's eligible:")

if address:
    result, error = (geocode_address_aws(address) if aws_available else (None, "AWS not available"))

    if error:
        st.warning(f"⚠️ AWS failed: {error}")
        st.info("🔄 Trying fallback geocoding...")
        result, fb_error = geocode_address_fallback(address)
        if fb_error:
            st.error(f"🚫 Geocoding failed: {fb_error}")
            st.stop()
        else:
            st.success("✅ Address geocoded with fallback service")
    else:
        st.success("✅ Address geocoded with AWS Location Service")

    # =====================
    # Boundary check + Map
    # =====================
    if result:
        lat, lon = result
        point = gpd.GeoSeries([Point(lon, lat)], crs=4326)
        inside = boundary.contains(point[0]).any()
        st.write(f"**Inside boundary?** {'✅ Yes' if inside else '❌ No'}")

        gdf = gpd.read_file("data/eligible_areas_dissolved.geojson")
        polygon = gdf.geometry.iloc[0]

        polygons = []
        if polygon.geom_type == "Polygon":
            polygons.append(list(polygon.exterior.coords))
        elif polygon.geom_type == "MultiPolygon":
            for poly in polygon.geoms:
                polygons.append(list(poly.exterior.coords))

        polygon_data = [
            {"polygon": coords, "fill_color": [255, 0, 0, 40], "line_color": [255, 0, 0]}
            for coords in polygons
        ]

        polygon_layer = pdk.Layer(
            "PolygonLayer",
            polygon_data,
            get_polygon="polygon",
            get_fill_color="fill_color",
            get_line_color="line_color",
        )

        point_layer = pdk.Layer(
            "ScatterplotLayer",
            [{"position": [lon, lat], "color": [0, 0, 255], "radius": 100}],
            get_position="position",
            get_color="color",
            get_radius="radius",
        )

        view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=12, pitch=0)
        st.pydeck_chart(pdk.Deck(layers=[polygon_layer, point_layer], initial_view_state=view_state))
