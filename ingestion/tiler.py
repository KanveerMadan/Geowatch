import ee
import os
import numpy as np
from PIL import Image


TILE_SIZE = 512  # pixels — safe for M3 + 8GB
SCALE = 10       # Sentinel-2 native resolution in meters

# ── Chunked-export constants (see export_image_local) ──────────────────
#
# GEE's direct-download path (getDownloadURL, which geemap.ee_export_image
# wraps) enforces a hard request-size ceiling. Measured live, not guessed:
#   "Total request size (284642550 bytes) must be less than or equal to
#    50331648 bytes."
# 50331648 == 48 MiB. This is an API limit, not a tunable setting.
GEE_DOWNLOAD_LIMIT_BYTES = 50_331_648

# GEE's own accounting of "request size" is larger than the raw pixel
# payload. Calibrated against the refusal above: the full-Mumbai grid is
# 2265x4189x6 bands, i.e. 227,714,040 raw float32 bytes, and GEE reported
# 284,642,550 -- a factor of exactly 1.2500. Used to convert a local pixel
# estimate into the number GEE will actually check against its ceiling.
GEE_REQUEST_SIZE_OVERHEAD = 1.25

# Fraction of the ceiling a single chunk is allowed to target. Deliberate
# headroom: the overhead factor above is calibrated from ONE observation,
# band count can vary, and a chunk that lands marginally over the ceiling
# fails the whole run. 0.5 keeps every chunk at roughly half the limit.
CHUNK_BUDGET_FRACTION = 0.5

# float32 -- confirmed against every raw.tif this pipeline has produced.
BYTES_PER_SAMPLE = 4

# GEE's meters->degrees constant for EPSG:4326 exports. Derived as
# SCALE / 111319.49079327358; the literal is pinned here because it is the
# value GEE actually produced in existing exports (verified byte-exact
# against phase1_dharavi's and phase1_multitile's raw.tif transforms), and
# recomputing it in float drifts by 1 ULP.
DEGREES_PER_PIXEL_AT_SCALE_10 = 8.983152841195215e-05

# ── Band order — C4 / build item 44 ────────────────────────────────────
#
# This used to be two literals under a comment reading "Must match
# S2_BAND_NAMES order in sentinel2.py". That comment was the ONLY thing holding
# the contract, and C4 is what happens when it drifts: RGB_BAND_INDICES pinned
# 2/1/0, so a reordered export would silently swap R and B into both the SAM
# segmentation input and the classifier input. Nothing would error; the model
# would simply be fed a different image than the one it was trained on.
#
# 01_DIAGNOSIS.md §4 S3: "a rule enforced only by prose fails at the first edit
# made by someone who did not read the prose." Three things replace the prose.
from ingestion.sentinel2 import S2_BAND_NAMES

BAND_NAMES = list(S2_BAND_NAMES)

# 1. THE CROSS-MODULE CONTRACT IS NOW CODE. BAND_NAMES is derived from
#    sentinel2.py rather than retyped, so the two cannot disagree at all. The
#    assertion below is belt-and-braces against someone reassigning BAND_NAMES
#    later, and it fires at import -- before any pixel is read.
assert BAND_NAMES == list(S2_BAND_NAMES), (
    f"BAND_NAMES {BAND_NAMES} has diverged from sentinel2.py's S2_BAND_NAMES "
    f"{list(S2_BAND_NAMES)}. These describe the same exported GeoTIFF and must "
    f"be identical."
)

# 2. THE INDICES ARE DERIVED, NOT PINNED. If the band order ever changes, these
#    follow it automatically. This is the half that makes the silent R/B swap
#    structurally impossible rather than merely detectable -- a hardcoded 2/1/0
#    is correct only by coincidence of the current order.
RGB_BAND_INDICES = {name: BAND_NAMES.index(name) for name in ("Red", "Green", "Blue")}

# 3. The read boundary verifies against the FILE, not the constant. See
#    assert_band_order() below.

# Set GEOWATCH_STRICT_BAND_ORDER=1 to make an unverifiable file an error rather
# than a warning. Off by default because every GeoTIFF this pipeline has
# produced so far carries no band descriptions at all (measured: 150 of 150), so
# defaulting to strict would refuse every existing run. See assert_band_order().
BAND_ORDER_STRICT_ENV = "GEOWATCH_STRICT_BAND_ORDER"


