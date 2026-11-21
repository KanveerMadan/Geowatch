"""
flood_round2 event set (DECISIONS.md R6–R8).

- DEV = flood_final DEV (67 units)
      + flood_final RESERVED units, now used (scored once on 2026-11-20). Flipped to dev, exposure 6 (R6).
      + DEV_EMS_R2: EMS activations that share a storm with an already-used unit, so they can never be reserved.
      + DEV_S1_R2: Sentinel-1 coastal cases for the coastal features and SFINCS.
- RESERVED = RESERVED_EMS_R2 (product metadata only, exposure 2)
      + RESERVED_S1_R2 (a town point and a date from general reporting, exposure 1).
  Nothing about a reserved unit's reference, inputs or scores is read before PREREGISTRATION_ROUND2.md is pushed.

Tags come from the activation text or the event's general description, by the
round-1 rules (flood_learned/heldout/select.py docstring).
- compound: a cyclone or storm whose text or reporting names at least two of surge, rain and river.
- snowmelt / glof / dam_breach: extra tags for M8 / M6 / M7. They are recorded, not scored as types this round.
"""
from __future__ import annotations

DEV_AOIS_PER_ACTIVATION = 3
RESERVED_AOIS_PER_ACTIVATION = 2

# DEV EMS activations (storm-linked to used units). code -> (tags, region, storm link)
DEV_EMS_R2 = {
    "EMSR764": (("flash_flood",), "europe_mediterranean", "Storm Boris, Sept 2024 (Nysa EMSR756 used in round 2)"),
    "EMSR761": (("fluvial",), "europe_mediterranean", "Storm Boris, Sept 2024"),
    "EMSR759": (("fluvial",), "europe_mediterranean", "Storm Boris, Sept 2024"),
    "EMSR762": (("fluvial",), "europe_mediterranean", "Storm Boris remnants, Emilia-Romagna, Sept 2024"),
    "EMSR705": (("flash_flood",), "europe_mediterranean", "Storm Ciaran, Nov 2023 (round-4b calais_2023 storm)"),
    "EMSR697": (("fluvial",), "europe_mediterranean", "Storm Daniel, Sept 2023 (volos DEV)"),
    "EMSR664": (("fluvial",), "europe_mediterranean", "Emilia-Romagna May 2023 (faenza EMSR659 used)"),
    "EMSR665": (("flash_flood",), "europe_mediterranean", "mid-May 2023 storm over Italy and the Balkans"),
}
# DEV Sentinel-1 coastal cases. name -> (tags, region, [lon, lat], date, basis)
DEV_S1_R2 = {
    "s1_ida_lafitte_2021": (("coastal", "compound"), "americas", [-90.11, 29.67], "2021-08-30",
                            "Hurricane Ida surge and rain, Lafitte / Jean Lafitte, Louisiana"),
    "s1_laura_cameron_2020": (("coastal",), "americas", [-93.33, 29.80], "2020-08-27",
                              "Hurricane Laura storm surge, Cameron Parish, Louisiana"),
    "s1_michael_mexicobeach_2018": (("coastal",), "americas", [-85.41, 29.94], "2018-10-10",
                                    "Hurricane Michael storm surge, Mexico Beach, Florida"),
    "s1_amphan_sundarbans_2020": (("coastal", "compound"), "south_asia", [88.80, 22.15], "2020-05-21",
                                  "Cyclone Amphan surge and rain, Gosaba / Sundarbans, West Bengal"),
    "s1_fani_puri_2019": (("coastal",), "south_asia", [85.83, 19.81], "2019-05-03",
                          "Cyclone Fani landfall and surge near Puri, Odisha"),
}

