"""
The flood_final event set: DEV (build / tune) and RESERVED (held out, scored
once after PREREGISTRATION.md is pushed). Rules and reasons: DECISIONS.md.

DEV  = the 29 clean batch-0 units (flood_learned.events.batch0)
     + DEV_NEW: AOIs of the 20 EMS activations whose references were built
       before the full-run brief (exposure 3), up to DEV_AOIS_PER_ACTIVATION
       qualifying AOIs each (most flooded cells first).
RESERVED = RESERVED_EMS (EMS activations chosen from product metadata only,
       exposure 2) + RESERVED_S1 (Sentinel-1 references at a town point and
       a date from general reporting, exposure 1). Nothing about a reserved
       event's reference, inputs or scores is read before the pre-registration
       is pushed.

Flood-type tags come from the activation text (rules: flood_learned/heldout/
select.py docstring); "compound" = the text names at least two of rain,
river, surge/waves. An event can carry more than one tag.
"""
from __future__ import annotations

# Up to 3 qualifying AOIs per DEV activation: AOIs of one activation are one
# storm (one cluster), so more than a few adds little independent
# information and costs ~8 min of input build each.
DEV_AOIS_PER_ACTIVATION = 3
# Reserved EMS activations: the 2 lowest-numbered AOIs with a DEL monitoring-0
# product (else GRA monitoring-0). Fixed from metadata; whether a box
# qualifies (>= 50/50) is decided once, at scoring.
RESERVED_AOIS_PER_ACTIVATION = 2

# DEV activations (opened). code -> (tags, region)
DEV_NEW = {
    "EMSR662": (("fluvial",), "africa"),
    "EMSR774": (("fluvial",), "americas"),
    "EMSR865": (("fluvial",), "americas"),
    "EMSR853": (("fluvial",), "americas"),
    "EMSR844": (("fluvial",), "southeast_asia"),
    "EMSR757": (("fluvial",), "europe_mediterranean"),
    "EMSR868": (("fluvial",), "europe_mediterranean"),
    "EMSR711": (("fluvial",), "europe_mediterranean"),
    "EMSR838": (("fluvial",), "south_asia"),                     # D2
    "EMSR779": (("waterlogging",), "africa"),
    "EMSR799": (("waterlogging",), "americas"),
    "EMSR870": (("flash_flood",), "americas"),
    "EMSR813": (("flash_flood",), "americas"),
    "EMSR770": (("flash_flood",), "europe_mediterranean"),
    "EMSR680": (("flash_flood",), "europe_mediterranean"),
    "EMSR776": (("pluvial",), "americas"),
    "EMSR694": (("pluvial",), "europe_mediterranean"),
    "EMSR935": (("pluvial",), "europe_mediterranean"),
}
# Opened but not used at all (DECISIONS.md D4, D5)
DEV_DROPPED = {
    "EMSR708": "same storm (Ciaran/Domingos, Nov 2023) as round-4b reserved calais_2023",
    "EMSR843": "no AOI qualifies (Seveso 33 flooded cells; Blevio none)",
}

