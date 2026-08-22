def test_inland_aoi_returns_nonzero_distance_not_zero():
    """
    Regression test for the filled-polygon-vs-boundary bug: an AOI deep
    inland (e.g. central Delhi, ~1000km from any coast) must NOT return
    distance_km=0.0. Confirmed live before this fix: Delhi, Dharavi, and
    Accra all returned identical 0.00km, which is only possible if
    distance was being measured against filled land area rather than
    the actual coastline boundary.
    """
    result = get_coastline_context(west=77.20, south=28.60, east=77.24, north=28.64)
    assert result["status"] == "available"
    # 1000km inland is far beyond the 50km search radius, so this
    # should hit the "nothing found nearby" branch entirely --
    # distance_km should be None, not a small/zero number.
    assert result["distance_km"] is None
    assert result["coastal_connectivity"] is False