# RESERVED EMS activations (metadata only). code -> (tags, region, quote from the activation text)
RESERVED_EMS_R2 = {
    # river
    "EMSR866": (("fluvial",), "europe_mediterranean", "flood event forecast to hit the Bordeaux region, the Charente river basin and the Dronne river basin"),
    "EMSR860": (("fluvial",), "europe_mediterranean", "Storm Chandra ... flooding damage ... Graiguenamanagh (County Kilkenny)"),
    "EMSR849": (("fluvial",), "europe_mediterranean", "Storm Claudia affected Ireland, causing floods"),
    "EMSR855": (("fluvial",), "europe_mediterranean", "Heavy rainfall ... Lazio ... the Aniene River has reached"),
    "EMSR854": (("fluvial",), "europe_mediterranean", "EFAS early warning on flood risk ... upper catchment of the Neretva River"),
    "EMSR797": (("fluvial",), "europe_mediterranean", "a flood was forecast to hit areas in Northern Bosnia-Herzegovina"),
    "EMSR794": (("fluvial",), "europe_mediterranean", "extraordinary volume situations ... reservoirs in the Tajo River basin"),
    "EMSR728": (("fluvial",), "europe_mediterranean", "continuous rain ... Southern and Eastern Germany"),
    "EMSR722": (("fluvial",), "europe_mediterranean", "flood event was reported affecting Saarland region"),
    "EMSR698": (("fluvial",), "europe_mediterranean", "extensive flooding is forecast to hit Central Scotland"),
    "EMSR684": (("fluvial",), "europe_mediterranean", "risk of flooding in several areas of central Sweden due to heavy rainfall"),
    "EMSR668": (("fluvial", "snowmelt"), "europe_mediterranean", "ongoing spring flood ... due to snow melt"),
    "EMSR657": (("fluvial", "snowmelt"), "europe_mediterranean", "flood due to melted snow and ice, as well as precipitation ... Daugava river valley"),
    "EMSR871": (("fluvial",), "europe_mediterranean", "heavy rain ... caused a rise in river water levels"),
    "EMSR783": (("fluvial",), "europe_mediterranean", "severe flooding is reported in North West Scotland (Western Cairngorms)"),
    # waterlogging
    "EMSR772": (("waterlogging",), "africa", "floods in Cameroon affected departments of Logone et Chari and Mayo Danay ... as of 25 September"),
    # rain / urban
    "EMSR721": (("pluvial",), "europe_mediterranean", "heavy thunderstorms, in Lombardy and Milan ... difficulties in the city's secondary network"),
    "EMSR789": (("pluvial",), "americas", "heavy rainfall affected especially western and coastal Ecuador causing floods"),
    # flash
    "EMSR927": (("flash_flood", "glof"), "south_asia", "a flash flood reportedly triggered by a Glacial Lake Outburst Flood (GLOF) in Nepal"),
    "EMSR802": (("flash_flood",), "europe_mediterranean", "a major flood is reported to have affected Covasna and Brasov counties"),
    "EMSR795": (("flash_flood",), "europe_mediterranean", "The Rimaggio River has flooded Sesto Fiorentino"),
    "EMSR750": (("flash_flood", "dam_breach"), "africa", "the collapse of Arba'at Dam ... flash flooding that affected 20 villages"),
    # compound
    "EMSR663": (("compound",), "africa", "Following Cyclone Freddy ... communities ... impacted by floods"),
}
# RESERVED Sentinel-1 events (a town point and a date from general reporting).
RESERVED_S1_R2 = {
    # coastal (+ compound where surge and rain are both reported)
    "s1_helene_steinhatchee_2024": (("coastal", "compound"), "americas", [-83.39, 29.67], "2024-09-27",
                                    "Hurricane Helene storm surge and rain, Steinhatchee / Keaton Beach, Florida Big Bend"),
    "s1_remal_satkhira_2024": (("coastal", "compound"), "south_asia", [89.10, 22.33], "2024-05-27",
                               "Cyclone Remal surge and rain, Shyamnagar, Satkhira, Bangladesh"),
    "s1_biparjoy_jakhau_2023": (("coastal",), "south_asia", [68.72, 23.22], "2023-06-16",
                                "Cyclone Biparjoy landfall and coastal flooding, Jakhau, Kutch, Gujarat"),
    "s1_francine_terrebonne_2024": (("coastal", "compound"), "americas", [-90.66, 29.25], "2024-09-12",
                                    "Hurricane Francine surge and rain, lower Terrebonne Parish, Louisiana"),
    "s1_dana_kendrapara_2024": (("coastal", "compound"), "south_asia", [86.95, 20.65], "2024-10-25",
                                "Cyclone Dana surge and heavy rain, Kendrapara / Bhitarkanika, Odisha"),
    # waterlogging (prolonged standing water)
    "s1_ndjamena_2024": (("waterlogging",), "africa", [15.05, 12.10], "2024-10-15",
                         "prolonged Chari / Logone flooding around N'Djamena, Oct 2024"),
    "s1_jowhar_2023": (("waterlogging",), "africa", [45.50, 2.78], "2023-11-20",
                       "prolonged Shabelle flooding around Jowhar, Somalia, Nov 2023 (El Nino rains)"),
    "s1_ubon_2022": (("waterlogging",), "southeast_asia", [104.87, 15.24], "2022-10-05",
                     "prolonged Mun River flooding at Ubon Ratchathani, Oct 2022"),
    "s1_garsen_2023": (("waterlogging",), "africa", [40.12, -2.27], "2023-12-01",
                       "prolonged Tana River delta flooding around Garsen, Kenya, Nov-Dec 2023"),
    "s1_sukhothai_2024": (("waterlogging",), "southeast_asia", [99.82, 17.01], "2024-09-01",
                          "prolonged Yom River flooding at Sukhothai, Thailand, late Aug-Sep 2024"),
    # rain / urban (S1 sees little among buildings: these may not qualify; R8)
    "s1_jeddah_2022": (("pluvial",), "africa_west_asia", [39.20, 21.55], "2022-11-24",
                       "torrential rain flooding in Jeddah, Saudi Arabia, 24 Nov 2022"),
    "s1_kinshasa_2022": (("pluvial",), "africa", [15.31, -4.38], "2022-12-13",
                         "heavy-rain flooding in Kinshasa, DR Congo, 13 Dec 2022"),
    # flash
    "s1_baghlan_2024": (("flash_flood",), "south_asia", [68.70, 36.13], "2024-05-11",
                        "flash floods in Baghlan province, Afghanistan, 10-11 May 2024"),
}
ACCEPTED_EXCEPTION_LINKS = {}
# R7: a reserved unit whose only links to DEV are main_basin links (no
# sub_basin, box, proximity, alias or storm link), each to a unit of another
# storm cluster more than MAIN_BASIN_MIN_KM away, is kept. Continental basins
# (Danube, Rhine, Ganges-Brahmaputra) put events hundreds of km and years apart
# in one "main basin"; that shares no water, storm or reference with a
# within-box ranking test.
MAIN_BASIN_MIN_KM = 100.0
