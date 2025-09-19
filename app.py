import streamlit as st
import geopandas as gpd
import boto3
from shapely.geometry import Point
import pydeck as pdk

# =====================
# Password protection
# =====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pw = st.text_input("Enter password:", type="password")
    if st.button("Login"):
        if pw == st.secrets["APP_PASSWORD"]:  # Store in Streamlit secrets
            st.session_state.authenticated = True
            st.success("Access granted")
        else:
            st.error("Wrong password")
    st.stop()  # prevent rest of app from loading until login succeeds

# =====================
# App starts here
# =====================
st.title("Address Boundary Checker (AWS)")

# Load boundary file (local or bundled in repo)
boundary = gpd.read_file("data/eligible_areas_dissolved.geojson")
boundary = boundary.to_crs(epsg=4326)

# Initialize AWS Location client
client = boto3.client(
    "location",
    aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
    region_name=st.secrets["AWS_DEFAULT_REGION"],
)

index_name = st.secrets["PLACE_INDEX_NAME"]  # Example: "MyPlaceIndex"

def geocode_address(address: str):
    """Geocode address with AWS Location Service"""
    response = client.search_place_index_for_text(
        IndexName=index_name,
        Text=address,
        MaxResults=1
    )
    results = response.get("Results", [])
    if not results:
        return None
    coords = results[0]["Place"]["Geometry"]["Point"]  # [lon, lat]
    return coords[1], coords[0]  # (lat, lon)

# =====================
# User Input
# =====================
address = st.text_input("Enter an address to check if it's eligible: ")

if address:
    result = geocode_address(address)
    if result:
        lat, lon = result
        point = gpd.GeoSeries([Point(lon, lat)], crs=4326)

        inside = boundary.contains(point[0]).any()
        st.write(f"**Inside boundary?** {'✅ Yes' if inside else '❌ No'}")

        gdf = gpd.read_file("data/eligible_areas_dissolved.geojson")
        polygon = gdf.geometry.iloc[0]

        # Handle Polygon vs MultiPolygon
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
            pickable=True,
            stroked=True,
            filled=True,
            extruded=False,
        )

        point_layer = pdk.Layer(
            "ScatterplotLayer",
            [{"position": [lon, lat], "color": [0, 0, 255], "radius": 100}],
            get_position="position",
            get_color="color",
            get_radius="radius",
            pickable=True,
        )

        view_state = pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=12,
            pitch=0,
        )

        st.pydeck_chart(pdk.Deck(layers=[polygon_layer, point_layer], initial_view_state=view_state))
    else:
        st.error("Address not found")