# RESERVED EMS activations (metadata only). code -> (tags, region, quote)
RESERVED_EMS = {
    # fluvial
    "EMSR857": (("fluvial",), "africa", "Heavy rain started in December, caused several floods in Mozambique (Limpopo AOIs)"),
    "EMSR712": (("fluvial",), "europe_mediterranean", "flood events ... Lower Saxony (AOIs: Hase, Hunte, Weser rivers)"),
    "EMSR861": (("fluvial",), "europe_mediterranean", "a river overflow was forecast to affect the Guadalquivir River Basin"),
    # flash flood
    "EMSR845": (("flash_flood",), "americas", "heavy rains ... severe flooding and landslides ... mud and debris (Mexico)"),
    "EMSR850": (("flash_flood",), "europe_mediterranean", "heavy and moderate rainfall ... localized flooding, road blockages, landslides (Albania)"),
    "EMSR683": (("flash_flood",), "europe_mediterranean", "extreme weather Hans ... heavy rainfall will produce floods (Norwegian mountain valleys)"),
    "EMSR775": (("flash_flood",), "europe_mediterranean", "heavy rainfall ... floods and mass movements in many places in western Norway"),
    "EMSR841": (("flash_flood",), "europe_mediterranean", "a severe rainstorm and subsequent flooding ... entire villages were cut off"),
    "EMSR872": (("flash_flood",), "oceania", "heavy rains and strong winds ... landslides and flash floods (Chuuk)"),
    # pluvial (urban rain)
    "EMSR742": (("pluvial",), "europe_mediterranean", "most precipitation ... around Riga 87 mm to 193 mm ... resulting in flooded territories"),
    "EMSR790": (("pluvial",), "africa", "Tropical Cyclone GARANCE ... La Réunion (Saint-Denis)"),
    "EMSR780": (("pluvial",), "africa", "Tropical Cyclone CHIDO ... Mayotte (Dembeni)"),
    "EMSR930": (("pluvial",), "europe_mediterranean", "a storm ... affected the cities of Policoro and Scanzano Jonico"),
    # waterlogging
    "EMSR856": (("waterlogging",), "europe_mediterranean", "assess the areas covered by water (Velipoje, Skadar Lake, Buna lowlands)"),
    # coastal / compound
    "EMSR703": (("coastal",), "americas", "TC OTIS (Cat. 5) ... landfall over ... Acapulco ... floods and landslides"),
    "EMSR805": (("coastal",), "americas", "Tropical Cyclone Erick-25 ... coastal area of Guerrero"),
    "EMSR734": (("coastal", "compound"), "americas", "very heavy rainfall, strong winds and storm surge (Beryl)"),
    "EMSR781": (("coastal",), "africa", "TC CHIDO ... hurricane-force winds and torrential floods (Cabo Delgado)"),
    "EMSR793": (("coastal",), "africa", "TC Jude ... hurricane-force winds and torrential flooding (Nampula)"),
    "EMSR867": (("coastal",), "africa", "TC Gezani ... landfall near Toamasina"),
    "EMSR863": (("coastal",), "africa", "TC Fytia ... North West Madagascar"),
    "EMSR858": (("coastal", "compound"), "europe_mediterranean", "Extremely heavy rainfall ... very high waves of up to 6 metres (cyclone Harry)"),
    "EMSR864": (("flash_flood", "compound"), "europe_mediterranean", "heavy and persistent rainfall ... significant maritime agitation ... flash flood notification"),
}

# RESERVED Sentinel-1 events (round-4 S1 reference method; event dates outside
# Jan-Mar because that method's baseline is Jan-Mar of the event year).
# name -> (tags, region, [lon, lat] town point, event date, basis)
RESERVED_S1 = {
    "s1_assam_morigaon_2024": (("fluvial",), "south_asia", [92.34, 26.25], "2024-07-03",
                               "Brahmaputra floods, Morigaon district, early July 2024"),
    "s1_sunamganj_2024": (("fluvial",), "south_asia", [91.40, 25.07], "2024-06-19",
                          "Surma floods, Sunamganj, June 2024"),
    "s1_lokoja_2022": (("fluvial",), "africa", [6.74, 7.80], "2022-10-10",
                       "Niger-Benue floods at Lokoja, October 2022"),
    "s1_kelantan_2024": (("fluvial",), "southeast_asia", [102.10, 6.05], "2024-11-30",
                         "Kelantan river floods (Pasir Mas), Nov-Dec 2024"),
    "s1_tabasco_2020": (("fluvial",), "americas", [-92.93, 17.99], "2020-11-08",
                        "Grijalva floods at Villahermosa, Nov 2020 (rain + reservoir releases)"),
    "s1_yenagoa_2022": (("waterlogging",), "africa", [6.27, 4.93], "2022-10-15",
                        "prolonged Niger-delta flooding around Yenagoa, Oct 2022"),
}
# Dropped from RESERVED by the registry guard (DECISIONS.md D7):
#   EMSR768 (Kupa/Korana, Danube main basin = 6 DEV units), s1_bor_2024 (Nile main basin = kigali, EMSR662).
# Registry links the brief asks to accept (DECISIONS.md D6): South Asian
# monsoon-plain river events necessarily share the GBM basin / region with
# DEV units. Only exception-severity links (basin, region) are accepted, never
# block-severity ones (product, box, proximity, storm).
ACCEPTED_EXCEPTION_LINKS = {"s1_assam_morigaon_2024", "s1_sunamganj_2024"}
