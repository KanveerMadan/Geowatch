"""Build a local QGIS editing project for a permitted Item 21 tile.

Run with the Python distributed with QGIS. All providers are opened on temporary
copies while building. The only file published next to imagery is a new QGZ.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

from labelling.label_style import COLOURS
from tools.labelling.guard import authorize_tile


def _snapshot(directory, filename, stage):
    original = directory / filename
    if original.is_symlink():
        raise ValueError(f"Unexpected layer symlink: {filename}")
    shutil.copyfile(original, stage / filename)
    # Unsaved QGIS edit buffers are deliberately outside this process. A
    # committed WAL may contain the current schema when a local file is open.
    wal = directory / (filename + "-wal")
    if filename.endswith(".gpkg") and wal.is_file():
        shutil.copyfile(wal, stage / wal.name)


def _spatial_tables(path):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        return [row[0] for row in db.execute(
            "SELECT table_name FROM gpkg_geometry_columns ORDER BY table_name"
        )]


def _vector(path, name, role, table=None):
    from qgis.core import QgsVectorLayer
    if table and not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise ValueError(f"Unexpected GeoPackage layer name: {table!r}")
    uri = str(path) + (f"|layername={table}" if table else "")
    layer = QgsVectorLayer(uri, name, "ogr")
    if not layer.isValid():
        raise ValueError(f"QGIS cannot read {path.name} {table or ''}")
    layer.setCustomProperty("geowatch/role", role)
    if role in {"candidate", "hint", "tile"}:
        layer.setReadOnly()
    return layer


def _labels_style(layer):
    from labelling.common import load_config
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsEditorWidgetSetup, QgsFieldConstraints,
                           QgsFillSymbol, QgsPalLayerSettings, QgsRendererCategory,
                           QgsVectorLayerSimpleLabeling)
    from qgis.PyQt.QtGui import QColor

    config = load_config()["labels"]
    classes = config["scored"] + config["excluded"]
    categories = []
    for label in classes:
        rgb = COLOURS[label]
        symbol = QgsFillSymbol.createSimple({"color": rgb + ",90", "outline_color": rgb,
                                             "outline_width": "0.3"})
        categories.append(QgsRendererCategory(label, symbol, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer("label", categories))
    field = layer.fields().indexFromName("label")
    if field < 0:
        raise ValueError("labels layer is missing the legacy label field")
    layer.setEditorWidgetSetup(field, QgsEditorWidgetSetup("ValueMap", {"map": [{v: v} for v in classes]}))
    layer.setFieldConstraint(field, QgsFieldConstraints.ConstraintNotNull)
    for flag in ("shadow_partial", "rooftop_solar"):
        index = layer.fields().indexFromName(flag)
        if index < 0:
            raise ValueError(f"labels layer is missing {flag}")
        layer.setEditorWidgetSetup(index, QgsEditorWidgetSetup("CheckBox", {}))
    form = layer.editFormConfig()
    for name in ("provenance", "source", "source_id", "source_version", "candidate_id"):
        index = layer.fields().indexFromName(name)
        if index >= 0:
            form.setReadOnly(index, True)
    layer.setEditFormConfig(form)
    # Works on legacy label schemas before the user's first plugin edit.
    settings = QgsPalLayerSettings()
    settings.fieldName = """CASE attribute(@feature, 'provenance')
        WHEN 'prelabel_kept' THEN 'kept'
        WHEN 'prelabel_edited' THEN 'edited'
        WHEN 'hand_drawn' THEN 'hand drawn' END"""
    settings.isExpression = True
    style = settings.format()
    style.setSize(8)
    style.setColor(QColor("#14231d"))
    buffer = style.buffer()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("white"))
    style.setBuffer(buffer)
    settings.setFormat(style)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _suggestion_layer(path, table):
    from qgis.core import QgsFeatureRequest, QgsFillSymbol, QgsSingleSymbolRenderer
    layer = _vector(path, table.replace("_", " "), "candidate", table)
    required = {"class", "source", "source_id", "source_version", "candidate_id",
                "confidence", "needs_check", "hint_only", "note"}
    if not required.issubset(layer.fields().names()):
        raise ValueError(f"Candidate schema missing fields in {table}: {sorted(required - set(layer.fields().names()))}")
    # A mixed layer is displayed as hints only. The plugin also checks each row.
    flags = layer.uniqueValues(layer.fields().indexFromName("hint_only"))
    hint = table.startswith("hint_") or any(str(value).lower() not in {"0", "false"} for value in flags)
    role = "hint" if hint else "candidate"
    layer.setCustomProperty("geowatch/role", role)
    layer.setCustomProperty("geowatch/table", table)
    request = QgsFeatureRequest()
    request.setFlags(QgsFeatureRequest.NoGeometry)
    request.setSubsetOfAttributes(["class"], layer.fields())
    request.setLimit(1)
    first = next(layer.getFeatures(request), None)
    label = str(first["class"]) if first is not None else table.removeprefix("hint_").split("_")[0]
    colour = COLOURS.get(label, "131,95,45")
    props = {"style": "no" if not hint else "b_diagonal", "color": colour + ",85",
             "outline_color": colour + ",220", "outline_style": "dot" if hint else "dash",
             "outline_width": "0.35"}
    layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(props)))
    display = table.removeprefix("hint_").replace("_", " ")
    layer.setName(display)
    layer.setDisplayExpression('"class" || \' · \' || "source"')
    return layer, hint


def _write_project(stage, spec, purpose):
    from qgis.core import (Qgis, QgsBookmark, QgsCoordinateReferenceSystem, QgsFillSymbol,
                           QgsProject, QgsRasterLayer, QgsRectangle, QgsReferencedRectangle,
                           QgsSingleSymbolRenderer, QgsSnappingConfig)

    project = QgsProject()
    project.setFileName(str(stage / "label_project.qgz"))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setTitle("Item 21 · " + spec.tile_id)
    project.writeEntry("GeoWatch", "/item21", purpose)
    project.writeEntry("GeoWatch", "/tile_id", spec.tile_id)
    crs = QgsCoordinateReferenceSystem(spec.crs)
    project.setCrs(crs)
    extent = QgsReferencedRectangle(QgsRectangle(*spec.bounds), crs)
    project.viewSettings().setDefaultViewExtent(extent)
    bookmark = QgsBookmark()
    bookmark.setName("Whole tile · " + spec.tile_id)
    bookmark.setExtent(extent)
    project.bookmarkManager().addBookmark(bookmark)
    root = project.layerTreeRoot()

    def add(layer, tree=root, checked=True):
        project.addMapLayer(layer, False)
        node = tree.addLayer(layer)
        node.setItemVisibilityChecked(checked)
        node.setExpanded(False)

    try:
        labels = _vector(stage / "labels.gpkg", "Final labels", "labels", "labels")
        _labels_style(labels)
        add(labels)
        candidates = root.addGroup("Suggestions · review against imagery")
        hints = root.addGroup("Hints only")
        for table in _spatial_tables(stage / "prelabels.gpkg"):
            layer, hint = _suggestion_layer(stage / "prelabels.gpkg", table)
            add(layer, hints if hint else candidates, checked=layer.featureCount() > 0)
        hints.setItemVisibilityChecked(False)
        hints.setExpanded(False)
        if (stage / "sun.gpkg").is_file():
            for table in _spatial_tables(stage / "sun.gpkg"):
                layer = _vector(stage / "sun.gpkg", "Sun measurements", "sun", table)
                add(layer, checked=False)
        tile = _vector(stage / "tile.geojson", "Tile boundary", "tile")
        tile.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({
            "style": "no", "outline_color": "252,231,111", "outline_width": "0.35"})))
        add(tile)
        raster = QgsRasterLayer(str(stage / Path(spec.image).name), "High-resolution imagery", "gdal")
        if not raster.isValid():
            raise ValueError("QGIS cannot read the base imagery")
        raster.setCustomProperty("geowatch/role", "imagery")
        add(raster)

        snap = QgsSnappingConfig(project)
        snap.setEnabled(True)
        snap.setMode(Qgis.SnappingMode.AdvancedConfiguration)
        # Screen pixels keep precision consistent as the labeller zooms in.
        types = Qgis.SnappingType.Vertex | Qgis.SnappingType.Segment
        for vector in (labels, tile):
            snap.setIndividualLayerSettings(vector, QgsSnappingConfig.IndividualLayerSettings(
                True, types, 8, Qgis.MapToolUnit.Pixels))
        project.setSnappingConfig(snap)
        project.setTopologicalEditing(True)
        project.setAvoidIntersectionsMode(Qgis.AvoidIntersectionsMode.AvoidIntersectionsLayers)
        project.setAvoidIntersectionsLayers([labels])
        if not project.write():
            raise OSError(project.error())
    finally:
        project.clear()
    return stage / "label_project.qgz"


def build_project(tile_dir):
    """Authorize and create one new adjacent project using project-relative sources."""
    spec = authorize_tile(Path(tile_dir))
    tile = Path(spec.path)
    output = tile / "label_project.qgz"
    if output.exists():
        raise FileExistsError(output)
    import json
    purpose = "practice" if json.loads((tile / "metadata.json").read_text())["site"] == "practice" else "training"
    inputs = ["labels.gpkg", "prelabels.gpkg", "tile.geojson", Path(spec.image).name]
    if (tile / "sun.gpkg").is_file():
        inputs.append("sun.gpkg")
    with tempfile.TemporaryDirectory(prefix="gw-item21-project-") as tmp:
        stage = Path(tmp)
        for name in inputs:
            _snapshot(tile, name, stage)
        draft = _write_project(stage, spec, purpose)
        # Exclusive creation protects any project Kanveer already customised.
        with draft.open("rb") as src, output.open("xb") as dst:
            try:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            except BaseException:
                output.unlink(missing_ok=True)
                raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tile", type=Path)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app_bundle = Path(sys.executable).resolve().parents[2]
    if sys.platform == "darwin" and app_bundle.suffix == ".app":
        os.environ.setdefault("QGIS_PREFIX_PATH", str(app_bundle))
        resources = app_bundle / "Contents/Resources/qgis"
        os.environ.setdefault("PROJ_DATA", str(resources / "proj"))
        os.environ.setdefault("GDAL_DATA", str(resources / "gdal"))
    from qgis.core import QgsApplication
    with tempfile.TemporaryDirectory(prefix="gw-item21-profile-") as profile:
        os.environ["QGIS_CUSTOM_CONFIG_PATH"] = profile
        app = QgsApplication([], False)
        if os.environ.get("QGIS_PREFIX_PATH"):
            QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
        app.initQgis()
        try:
            print(build_project(args.tile))
        finally:
            app.exitQgis()


if __name__ == "__main__":
    main()
