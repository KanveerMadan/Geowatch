"""
Write a GeoPackage layer with a QGIS style stored as its DEFAULT style.

QGIS reads a GeoPackage's `layer_styles` table on open and applies the row
flagged useAsDefault -- so dropdowns (Value Map), checkboxes and colours
appear without loading a .qml by hand. Used for the strata layers
(labelling/strata_rule.py) and the label layers (labelling/label_style.py).
"""

from __future__ import annotations

import os
import sqlite3


def write_gpkg(path: str, gdf, layer: str, qml: str, geometry_type: str | None = None) -> str:
    """Write `gdf` as `layer` (replacing any existing file) and store `qml` as
    the layer's default style. `geometry_type` is needed for an EMPTY layer,
    whose type cannot be inferred from features."""
    import pyogrio
    if os.path.exists(path):
        os.remove(path)
    kw = {"geometry_type": geometry_type} if geometry_type else {}
    pyogrio.write_dataframe(gdf, path, layer=layer, driver="GPKG", **kw)
    con = sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE layer_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), f_table_schema TEXT(256),
            f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
            styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30),
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        geom_col = con.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?",
                               (layer,)).fetchone()[0]
        con.execute("""INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name,
            f_geometry_column, styleName, styleQML, styleSLD, useAsDefault, description, owner)
            VALUES ('', '', ?, ?, ?, ?, '', 1, 'item 21 style (default)', '')""",
                    (layer, geom_col, layer, qml))
        con.execute("""INSERT INTO gpkg_contents (table_name, data_type, identifier, description)
            VALUES ('layer_styles', 'attributes', 'layer_styles', '')""")
        con.commit()
    finally:
        con.close()
    return path
