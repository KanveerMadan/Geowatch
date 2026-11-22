"""Local QGIS fixture. All editable datasets live under pytest's temporary directory."""
import json
import os
from pathlib import Path
import shutil
import sys

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QAction, QMainWindow
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry,
                       QgsProject, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas, QgsAdvancedDigitizingDockWidget
from osgeo import gdal, ogr, osr

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.labelling.geowatch_item21.plugin import ReviewPlugin
from tools.labelling.geowatch_item21.editing import value
from tools.labelling.geowatch_item21.storage import Log


class Iface(QObject):
    projectRead = pyqtSignal()
    newProjectCreated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas(self.window)
        self.cad = QgsAdvancedDigitizingDockWidget(self.canvas, self.window)
        self.vertex = QAction(self.window)
        self.active = None

    def mainWindow(self): return self.window
    def mapCanvas(self): return self.canvas
    def activeLayer(self): return self.active
    def setActiveLayer(self, layer):
        self.active = layer
        self.canvas.setCurrentLayer(layer)
    def addDockWidget(self, area, w): self.window.addDockWidget(area, w)
    def removeDockWidget(self, w): self.window.removeDockWidget(w)
    def addPluginToMenu(self, *args): pass
    def removePluginMenu(self, *args): pass
    def cadDockWidget(self): return self.cad
    def actionVertexToolActiveLayer(self): return self.vertex
    def messageBar(self): return self
    def pushWarning(self, title, text): raise AssertionError(text)


def candidates(tile):
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(32734)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(tile/"prelabels.gpkg"))
    layer = ds.CreateLayer("built_source", sr, ogr.wkbPolygon)
    for k in ("class", "source", "source_id", "source_version", "candidate_id", "hint_only", "note"):
        layer.CreateField(ogr.FieldDefn(k, ogr.OFTInteger if k == "hint_only" else ogr.OFTString))
    for i, (ident, hint) in enumerate((("A", 0), ("B", 0), ("C", 0), ("D", 1))):
        feat = ogr.Feature(layer.GetLayerDefn())
        for k,v in dict(source="fixture", source_id=f"region/{i}", source_version="1", candidate_id=ident, hint_only=hint).items():
            feat.SetField(k,v)
        feat.SetField("class","built")
        x,y = 285002 + i*6, 6235810
        feat.SetGeometry(ogr.CreateGeometryFromWkt(f"POLYGON (({x} {y},{x+4} {y},{x+4} {y+4},{x} {y+4},{x} {y}))"))
        layer.CreateFeature(feat)
    ds = None


def run(tmp):
    tile = tmp/"PRACTICE_formal"
    source = Path(os.environ.get("GEOWATCH_PRACTICE_COPY", ROOT/"data/practice_tiles/PRACTICE_formal"))
    tile.mkdir()
    for k in ("metadata.json", "labels.gpkg"):
        shutil.copyfile(source/k, tile/k)
    if (source/"hr.tif").is_file():
        shutil.copyfile(source/"hr.tif", tile/"hr.tif")
    else:
        ds = gdal.GetDriverByName("GTiff").Create(str(tile/"hr.tif"), 200, 200, 3)
        sr = osr.SpatialReference()
        sr.ImportFromEPSG(32734)
        ds.SetProjection(sr.ExportToWkt())
        ds.SetGeoTransform((285000,1,0,6236000,0,-1))
        ds = None
    candidates(tile)
    p = QgsProject.instance()
    p.setFileName(str(tile/"label_project.qgz"))
    p.writeEntry("GeoWatch","/item21","practice")
    p.writeEntry("GeoWatch","/tile_id",tile.name)
    p.setCrs(QgsCoordinateReferenceSystem("EPSG:32734"))
    labels = QgsVectorLayer(str(tile/"labels.gpkg")+"|layername=labels","Labels","ogr")
    layer = QgsVectorLayer(str(tile/"prelabels.gpkg")+"|layername=built_source","Suggestions","ogr")
    for l, role in ((labels,"labels"),(layer,"candidate")):
        assert l.isValid()
        l.setCustomProperty("geowatch/role",role)
        p.addMapLayer(l)
    iface=Iface()
    iface.canvas.setDestinationCrs(labels.crs())
    plugin=ReviewPlugin(iface)
    plugin.log=Log(tmp/"profile-test/review.sqlite")
    plugin.initGui()
    assert plugin.labels is not None, plugin.status.text()
    original = labels.featureCount()
    assert not labels.isEditable() and len(plugin.pending()) == 3 and "D" not in plugin.candidates
    plugin.perform("next")
    assert plugin.current == "A"
    plugin.perform("accept")
    assert labels.featureCount() == original+1 and plugin.current == "B", plugin.status.text()
    one=next(f for f in labels.getFeatures() if value(f,"candidate_id")=="A")
    assert value(one,"provenance")=="prelabel_kept" and value(one,"source_id")=="region/0"
    plugin.perform("edit")
    fid=labels.selectedFeatureIds()[0]
    assert value(labels.getFeature(fid),"provenance")=="prelabel_kept"
    plugin.perform("class","paved")
    assert value(labels.getFeature(fid),"provenance")=="prelabel_edited"
    plugin.perform("next")
    plugin.perform("reject")
    assert not plugin.pending() and plugin.log.rejected(tile)=={"C"}
    plugin.perform("draw")
    sketch=QgsFeature()
    sketch.setGeometry(QgsGeometry.fromRect(QgsRectangle(285080,6235900,285086,6235906)))
    plugin.capture.digitizingCompleted.emit(sketch)
    hand=labels.getFeature(labels.selectedFeatureIds()[0])
    assert value(hand,"provenance")=="hand_drawn" and value(hand,"candidate_id")==""
    # Native imports must not gain or preserve copied origins, even with drawing active.
    unsafe=QgsFeature(hand)
    unsafe.setId(-1)
    assert labels.addFeature(unsafe)
    assert not value(labels.getFeature(unsafe.id()),"provenance")
    assert labels.deleteFeature(unsafe.id())
    plugin.perform("unlabelled")
    assert plugin.overlay is not None
    plugin.perform("unlabelled")
    assert not plugin.overlay
    assert labels.commitChanges(), labels.commitErrors()
    plugin.open_project()
    assert not plugin.pending()
    # Geometry change via a native editor after reopening is also tracked.
    assert labels.startEditing()
    one=next(f for f in labels.getFeatures() if value(f,"candidate_id")=="A")
    assert labels.changeGeometry(one.id(),sketch.geometry())
    assert value(labels.getFeature(one.id()),"provenance")=="prelabel_edited"
    assert labels.rollBack()
    p.setFileName(str(tmp/"validation"/"label_project.qgz"))
    plugin.open_project()
    assert plugin.tile is None and not plugin.candidates
    assert not p.layerTreeRoot().findLayer(layer.id()).isVisible()
    plugin.unload()
    p.clear()


if __name__ == "__main__":
    app=QgsApplication([],True)
    app.initQgis()
    run(Path(sys.argv[1]))
