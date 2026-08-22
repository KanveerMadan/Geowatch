import ee
from ingestion.gee_client import initialize_gee

# Canonical Dharavi AOI — coordinates only; the actual ee.Geometry object
# is built inside main(), AFTER initialize_gee() runs. Building it at
# module level (before initialization) is what caused the crash.
WEST, SOUTH, EAST, NORTH = 72.836, 19.037, 72.862, 19.060

# Do not change this asset ID until the live check proves it is wrong.
WORLDPOP_COLLECTION_ID = "WorldPop/GP/100m/pop"

def safe_get(label, obj):
    """Print GEE object output without hiding failures."""
    try:
        value = obj.getInfo()
        print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
        print(value)
        return value
    except Exception as exc:
        print(f"\n{'=' * 72}\nFAILED: {label}\n{'=' * 72}")
        print(f"{type(exc).__name__}: {exc}")
        return None


def main():
    initialize_gee()
    AOI = ee.Geometry.Rectangle([WEST, SOUTH, EAST, NORTH])

    # 1. Asset existence and collection size
    collection = ee.ImageCollection(WORLDPOP_COLLECTION_ID)
    count = safe_get("1. WorldPop collection size", collection.size())
    if not count:
        print("\nSTOP: Collection does not exist or is empty. Do not build against it.")
        return

    # 2. Inspect one raw collection item and its metadata
    first = ee.Image(collection.first())
    safe_get("2. First collection image metadata", first.toDictionary())

    # 3. Actual available years across the collection
    years = collection.aggregate_array("year").distinct().sort()
    safe_get("3. Available `year` property values", years)

    # 4. Actual country metadata values — verify the exact key before filtering.
    for property_name in ["country", "country_name", "iso3", "ISO3", "country_code"]:
        values = collection.aggregate_array(property_name).distinct().sort()
        safe_get(f"4. Candidate country metadata values for `{property_name}`", values)

    # 5. Band names
    safe_get("5. Band names of first image", first.bandNames())

    # 6. Projection and scale for the expected population band
    population_band = first.select("population")
    safe_get("6. Population band projection", population_band.projection())
    safe_get("7. Population band nominal scale in metres", population_band.projection().nominalScale())

    # 7. Find India images
    india = collection.filter(ee.Filter.eq("country", "IND"))
    india_count = safe_get("8. India image count using ISO3 == IND", india.size())
    if not india_count:
        print("\nIndia filter returned no images. Inspect section 4 and update "
              "the country filter deliberately. Do not continue with guessed metadata.")
        return

    india_years = india.aggregate_array("year").distinct().sort()
    safe_get("9. Available India years", india_years)

    # Choose most recent India image based on actual year metadata
    latest_year = ee.Number(india.aggregate_max("year"))
    latest_india = ee.Image(india.filter(ee.Filter.eq("year", latest_year)).first())
    safe_get("10. Selected latest India image metadata", latest_india.toDictionary())

    # 8. Dharavi AOI zonal sum
    zonal_sum = latest_india.select("population").reduceRegion(
        reducer=ee.Reducer.sum(), geometry=AOI, scale=100, maxPixels=1e9, bestEffort=False,
    )
    safe_get("11. Dharavi WorldPop zonal sum at 100m", zonal_sum)

    # 9. Valid-data coverage in the AOI
    valid_pixel_count = latest_india.select("population").reduceRegion(
        reducer=ee.Reducer.count(), geometry=AOI, scale=100, maxPixels=1e9, bestEffort=False,
    )
    safe_get("12. Dharavi valid WorldPop pixel count at 100m", valid_pixel_count)

    # 10. Explicit no-data check: Dharavi point vs. a remote/ocean-like point
    dharavi_point = ee.Geometry.Point([72.849, 19.048])
    ocean_point = ee.Geometry.Point([72.849, 18.0])

    dharavi_sample = latest_india.select("population").reduceRegion(
        reducer=ee.Reducer.first(), geometry=dharavi_point, scale=100, maxPixels=1000,
    )
    ocean_sample = latest_india.select("population").reduceRegion(
        reducer=ee.Reducer.first(), geometry=ocean_point, scale=100, maxPixels=1000,
    )
    safe_get("13. Dharavi point population sample", dharavi_sample)
    safe_get("14. Remote/ocean point population sample — inspect null vs zero behavior", ocean_sample)

    print(
        "\nVERIFICATION COMPLETE.\n"
        "Before implementation, save this output and confirm:\n"
        "- actual collection ID;\n"
        "- actual India metadata filter;\n"
        "- selected year;\n"
        "- actual population band;\n"
        "- nominal scale;\n"
        "- whether values are population counts per pixel;\n"
        "- null/no-data behavior.\n"
    )


if __name__ == "__main__":
    main()