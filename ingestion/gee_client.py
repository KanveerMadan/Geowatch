import ee
import geemap
from dotenv import load_dotenv
import os

load_dotenv()

def initialize_gee():
    """
    Initialize Google Earth Engine.
    Uses persistent credentials from earthengine authenticate.
    """
    try:
        ee.Initialize(project=os.getenv("GEE_PROJECT_ID"))
        print("GEE initialized successfully.")
    except Exception as e:
        print(f"GEE initialization failed: {e}")
        raise

def get_map(center_lat: float, center_lon: float, zoom: int = 10) -> geemap.Map:
    """
    Return a geemap Map object centered on given coordinates.
    Used for quick visual inspection during development.
    """
    m = geemap.Map(center=[center_lat, center_lon], zoom=zoom)
    return m