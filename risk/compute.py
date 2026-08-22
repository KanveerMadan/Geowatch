"""
Phase 10A: risk computation.

Any future real risk computation (Phase 10B, once gates D/E are actually
passed -- see PROJECT_GATES.md) must propagate the exposure input's
`product_validation_status` field into its own output, e.g.:

    risk_output["exposure_product_validation_status"] = \
        exposure.get("product_validation_status")

This ensures Gate C's waiver (see exposure/compute.py's GATE_C_STATUS)
remains visible even in the most consequential output this system
produces, rather than silently disappearing two layers up the stack.

HARD RULE: this function returns a real numerical risk score ONLY when
hazard, exposure, AND a genuine externally-sourced vulnerability context
are all available. It NEVER fabricates vulnerability from imagery
(roofing appearance, building density, road access, OSM completeness,
or population density all explicitly forbidden per this project's
ethical constraints), and it NEVER uses a V=1.0 "reference scenario"
fallback dressed up as risk -- that was proposed and explicitly
REJECTED (see project decision log): multiplying by exactly 1.0 changes
nothing mathematically and would misrepresent an exposure number as a
risk number.

vulnerability.status = "not_calculated" is the CORRECT, PERMANENT
default for this phase -- not a placeholder to be filled in casually.
It remains not_calculated pending an explicit future decision (a
separate, fully-gated "Phase 10B") that requires: exposure validated
across multiple live runs, at least one real user finding exposure
output useful, and a written feasibility/license/ethics assessment of
one specific real vulnerability data source (e.g. INFORM) BEFORE any
integration code is written. See project decision log for the full
5-gate criteria. Do not build toward vulnerability integration in this
file without that explicit go/no-go having happened first.
"""


def compute_risk(hazard: dict = None, exposure: dict = None, vulnerability: dict = None) -> dict:
    """
    Args:
        hazard: a susceptibility/hazard block (e.g.
            susceptibility.pluvial, susceptibility.fluvial, or
            observed_inundation) for ONE evidence layer.
        exposure: output of exposure.compute.compute_exposure_for_layer()
            for that SAME evidence layer.
        vulnerability: real vulnerability context, or None. As of Phase
            10A, this will always be None/not_calculated -- see module
            docstring.

    Returns:
        dict with status="not_calculated" and an honest reason, unless
        all three inputs are genuinely available (which will not happen
        in Phase 10A, by design).
    """
    if hazard is None or hazard.get("status") not in ("applicable", "experimental", "available"):
        return {
            "status": "not_calculated",
            "reason": "Risk requires hazard evidence; hazard is unavailable "
                      "or not yet calculated for this evidence layer.",
        }

    if exposure is None or exposure.get("status") != "available":
        return {
            "status": "not_calculated",
            "reason": "Risk requires exposure; exposure is unavailable or "
                      "not yet calculated for this evidence layer.",
        }

    if vulnerability is None or vulnerability.get("status") != "available":
        return {
            "status": "not_calculated",
            "reason": "No validated, geographically appropriate, ethically "
                      "governed vulnerability dataset is currently configured. "
                      "Risk = Hazard x Exposure x Vulnerability requires a "
                      "real vulnerability input; this project does not use "
                      "V=1.0 fallbacks or imagery-derived vulnerability "
                      "proxies.",
        }

    # Phase 10B: vulnerability IS now available (INFORM Risk), but per
    # PROJECT_GATES.md Gate E's approved methodology, this phase deliberately
    # stops at producing vulnerability_context -- it does NOT define a
    # hazard x exposure x vulnerability fusion formula. Inventing one here
    # would repeat exactly the mistake already rejected once (the V=1.0
    # "reference scenario" proposal) -- a formula decided ad hoc while
    # coding, not through the same explicit methodology-first discipline
    # every other phase in this project has followed.
    return {
        "status": "not_calculated",
        "reason": "Hazard, exposure, and vulnerability are all now available "
                  "for this evidence layer, but a hazard x exposure x "
                  "vulnerability FUSION METHODOLOGY has not yet been defined "
                  "and approved. This is a deliberate, separate methodology "
                  "decision (see PROJECT_GATES.md) -- not started. Do not "
                  "invent a fusion formula ad hoc; it must be defined and "
                  "approved the same way Gate E defined the "
                  "vulnerability_context schema before any code was written.",
        "vulnerability_available": True,
        "exposure_product_validation_status": exposure.get("product_validation_status"),
    }