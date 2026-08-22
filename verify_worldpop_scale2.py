import ee
from ingestion.gee_client import initialize_gee

WEST, SOUTH, EAST, NORTH = 72.836, 19.037, 72.862, 19.060
WORLDPOP_COLLECTION_ID = "WorldPop/GP/100m/pop"


def main():
    initialize_gee()
    aoi = ee.Geometry.Rectangle([WEST, SOUTH, EAST, NORTH])

    collection = ee.ImageCollection(WORLDPOP_COLLECTION_ID).filterBounds(aoi).filter(
        ee.Filter.eq("country", "IND")
    )
    latest_year = ee.Number(collection.aggregate_max("year"))
    img = ee.Image(collection.filter(ee.Filter.eq("year", latest_year)).first()).select("population")

    proj = img.projection()
    print("Native CRS:", proj.crs().getInfo())
    print("Native transform:", proj.getInfo()["transform"])

    # Use the image's OWN projection/transform directly -- no scale
    # guessing, no resampling ambiguity. This forces reduceRegion to sum
    # over the exact native pixel grid.
    result = img.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        crs=proj.crs(),
        crsTransform=proj.getInfo()["transform"],
        maxPixels=1e9,
        bestEffort=False,
    ).getInfo()
    print(f"\nSum using native crsTransform (no scale param): {result.get('population')}")


if __name__ == "__main__":
    main()