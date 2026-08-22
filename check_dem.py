import ee
from ingestion.gee_client import initialize_gee

initialize_gee()

old = ee.ImageCollection("COPERNICUS/DEM/GLO30").first()
new = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").first()

print("Old bands:", old.bandNames().getInfo())
print("New bands:", new.bandNames().getInfo())
