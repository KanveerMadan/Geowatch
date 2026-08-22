import ee
from ingestion.gee_client import initialize_gee

# Canonical Dharavi AOI
WEST, SOUTH, EAST, NORTH = 72.836, 19.037, 72.862, 19.060

# UNVERIFIED — this is the guess used in exposure_constants.py.
# This script exists specifically to confirm or reject it.
GHSL_ASSET_CANDIDATES = [
    "JRC/GHSL/P2023A/GHS_BUILT_S/2020",
    "JRC/GHSL/P2023A/GHS_BUILT_S",
    "JRC/GHSL/P2016/BUILT_LDSMT_GLOBE_V1",
]


def safe_get(label, obj):
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
    aoi = ee.Geometry.Rectangle([WEST, SOUTH, EAST, NORTH])

    for asset_id in GHSL_ASSET_CANDIDATES:
        print(f"\n\n{'#' * 72}\nTRYING: {asset_id}\n{'#' * 72}")

        # Try as a single Image first
        img = ee.Image(asset_id)
        band_names = safe_get(f"Band names (as Image) for {asset_id}", img.bandNames())
        if band_names:
            proj = safe_get(f"Projection for {asset_id}", img.select(0).projection())
            scale = safe_get(f"Nominal scale (m) for {asset_id}", img.select(0).projection().nominalScale())

            stats = img.select(0).reduceRegion(
                reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
                geometry=aoi, scale=100, maxPixels=1e9,
            )
            safe_get(f"Dharavi AOI stats for {asset_id}", stats)
            continue

        # If that failed, try as an ImageCollection
        collection = ee.ImageCollection(asset_id)
        count = safe_get(f"Collection size (as ImageCollection) for {asset_id}", collection.size())
        if count:
            first = ee.Image(collection.first())
            safe_get(f"Band names of first image for {asset_id}", first.bandNames())
            safe_get(f"First image metadata for {asset_id}", first.toDictionary())

    print(
        "\n\nVERIFICATION COMPLETE.\n"
        "Whichever candidate above returned real band names, a plausible "
        "scale (~100m or ~30m), and non-null Dharavi stats is the one to "
        "use. Update GHSL_BUILTUP_ASSET in configs/exposure_constants.py "
        "to match EXACTLY — do not guess further from documentation.\n"
        "If ALL candidates failed: do not fabricate a fourth guess blind — "
        "search the GEE data catalog (developers.google.com/earth-engine/"
        "datasets/catalog) for 'GHSL' and paste back the exact listed asset "
        "ID before retrying.\n"
    )


if __name__ == "__main__":
    main()