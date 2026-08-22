import json
import glob
import os

def find_latest_run(label_prefix):
    """Find the most recently created run directory matching a label prefix."""
    candidates = glob.glob(f"data/pipeline_runs/{label_prefix}*")
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)

def check_run(label_prefix, aoi_name):
    run_dir = find_latest_run(label_prefix)
    if not run_dir:
        print(f"\n{'=' * 72}\n{aoi_name}: NO RUN FOUND matching '{label_prefix}'\n{'=' * 72}")
        return

    result_path = os.path.join(run_dir, "result.json")
    if not os.path.exists(result_path):
        print(f"\n{'=' * 72}\n{aoi_name}: run dir exists but no result.json ({run_dir})\n{'=' * 72}")
        return

    with open(result_path) as f:
        data = json.load(f)

    print(f"\n{'=' * 72}\n{aoi_name}  ({run_dir})\n{'=' * 72}")

    # 1. Population consistency across all 5 evidence layers
    print("\n--- Population per evidence layer (should ALL match) ---")
    pops = {}
    for layer, exp in data.get("exposure", {}).get("by_evidence_layer", {}).items():
        pop = exp.get("components", {}).get("population", {}).get("estimated_population")
        pops[layer] = pop
        print(f"  {layer}: {pop}")

    unique_vals = set(v for v in pops.values() if v is not None)
    if len(unique_vals) <= 1 and len(pops) > 0:
        print("  ✅ CONSISTENT across all layers")
    else:
        print(f"  ❌ INCONSISTENT — found {len(unique_vals)} distinct values: {unique_vals}")

    # 2. Facilities status (the thing we're actually re-testing)
    print("\n--- Facilities status ---")
    first_layer = next(iter(data.get("exposure", {}).get("by_evidence_layer", {}).values()), {})
    facilities_component = first_layer.get("components", {}).get("facilities", {})
    fac_status = facilities_component.get("status")
    fac_count = facilities_component.get("count", 0)
    fac_error = facilities_component.get("error")
    print(f"  status: {fac_status}")
    print(f"  count: {fac_count}")
    if fac_error:
        print(f"  error: {fac_error}")
    if fac_status == "available":
        print("  ✅ Facilities fetch succeeded (retry logic worked or wasn't needed this time)")
    else:
        print("  ⚠️  Facilities still unavailable — check error above; may be a persistent "
              "Overpass outage rather than a code issue at this point")

    # 3. Built-up cross-check sanity
    print("\n--- Built-up (GeoWatch vs GHSL) ---")
    builtup = first_layer.get("components", {}).get("built_up", {})
    print(f"  GeoWatch model built-up %: {builtup.get('geowatch_model_builtup_pct')}")
    print(f"  GHSL reference source: {builtup.get('global_reference_source')}")
    print(f"  GHSL status: {builtup.get('status')}")

    # 4. Vulnerability / Risk gating
    print("\n--- Vulnerability / Risk (should both be not_calculated) ---")
    vuln_status = data.get("vulnerability", {}).get("status")
    risk_status = data.get("risk", {}).get("status")
    print(f"  vulnerability.status: {vuln_status}")
    print(f"  risk.status: {risk_status}")
    if vuln_status == "not_calculated" and risk_status == "not_calculated":
        print("  ✅ Correctly gated — no fabricated risk score")
    else:
        print("  ❌ UNEXPECTED — vulnerability or risk is not 'not_calculated', investigate immediately")

    # 5. Never-merged-layers structural check
    print("\n--- Evidence layers present (should be 5, never merged) ---")
    layer_keys = list(data.get("exposure", {}).get("by_evidence_layer", {}).keys())
    print(f"  {layer_keys}")
    if set(layer_keys) == {"pluvial", "fluvial", "coastal", "flash_flood", "waterlogging"}:
        print("  ✅ All 5 layers present and separate")
    else:
        print(f"  ❌ Unexpected layer set")


if __name__ == "__main__":
    check_run("dharavi_phase10a_final", "DHARAVI")
    check_run("delhi_phase10a_final", "DELHI")