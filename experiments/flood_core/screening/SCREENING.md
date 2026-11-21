# Screening: Valencia (DANA 2024) and Volos (Storm Daniel 2023) as first real development cases

**Date:** 2026-11-01. Both are **development** units (registry exposure 5–6; never test events). Only cached EMS layers already read by earlier rounds, Earth Engine input statistics (MERIT `upa`, HydroBASINS) and public sources were used. **Nothing was scored.** Outputs: `ems_screen_output.txt` and `catchments_output.txt`, produced by `ems_screen.py` and `catchments.py`.

## Volos: does not pass
| Item | Finding (source) |
|---|---|
| Reference coverage | EMSR692 has **no AOI over Volos city**. AOI01 "Magnesia" is a 9,613 km² regional extent. Its monitoring-3 layer (WorldView-3, 2023-09-09 09:31) maps 283.5 km² "Flooded area" with bounds 21.74–22.33° E, which is the Thessaly plain (Karditsa/Palamas), not Volos (22.94° E) (EMS activation record, cached layer) |
| Round history | Round 2's town-centred Volos box held **0 flooded cells**. Rounds 3/4's flood-centred box moved to **Palamas** (39.448 N, 22.069 E), the C72 issue. Inside the Volos town box: **0.0 km²** Flooded area and **0.0 km²** Flood trace (cached layer) |
| Mechanism at the reference | Plain flooding of the Pineios/Enipeas system, monitored by EMS AOIs 02–07 from 10 to 22 Sep 2023 (multi-day, large basin) |
| Consequence | The proposed "short steep torrents onto a coastal city" case has **no reference**. The referenced flood is a large-river plain flood that needs nested inflow boundaries and levee information (supplement §5). **Not a first case.** It could later serve a nested-domain test. |

## Valencia (Horta Sud): passes, with stated gaps
| Item | Finding (source) |
|---|---|
| Catchment | MERIT `upa` max near Paiporta **413 km²**, near the Albufera outlet **421 km²**. The round-4 box centre (−0.498, 39.447) reads 309 km² and may sit on the adjacent **Poçalet–Saleta** ravines; the domain must contain both systems (catchments_output.txt; Vallés-Morán 2025). HydroBASINS level 12 puts the Paiporta point in a **Turia** sub-basin (UP_AREA 6,674 km²), which is wrong for the Poyo: **delineate from the DEM, not HydroBASINS** |
| Upstream boundary | None needed: the Poyo headwaters are inside a ~420 km² domain. The **Turia new channel** (`upa` ≈ 6,199 km²) bounds the area to the north. Whether it overtopped is **unverified**, so treat it as a closed wall with a sensitivity run |
| Downstream boundary | **Albufera lagoon.** The level rose about **1.0 m** on 29 Oct (gauge 10 → 110 cm; gauge datum not found), about **120 hm³** in a day. The sea outlets ("golas") of El Pujol and Perellonet were opened (times not found) (Ajuntament de València; Valencia Plaza; Alicante Plaza). Include the lagoon in the domain, with the golas as the sea boundary, scenarios {closed, open}. The **datum** between lagoon gauge, DEM (EGM2008) and sea level is **unresolved**, and P0b-3 shows a 1 m offset against a level boundary is the largest systematic effect |
| Rainfall forcing | Turís 771.8 mm / 24 h and 184.6 mm / 1 h (AEMET, via secondary sources). IMERG's 0.1° cells cannot resolve this. Use IMERG plus a gauge-informed bracket scenario; AEMET gauge or radar access is **not verified** |
| Infrastructure | The **V-31 motorway** embankment caused backwater upstream (Vallés-Morán 2025, 2D model). There are the A-7 and rail embankments, and bridges and culverts the 30 m DEM cannot represent, so run a crossings-open/closed scenario. Urban drains are small next to Poyo flows (gauge 2,282 m³/s at 18:55, then the sensor failed; CHJ preliminary models > 3,500 m³/s downstream). The drainage scenario matters for ponding duration, not the peak |
| Dynamics | Under 1 h response from headwaters to towns; speeds up to 8 m/s and depths > 4 m in urban areas (Vallés-Morán 2025). The first Paiporta overflows came from the **Horteta and Gallego** tributary ravines (TETIS thesis, UPV). There is no gauge on the tributaries (court resolution, via Maldita) |
| Reference timing | **AOI03 Horta Sud DEL m0:** GeoEye-1/WorldView-2, **2024-10-31 10:22**, about 40 h after the evening peak of 29 Oct. **Flooded area 0.84 km²** against **Flood trace 23.22 km²**: the product is mostly a **maximum-extent proxy** (mud/debris traces), with a small residual-water component. **AOI01 province DEL m0** adds **Landsat-8 2024-10-30 10:37** (~16 h after the peak), S2 31 Oct 10:51 and S1 31 Oct 18:02: a second time and sensor (layer **not yet downloaded**) |
| Comparison target (supplement §3) | model **hmax** ↔ trace ∪ flooded (maximum-extent proxy; traces have their own detection limits); model state at 31 Oct 10:22 ↔ Flooded area only; model state at 30 Oct 10:37 ↔ AOI01 Landsat (after download) |

## Dubai
Kept **diagnostic only**, as instructed: an arid urban case for SAR four-state observations. No model run is planned.

Sources:
- [Vallés-Morán 2025 summary (UPV/IIAMA)](https://www.eurekalert.org/news-releases/1116573)
- [Maldita, Poyo gauge data](https://maldita.es/clima/20241107/datos-rambla-poyo-dana-valencia/)
- [Ajuntament de València, Albufera recovery plan](https://www.valencia.es/cas/actualidad/-/content/plan-recuperaci%C3%B3n-albufera-dana-1)
- [Valencia Plaza](https://valenciaplaza.com/lalbufera-valencia-playas-alteradas-dana)
- [Alicante Plaza](https://alicanteplaza.es/alicanteplaza/laalbuferaarrastraelretodemejorarsusaguasagravadotraseldesastredeladana1)
- [AEMET figures via El Debate](https://www.eldebate.com/sociedad/sociedad-medio-ambiente/20241129/primer-informe-aemet-mes-despues-dana-cayeron-621-litros-metro-cuadrado-seis-horas_249313_amp.html)
- [Rambla del Poyo](https://en.wikipedia.org/wiki/Rambla_del_Poyo)