class BandOrderError(ValueError):
    """Raised when a GeoTIFF's bands are not the order this pipeline assumes."""


def stamp_band_descriptions(path: str, band_names=None) -> bool:
    """
    Write BAND_NAMES into the GeoTIFF's band descriptions, in place.

    WHY THIS EXISTS. Item 44 asks for the read boundary to check the file's
    actual band descriptions. Measured first: every raw.tif this pipeline has
    produced reports `descriptions == (None,) * 6` -- GEE's export path
    (geemap.ee_export_image / getDownloadURL) does not write them, and neither
    did the chunked stitcher. So the check the item describes had nothing to
    read, and would have been decoration: a test that cannot fail.

    This is the half that makes the check real. Once the export stamps the
    names, the file carries its own contract and a future reordering is caught
    by comparing the file against BAND_NAMES rather than by trusting a comment.

    Returns True if descriptions were written, False if the file could not be
    opened for update. Never raises on a read-only or missing file: failing to
    ANNOTATE a good export must not fail the export.
    """
    import rasterio

    names = list(band_names or BAND_NAMES)
    try:
        with rasterio.open(path, "r+") as dst:
            if dst.count != len(names):
                print(
                    f"WARNING: not stamping band descriptions on {path}: file "
                    f"has {dst.count} bands, expected {len(names)} {names}."
                )
                return False
            dst.descriptions = tuple(names)
        return True
    except Exception as e:
        print(f"WARNING: could not stamp band descriptions on {path}: {e}")
        return False


def assert_band_order(src, path: str = "<unknown>", strict: bool = None,
                      expected: list = None) -> str:
    """
    Verify a GeoTIFF's bands are the order this pipeline assumes.

    Three outcomes, kept distinct on purpose. Collapsing the third into the
    first is the whole bug class: "nobody checked" must never render as
    "checked and fine" (the same collapse C23 made with Gate C's waiver).

        "verified"     descriptions present and equal to BAND_NAMES
        "mismatch"     descriptions present and different  -> ALWAYS raises
        "unverifiable" descriptions absent -- the file carries no contract

    A wrong band COUNT always raises regardless: it means the export did not
    produce the six-band image the rest of the pipeline is written against, and
    every index into it is meaningless. This was previously a print() that
    execution continued straight past.

    `strict` promotes "unverifiable" to an error. Defaults to the
    GEOWATCH_STRICT_BAND_ORDER env var, off unless set, because 150 of 150
    existing files are unverifiable and refusing them would break every
    reprocessing run. New exports are stamped, so this default decays toward
    strict on its own as files are regenerated.

    `expected` defaults to BAND_NAMES. Item 21 Phase A passes the band list of
    its multi-band input stack, so that stack goes through this same check
    rather than a second copy of it.

    Returns the verdict string so callers can record it.
    """
    expected = list(expected or BAND_NAMES)
    if strict is None:
        strict = os.getenv(BAND_ORDER_STRICT_ENV, "").strip().lower() in ("1", "true", "yes")

    if src.count != len(expected):
        raise BandOrderError(
            f"{path}: expected {len(expected)} bands {expected}, found "
            f"{src.count}. Every band index in this pipeline (including "
            f"RGB_BAND_INDICES={RGB_BAND_INDICES}) assumes the full band set; "
            f"check the export included all S2_BANDS from sentinel2.py, not "
            f"just RGB."
        )

    descriptions = list(src.descriptions or [])
    if not descriptions or all(d is None for d in descriptions):
        message = (
            f"{path}: band order UNVERIFIED -- the file carries no band "
            f"descriptions, so the assumed order {expected} could not be "
            f"checked against it. Exports written before build item 44 are not "
            f"stamped; re-export, or run stamp_band_descriptions() on the file, "
            f"to make this checkable."
        )
        if strict:
            raise BandOrderError(message)
        print(f"WARNING: {message}")
        return "unverifiable"

    if descriptions != expected:
        raise BandOrderError(
            f"{path}: BAND ORDER MISMATCH. File reports {descriptions}; this "
            f"pipeline assumes {expected}. Reading it would feed the wrong "
            f"channels to both the SAM segmentation input and the classifier "
            f"input -- silently, because the arrays are the same shape either "
            f"way. Refusing rather than guessing (C4)."
        )

    return "verified"


