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

    for scale in [92.76624203150153, 100, 30, 10]:
        result = img.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=aoi, scale=scale, maxPixels=1e9, bestEffort=False,
        ).getInfo()
        print(f"scale={scale}: sum={result.get('population')}")

    # Also check the image's native projection/pyramiding info directly
    print("\nProjection:", img.projection().getInfo())


if __name__ == "__main__":
    main()