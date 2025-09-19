import geopandas as gpd

# Read the original GeoJSON
gdf = gpd.read_file("data/eligible_areas.geojson")

# Dissolve all geometries into one
single_boundary = gdf.union_all()

# Create a new GeoDataFrame with the dissolved geometry
gdf_single = gpd.GeoDataFrame(geometry=[single_boundary], crs=gdf.crs)

# Save to a new GeoJSON file
gdf_single.to_file("data/eligible_areas_dissolved.geojson", driver="GeoJSON")
print("Dissolved boundary saved to data/eligible_areas_dissolved.geojson")