def export_image_to_drive(
    image: ee.Image,
    aoi: ee.Geometry,
    filename: str,
    folder: str = "GeoWatch",
    scale: int = SCALE,
) -> ee.batch.Task:
    """
    Export a GEE image to Google Drive as a GeoTIFF.
    This is the standard approach for larger AOIs.

    Args:
        image: clipped, cloud-masked Sentinel-2 image (all 6 bands)
        aoi: region to export
        filename: output filename (no extension)
        folder: Google Drive folder name
        scale: resolution in meters. GEE will resample any band not natively
            at this scale (e.g. SWIR1/SWIR2 at native 20m) to match — no
            separate upsampling step is needed on the client side.

    Returns:
        GEE export task (started)
    """
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=filename,
        folder=folder,
        fileNamePrefix=filename,
        region=aoi,
        scale=scale,
        maxPixels=1e9,
        fileFormat="GeoTIFF",
    )
    task.start()
    print(f"Export task started: {filename} → Google Drive/{folder}")
    print("Monitor at: https://code.earthengine.google.com/tasks")
    return task


def _degrees_per_pixel(scale: int) -> float:
    """
    Pixel size in degrees for a GEE EPSG:4326 export at `scale` metres.
    Anchored on the measured scale=10 value so the common path is exact.
    """
    if scale == SCALE:
        return DEGREES_PER_PIXEL_AT_SCALE_10
    return DEGREES_PER_PIXEL_AT_SCALE_10 * (scale / SCALE)


def _compute_export_grid(west: float, south: float, east: float, north: float,
                          scale: int = SCALE) -> dict:
    """
    Compute the exact pixel grid a GEE EPSG:4326 export uses for this AOI.

    GEE snaps exports to a GLOBAL lattice anchored at (0, 0) with pixel
    size `px` -- verified empirically: existing raw.tif origins divide by
    px to exact integers (810806.000000 / 212175.000000 for Dharavi,
    810405.000000 / 212398.000000 for the 4-tile run). Because the lattice
    is global rather than per-request, two separate exports that both snap
    to it are automatically co-registered -- which is what makes seam-free
    chunking possible at all.

    Verified to reproduce both known exports exactly:
      Dharavi   -> 291x257   (matches raw.tif)
      multitile -> 892x891   (matches raw.tif)

    Returns integer lattice indices plus the derived width/height.
    """
    import math
    px = _degrees_per_pixel(scale)
    x0 = math.floor(west / px)
    x1 = math.ceil(east / px)
    y1 = math.ceil(north / px)     # north edge, lattice row index
    y0 = math.floor(south / px)
    return {
        "px": px,
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "width": x1 - x0,
        "height": y1 - y0,
        "west": x0 * px,
        "north": y1 * px,
    }


def _estimate_request_bytes(width: int, height: int, n_bands: int) -> int:
    """GEE-accounted request size for a width x height x n_bands float32 read."""
    return int(width * height * n_bands * BYTES_PER_SAMPLE
               * GEE_REQUEST_SIZE_OVERHEAD)


def _plan_export_chunks(width: int, height: int, n_bands: int) -> list:
    """
    Split a width x height pixel grid into the fewest chunks that each fit
    under CHUNK_BUDGET_FRACTION of GEE's ceiling.

    Chunk boundaries use the SAME convention Phase 2 established for the
    tile loop -- `range(0, extent, step)` with `min(off + step, extent)`
    clamping -- so chunks are non-overlapping and exactly cover the grid.
    That invariant is what guarantees no seams, no gaps and no off-by-one
    overlap in the stitched raster.

    Returns a list of (col_off, row_off, chunk_w, chunk_h).
    """
    import math
    budget = int(GEE_DOWNLOAD_LIMIT_BYTES * CHUNK_BUDGET_FRACTION)

    n_cols, n_rows = 1, 1
    while True:
        cw = math.ceil(width / n_cols)
        ch = math.ceil(height / n_rows)
        if _estimate_request_bytes(cw, ch, n_bands) <= budget:
            break
        # Split whichever axis is currently longer, so chunks stay
        # roughly square rather than degenerating into 1-pixel strips.
        if cw >= ch:
            n_cols += 1
        else:
            n_rows += 1
        if n_cols > width or n_rows > height:
            raise RuntimeError(
                f"Cannot fit a single pixel row/column of a "
                f"{width}x{height}x{n_bands} export under GEE's "
                f"{GEE_DOWNLOAD_LIMIT_BYTES}-byte ceiling."
            )

    cw = math.ceil(width / n_cols)
    ch = math.ceil(height / n_rows)
    chunks = []
    for row_off in range(0, height, ch):
        for col_off in range(0, width, cw):
            chunks.append((
                col_off, row_off,
                min(cw, width - col_off),
                min(ch, height - row_off),
            ))
    return chunks


def export_image_local(
    image: ee.Image,
    aoi: ee.Geometry,
    output_path: str,
    scale: int = SCALE,
    crs: str = None,
    crs_transform: list = None,
    band_names: list = None,
) -> str:
    """
    Download a GEE image directly to local disk as GeoTIFF.
    Use only for small AOIs during development (< 5 sq km).

    Args:
        image: clipped Sentinel-2 image (all 6 bands)
        aoi: region geometry
        output_path: local file path (include .tif)
        scale: resolution in meters
        crs, crs_transform: item 21 Phase A. Export on an explicit grid --
            the native Sentinel-2 UTM grid -- instead of the EPSG:4326
            lattice. Both or neither. When given, `aoi` should already be
            the lattice-aligned rectangle (see surface_fractions.grid), and
            `scale` is ignored because the transform carries it. When
            omitted, the call below is the original one, unchanged.
        band_names: names to stamp into the file. Defaults to BAND_NAMES;
            a multi-band input stack passes its own.

    Returns:
        Path to saved file
    """
    import geemap
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if (crs is None) != (crs_transform is None):
        raise ValueError("crs and crs_transform must be given together")

    if crs is not None:
        # Explicit-grid path. No chunking: the stitcher is built on the
        # EPSG:4326 global lattice and cannot be reused for a UTM grid.
        # Phase A AOIs (labelling sites, Dharavi) fit in one request; a
        # larger one fails loudly here rather than being silently resampled
        # onto the 4326 lattice.
        n_bands = len(image.bandNames().getInfo())
        width, height = (round(v) for v in
                         _explicit_grid_extent(aoi, crs, crs_transform))
        est = _estimate_request_bytes(width, height, n_bands)
        if est > GEE_DOWNLOAD_LIMIT_BYTES * CHUNK_BUDGET_FRACTION:
            raise RuntimeError(
                f"Explicit-grid export of {width}x{height}px x {n_bands} bands "
                f"(est. {est/1024/1024:.1f} MiB) exceeds the single-request "
                f"budget; chunking is only implemented for the EPSG:4326 path."
            )
        geemap.ee_export_image(
            image,
            filename=output_path,
            crs=crs,
            crs_transform=list(crs_transform),
            region=aoi,
            file_per_band=False,
        )
        _check_export_written(output_path, scale)
        stamp_band_descriptions(output_path, band_names)
        print(f"Image saved locally: {output_path}")
        return output_path

    # ── Decide single-request vs chunked ──
    # Bounds + band count come from GEE (two cheap metadata calls), so the
    # size estimate is real rather than assumed.
    coords = aoi.bounds().getInfo()["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    grid = _compute_export_grid(min(lons), min(lats), max(lons), max(lats), scale)
    n_bands = len(image.bandNames().getInfo())
    est = _estimate_request_bytes(grid["width"], grid["height"], n_bands)

    print(f"Export grid: {grid['width']}x{grid['height']}px x {n_bands} bands "
          f"-> est. GEE request size {est/1024/1024:.1f} MiB "
          f"(ceiling {GEE_DOWNLOAD_LIMIT_BYTES/1024/1024:.0f} MiB)")

    if est <= GEE_DOWNLOAD_LIMIT_BYTES * CHUNK_BUDGET_FRACTION:
        # Fits comfortably: take the ORIGINAL code path unchanged, so small
        # AOIs (every run this project has made until now) are byte-for-byte
        # unaffected by the chunking work.
        geemap.ee_export_image(
            image,
            filename=output_path,
            scale=scale,
            region=aoi,
            file_per_band=False,
        )
    else:
        _export_image_local_chunked(image, grid, n_bands, output_path, scale)

    # C4 / item 44: write the band names INTO the file, so the read boundary has
    # something real to check. Measured before building this: 150 of 150
    # existing raw.tif files report descriptions == (None,) * 6, because neither
    # geemap's export nor the chunked stitcher writes them. Without this stamp,
    # assert_band_order() could only ever return "unverifiable" and the item
    # would be decoration. Stamping is best-effort and never fails the export --
    # failing to annotate a good file must not discard it.
    if os.path.exists(output_path):
        stamp_band_descriptions(output_path, band_names)

    _check_export_written(output_path, scale)

    print(f"Image saved locally: {output_path}")
    return output_path


def _explicit_grid_extent(aoi, crs, crs_transform):
    """(width, height) in pixels of `aoi`'s bounds on an explicit grid."""
    coords = aoi.bounds(1, crs).getInfo()["coordinates"][0]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return ((max(xs) - min(xs)) / abs(crs_transform[0]),
            (max(ys) - min(ys)) / abs(crs_transform[4]))


def _check_export_written(output_path: str, scale) -> None:
    # geemap.ee_export_image() CATCHES its own download failures: it prints
    # "An error occurred while downloading." and returns normally, writing
    # nothing. Without this check the function then printed "Image saved
    # locally: <path>" for a file that does not exist, and the real failure
    # surfaced three steps later as an unrelated rasterio FileNotFoundError
    # in generate_rgb_preview_tiles(). Observed live on the Phase 12B
    # full-Mumbai run (943 km2), where the underlying cause was a hard GEE
    # limit: "Total request size (284642550 bytes) must be less than or
    # equal to 50331648 bytes."
    #
    # Fail loudly and attribute correctly instead -- degradation must be
    # visible, never silent.
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(
            f"GEE export produced no file at {output_path}. "
            f"geemap.ee_export_image() swallowed the underlying error "
            f"(check stdout above for 'An error occurred while "
            f"downloading'). The most common cause is exceeding GEE's "
            f"direct-download request-size ceiling (~48 MiB) for the "
            f"requested AOI at scale={scale}m -- a hard API limit, not a "
            f"tunable setting. A larger AOI needs a different export path "
            f"(batch export to Drive, or chunked per-tile download), not a "
            f"retry."
        )


def _export_image_local_chunked(image: "ee.Image", grid: dict, n_bands: int,
                                 output_path: str, scale: int) -> None:
    """
    Download an AOI too large for GEE's single-request ceiling as several
    sub-48-MiB requests, then stitch them into ONE GeoTIFF at output_path.

    Seam-free by construction, via the GLOBAL lattice rather than via
    per-request grid overrides.

    (Note: passing crs_transform + dimensions was tried first and is
    rejected by GEE itself -- "Cannot specify (bounding region,
    crs_transform/scale, dimensions) simultaneously" -- despite geemap's
    docstring implying region is merely ignored in that case. So each
    chunk instead uses the SAME `scale` + `region` call the working
    single-request path uses.)

    Alignment comes from _compute_export_grid()'s finding that GEE snaps
    every EPSG:4326 export to one global lattice anchored at (0,0). Each
    chunk's region is therefore built directly from integer lattice
    indices, so every chunk lands on that shared lattice and adjacent
    chunks share exact pixel edges -- no resampling, no fractional offset,
    no seam. Each region is inset a quarter-pixel from its lattice edges
    so that GEE's own floor/ceil snapping cannot land one pixel off due to
    float round-trip error; the resulting size is asserted against the
    requested size below.

    The stitched file keeps the same shape/CRS/transform a single-request
    export of the same AOI would have produced, so everything downstream
    (generate_rgb_preview_tiles, raster_info, and the Option A persistence
    files landcover_map_full.npy / waterway_dist_map_full.npy /
    raster_info.json) is unchanged and needs no chunk awareness at all.

    If ANY chunk fails, this raises. It never writes a partial raster --
    a half-downloaded mosaic that silently continued would be exactly the
    "plausible but wrong" failure mode this project forbids.
    """
    import shutil
    import tempfile

    import geemap
    import rasterio
    from rasterio.windows import Window

    px = grid["px"]
    chunks = _plan_export_chunks(grid["width"], grid["height"], n_bands)
    est_chunk = _estimate_request_bytes(chunks[0][2], chunks[0][3], n_bands)
    print(f"AOI exceeds GEE's single-request ceiling -- chunking into "
          f"{len(chunks)} sub-requests "
          f"(~{est_chunk/1024/1024:.1f} MiB each, largest chunk "
          f"{max(c[2] for c in chunks)}x{max(c[3] for c in chunks)}px).")

    tmpdir = tempfile.mkdtemp(prefix="gw_chunk_")
    profile = None
    try:
        chunk_files = []
        for i, (col_off, row_off, cw, ch) in enumerate(chunks, start=1):
            # This chunk's exact lattice indices, inset a quarter pixel so
            # GEE's floor/ceil snapping cannot round to a neighbouring
            # index through float round-trip error.
            xi0 = grid["x0"] + col_off
            yi1 = grid["y1"] - row_off
            region = ee.Geometry.Rectangle(
                [(xi0 + 0.25) * px,          # west
                 (yi1 - ch + 0.25) * px,     # south
                 (xi0 + cw - 0.25) * px,     # east
                 (yi1 - 0.25) * px],         # north
                proj="EPSG:4326", geodesic=False,
            )

            cpath = os.path.join(tmpdir, f"chunk_{i:04d}.tif")
            print(f"  chunk {i}/{len(chunks)}: {cw}x{ch}px at "
                  f"col={col_off} row={row_off} ...")
            geemap.ee_export_image(
                image,
                filename=cpath,
                scale=scale,
                region=region,
                file_per_band=False,
                verbose=False,
            )
            if not os.path.isfile(cpath) or os.path.getsize(cpath) == 0:
                raise RuntimeError(
                    f"Chunk {i}/{len(chunks)} ({cw}x{ch}px at col={col_off} "
                    f"row={row_off}) produced no file. geemap swallows its "
                    f"own download errors, so check stdout for 'An error "
                    f"occurred while downloading'. Aborting WITHOUT writing "
                    f"a partial raster."
                )
            with rasterio.open(cpath) as cs:
                if (cs.width, cs.height) != (cw, ch):
                    raise RuntimeError(
                        f"Chunk {i}/{len(chunks)} came back "
                        f"{cs.width}x{cs.height}px but {cw}x{ch}px was "
                        f"requested via crs_transform+dimensions. Stitching "
                        f"would misalign the mosaic; aborting."
                    )
                if profile is None:
                    profile = cs.profile.copy()
            chunk_files.append((cpath, col_off, row_off, cw, ch))

        # Stitch. Full-raster transform is the same lattice origin.
        profile.update(
            width=grid["width"],
            height=grid["height"],
            transform=rasterio.transform.Affine(
                px, 0.0, grid["west"], 0.0, -px, grid["north"]
            ),
            crs="EPSG:4326",
            count=n_bands,
        )
        # tiled/blockx/blocky from a small chunk can be invalid for the
        # full raster; let rasterio pick defaults.
        for k in ("tiled", "blockxsize", "blockysize", "compress"):
            profile.pop(k, None)

        tmp_out = output_path + ".partial"
        with rasterio.open(tmp_out, "w", **profile) as dst:
            for cpath, col_off, row_off, cw, ch in chunk_files:
                with rasterio.open(cpath) as cs:
                    dst.write(cs.read(), window=Window(col_off, row_off, cw, ch))
        # Only promote to the real path once every chunk is written.
        os.replace(tmp_out, output_path)
        print(f"Stitched {len(chunks)} chunks -> "
              f"{grid['width']}x{grid['height']}px GeoTIFF.")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def generate_tiles(image_path: str, output_dir: str, tile_size: int = TILE_SIZE) -> list:
    """
    Split a downloaded multi-band GeoTIFF into fixed-size training tiles.

    IMPORTANT: this is the TRAINING data path. Tiles are saved as .npy
    arrays holding all available bands (Blue, Green, Red, NIR, SWIR1,
    SWIR2) as float32 surface reflectance, with NO contrast stretch and
    NO 8-bit quantization. Both of those are lossy, visualization-only
    transforms that must not touch data the model actually trains on.

    If you need human-viewable RGB previews (for QA, overlays, or the
    frontend), use generate_rgb_preview_tiles() instead/in addition —
    that path still does the percentile stretch + 8-bit PNG save, but
    it is explicitly NOT the training data source anymore.

    Args:
        image_path: path to input multi-band GeoTIFF
        output_dir: directory to save tile .npy files
        tile_size: pixel size of each tile (default 512)

    Returns:
        List of saved tile .npy paths
    """
    import rasterio

    os.makedirs(output_dir, exist_ok=True)
    tile_paths = []

    with rasterio.open(image_path) as src:
        # C4 / item 44: verify against the FILE before reading a single pixel.
        # This is the training data path, so a wrong band order here would be
        # baked into every .npy tile the model is trained on. The previous
        # band-count check was a print() that execution ran straight past;
        # assert_band_order() raises on a wrong count and on a genuine order
        # mismatch, and reports "unverifiable" for files that carry no
        # descriptions rather than implying they were checked.
        band_order_verdict = assert_band_order(src, image_path)

        width = src.width
        height = src.height
        bands = src.count
        print(f"Image size: {width}x{height}, bands: {bands} "
              f"(band order: {band_order_verdict})")

        for row in range(0, height, tile_size):
            for col in range(0, width, tile_size):
                # Clamp to image bounds
                row_end = min(row + tile_size, height)
                col_end = min(col + tile_size, width)

                # Read tile data: shape (bands, H, W)
                tile_data = src.read(
                    window=rasterio.windows.Window(col, row, col_end - col, row_end - row)
                )

                # Keep ALL bands, as float32 reflectance, channel-last: (H, W, bands)
                multiband = np.transpose(tile_data, (1, 2, 0)).astype(np.float32)

                tile_filename = f"tile_{row}_{col}.npy"
                tile_path = os.path.join(output_dir, tile_filename)
                np.save(tile_path, multiband)
                tile_paths.append(tile_path)

    print(f"Generated {len(tile_paths)} multi-band training tiles → {output_dir}")
    return tile_paths


def generate_rgb_preview_tiles(image_path: str, output_dir: str, tile_size: int = TILE_SIZE):
    """
    Split a downloaded GeoTIFF into fixed-size RGB PNG tiles for VISUAL
    QA / overlay purposes ONLY. Not used as model training input.

    PHASE 2 CHANGE: now returns (tiles, raster_info) instead of a bare
    list of paths. Each tile dict carries its pixel offset within the
    FULL source raster, so downstream code (pipeline.py) can place each
    tile's SAM/inference results into a correctly-positioned full-AOI
    mosaic instead of only ever processing tiles[0].

    Returns:
        tiles: list of dicts, each:
            {"path": str, "col_off": int, "row_off": int,
             "width": int, "height": int}
        raster_info: dict describing the FULL source raster:
            {"width": int, "height": int,
             "bounds": (west, south, east, north), "crs": str}
    """
    import rasterio

    os.makedirs(output_dir, exist_ok=True)
    tiles = []

    with rasterio.open(image_path) as src:
        # C4 / item 44: this is the function that actually indexes with
        # RGB_BAND_INDICES, so it is the sharpest consumer of the assumption.
        # A silent R/B swap here reaches the frontend overlay and the
        # classifier input alike.
        band_order_verdict = assert_band_order(src, image_path)

        width = src.width
        height = src.height
        bands = src.count
        bounds = src.bounds

        raster_info = {
            "width": width,
            "height": height,
            "bounds": (bounds.left, bounds.bottom, bounds.right, bounds.top),
            "crs": str(src.crs),
            # Carried so a consumer can tell a verified read from an
            # unverifiable one, rather than assuming the check happened.
            "band_order": band_order_verdict,
            "band_names": list(BAND_NAMES),
        }

        for row in range(0, height, tile_size):
            for col in range(0, width, tile_size):
                row_end = min(row + tile_size, height)
                col_end = min(col + tile_size, width)
                w = col_end - col
                h = row_end - row

                tile_data = src.read(
                    window=rasterio.windows.Window(col, row, w, h)
                )

                if bands >= 3:
                    rgb = np.stack(
                        [
                            tile_data[RGB_BAND_INDICES["Red"]],
                            tile_data[RGB_BAND_INDICES["Green"]],
                            tile_data[RGB_BAND_INDICES["Blue"]],
                        ],
                        axis=-1,
                    )
                else:
                    rgb = np.stack([tile_data[0]] * 3, axis=-1)

                p2, p98 = np.percentile(rgb, (2, 98))
                if p98 > p2:
                    rgb = np.clip((rgb - p2) * 255.0 / (p98 - p2), 0, 255).astype(np.uint8)
                else:
                    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

                tile_img = Image.fromarray(rgb)
                tile_filename = f"tile_{row}_{col}.png"
                tile_path = os.path.join(output_dir, tile_filename)
                tile_img.save(tile_path)

                tiles.append({
                    "path": tile_path,
                    "col_off": col,
                    "row_off": row,
                    "width": w,
                    "height": h,
                })

    print(f"Generated {len(tiles)} RGB preview tiles → {output_dir} "
          f"(full raster {width}x{height}px)")
    return tiles, raster_info