"""Keyboard-first Item 21 review in a registered training or practice project."""
import json
import os
from pathlib import Path
import subprocess
import sys

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import QColor, QKeySequence
from qgis.PyQt.QtWidgets import (QAction, QDockWidget, QFileDialog, QGridLayout, QInputDialog,
                                  QLabel, QMessageBox, QPushButton, QWidget)
from qgis.gui import QgsMapToolCapture, QgsMapToolDigitizeFeature
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsProject,
                       QgsProviderRegistry, QgsRectangle, QgsVectorLayer)

from .editing import TRACE, assign, command, copy_candidate, mark_change, prepare_schema, value
from .storage import Log, timer

ROOT = Path(__file__).resolve().parents[3]
# The documented profile symlink retains the versioned worktree and its frozen guard.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.labelling.guard import authorize_tile


CLASSES = ("built", "paved", "bare", "vegetation", "water", "mixed_water_vegetation",
           "snow_ice", "solar", "shadow_full", "unsure")
SPEC = (("Previous", "[", "prev"), ("Next", "]", "next"),
        ("Accept", "A", "accept"), ("Accept and edit", "E", "edit"),
        ("Reject", "R", "reject"), ("Draw new", "D", "draw"),
        ("Unlabelled area", "U", "unlabelled"), ("Start / stop timer", "T", "time"),
        ("Mark tile done", "", "done"), ("Reopen rejection", "", "reopen"),
        ("Edit selected label form", "F", "form"))


def verify_source(layer, path, expected_name=None):
    parts = QgsProviderRegistry.instance().decodeUri(layer.providerType(), layer.source())
    if layer.providerType() != "ogr" or Path(parts.get("path") or "").resolve() != path:
        raise ValueError(f"A project layer points outside {path.name}. Reopen the generated project.")
    if expected_name and (parts.get("layerName") or parts.get("layername")) != expected_name:
        raise ValueError(f"The editable layer must be the {expected_name} table.")


class ReviewPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.project = QgsProject.instance()
        self.dock = self.labels = self.tile = self.overlay = self.current = None
        self.candidates = {}
        self.actions = []
        self.signals = []
        self.number = "built"
        self.capture = None
        self.copying = False
        self.authored = set()
        self.log = Log(Path(QgsApplication.qgisSettingsDirPath())/"geowatch/item21_review.sqlite")

    def initGui(self):
        self.dock = QDockWidget("GeoWatch · Item 21", self.iface.mainWindow())
        self.dock.setObjectName("GeoWatchItem21Review")
        self.panel = QWidget()
        layout = QGridLayout(self.panel)
        self.status = QLabel("Open a generated Item 21 training or practice project.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status, 0, 0, 1, 2)
        for i, (name, key, code) in enumerate(SPEC):
            button = QPushButton(f"{name} [{key}]" if key else name)
            button.clicked.connect(lambda checked=False, c=code: self.perform(c))
            layout.addWidget(button, 1+i//2, i%2)
            if key:
                self.shortcut(key, lambda c=code: self.perform(c))
        for i, label in enumerate(CLASSES):
            self.shortcut(str((i+1)%10), lambda x=label: self.perform("class", x))
        legend = QLabel("1 built  ·  2 paved  ·  3 bare  ·  4 vegetation  ·  5 water\n"
                        "6 mixed water/vegetation  ·  7 snow/ice  ·  8 solar  ·  9 full shadow  ·  0 unsure")
        legend.setWordWrap(True)
        layout.addWidget(legend, 7, 0, 1, 2)
        self.dock.setWidget(self.panel)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.menu = self.dock.toggleViewAction()
        self.iface.addPluginToMenu("GeoWatch", self.menu)
        self.dock.visibilityChanged.connect(self.enable_keys)
        self.iface.projectRead.connect(self.open_project)
        self.iface.newProjectCreated.connect(self.open_project)
        self.open_project()
        if self.tile is None:
            self.dock.hide()

    def shortcut(self, key, fn):
        a = QAction(self.panel)
        a.setShortcut(QKeySequence(key))
        a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        a.triggered.connect(lambda checked=False: fn())
        self.iface.mapCanvas().addAction(a)
        self.panel.addAction(a)
        self.actions.append(a)

    def enable_keys(self, visible):
        for action in self.actions:
            action.setEnabled(bool(visible and self.labels is not None))

    def bind(self, signal, slot):
        signal.connect(slot)
        self.signals.append((signal, slot))

    def detach(self):
        for signal, slot in self.signals:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self.signals.clear()
        if self.capture is not None:
            self.iface.mapCanvas().unsetMapTool(self.capture)
            self.capture.deleteLater()
        self.capture = None
        self.copying = False
        self.authored = set()
        self.labels = self.tile = self.overlay = self.current = None
        self.candidates.clear()

    def hide_suggestions(self):
        # Do not read feature data while handling a refused or mismatched project.
        root = self.project.layerTreeRoot()
        for layer in self.project.mapLayers().values():
            if layer.customProperty("geowatch/role", "") in ("candidate", "hint"):
                node = root.findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(False)

    def open_project(self, *args):
        self.detach()
        kind = self.project.readEntry("GeoWatch", "/item21", "")[0]
        if kind not in ("training", "practice"):
            self.hide_suggestions()
            self.status.setText("Open a generated Item 21 training or practice project.")
            self.enable_keys(False)
            return
        try:
            tile = authorize_tile(Path(self.project.fileName()).parent)
            if self.project.readEntry("GeoWatch", "/tile_id", "")[0] != tile.tile_id:
                raise ValueError("The project's tile ID differs from its registered folder.")
            labels = []
            candidates = {}
            for layer in self.project.mapLayers().values():
                role = layer.customProperty("geowatch/role", "")
                if role == "labels":
                    verify_source(layer, tile.path/"labels.gpkg", "labels")
                    labels.append(layer)
                if role != "candidate":
                    continue
                verify_source(layer, tile.path/"prelabels.gpkg")
                if not layer.isValid() or layer.crs().authid() != tile.crs:
                    raise ValueError("A candidate layer has missing or mismatched tile coordinates.")
                for f in layer.getFeatures():
                    if value(f, "hint_only").lower() not in ("false", "0"):
                        continue
                    cid = value(f, "candidate_id")
                    if not cid or cid in candidates:
                        raise ValueError("Missing or repeated candidate_id. Regenerate the suggestions.")
                    candidates[cid] = (layer, f.id())
            if len(labels) != 1 or not labels[0].isValid() or labels[0].crs().authid() != tile.crs:
                raise ValueError("The project needs its own tile's editable labels layer in the tile CRS.")
            self.labels, self.tile, self.candidates = labels[0], tile, candidates
            self.bind(self.labels.geometryChanged, self.changed_geometry)
            self.bind(self.labels.attributeValueChanged, self.changed_attribute)
            self.bind(self.labels.featureAdded, self.added)

            self.status.setText(f"{tile.tile_id} · {len(candidates)} suggestions. Press ] to inspect.")
            self.enable_keys(self.dock.isVisible())
        except Exception as exc:
            self.hide_suggestions()
            self.detach()
            self.enable_keys(False)
            self.status.setText(f"Review unavailable: {exc}")

    def changed_geometry(self, fid, geometry):
        mark_change(self.labels, fid, self.candidates, geometry=geometry)

    def changed_attribute(self, fid, index, new):
        if self.labels.fields()[index].name() == "label":
            mark_change(self.labels, fid, self.candidates, field="label", new=new)

    def added(self, fid):
        if self.copying:
            self.authored.add(fid)
            return
        if fid in self.authored or self.labels.fields().indexOf("provenance") < 0:
            return
        # Native paste/duplicate is not evidence of a human trace. Keep its origin
        # unknown; the final QC gate requires an explicit reviewed origin.
        f = self.labels.getFeature(fid)
        for k in TRACE:
            if value(f, k):
                assign(self.labels, fid, k, None)

    def pending(self):
        accepted = {value(f, "candidate_id") for f in self.labels.getFeatures()}
        rejected = self.log.rejected(self.tile.path)
        return [k for k in sorted(self.candidates) if k not in accepted and k not in rejected]

    def browse(self, direction):
        import bisect
        available = self.pending()
        if not available:
            self.current = None
            self.status.setText("No unchecked suggestions. Review gaps and mark the tile done.")
            return
        if self.current is None:
            i = 0 if direction == 1 else -1
        elif direction == 1:
            i = bisect.bisect_right(available, self.current)
        else:
            i = bisect.bisect_left(available, self.current)-1
        self.current = available[i % len(available)]
        layer, fid = self.candidates[self.current]
        for other in {x[0] for x in self.candidates.values()}:
            other.removeSelection()
        layer.selectByIds([fid])
        node = self.project.layerTreeRoot().findLayer(layer.id())
        if node:
            node.setItemVisibilityCheckedParentRecursive(True)
        self.iface.setActiveLayer(layer)
        feat = layer.getFeature(fid)
        rect = QgsRectangle(feat.geometry().boundingBox())
        rect.grow(max(2.0, max(rect.width(), rect.height())*.3))
        self.iface.mapCanvas().setExtent(rect)
        self.iface.mapCanvas().refresh()
        self.status.setText(f"{len(available)} unchecked · {value(feat,'class')} · {value(feat,'source')}\n"
                            f"{value(feat,'note')}\nReview on the tile image. A accept · E edit · R reject.")

    def candidate(self):
        if self.current not in self.pending():
            raise ValueError("Use Next or Previous to inspect one unchecked suggestion first.")
        layer, fid = self.candidates[self.current]
        return layer.getFeature(fid)

    def accept(self, edit):
        feat = self.candidate()
        self.copying = True
        try:
            fid = copy_candidate(self.labels, feat, CLASSES)
        finally:
            self.copying = False
        self.labels.triggerRepaint()
        if not edit:
            self.browse(1)
            return
        self.iface.setActiveLayer(self.labels)
        self.labels.selectByIds([fid])
        self.iface.actionVertexToolActiveLayer().trigger()
        self.status.setText("Copied. Move vertices or change class to record prelabel_edited. ] advances.")

    def choose_class(self, name):
        self.number = name
        if ((self.capture is None or self.iface.mapCanvas().mapTool() != self.capture) and self.iface.activeLayer() == self.labels
                and self.labels.selectedFeatureCount() == 1):
            fid = self.labels.selectedFeatureIds()[0]
            with command(self.labels, "Change GeoWatch class"):
                if name != "built" and value(self.labels.getFeature(fid), "rooftop_solar").lower() in ("true","1"):
                    assign(self.labels, fid, "rooftop_solar", False)
                assign(self.labels, fid, "label", name)
            self.labels.triggerRepaint()
        self.status.setText(f"Class: {name}. D starts a hand-drawn polygon.")

    def draw(self):
        self.iface.setActiveLayer(self.labels)
        self.labels.removeSelection()
        with command(self.labels, "Prepare hand tracing"):
            prepare_schema(self.labels)
        if self.capture is None:
            self.capture = QgsMapToolDigitizeFeature(self.iface.mapCanvas(), self.iface.cadDockWidget(),
                                                     QgsMapToolCapture.CapturePolygon)
            self.capture.setLayer(self.labels)
            self.capture.digitizingCompleted.connect(self.traced)
        self.iface.mapCanvas().setMapTool(self.capture)
        self.status.setText(f"Draw {self.number}. Right click to finish. Number keys change the next surface class.")

    def traced(self, sketch):
        # Only a completed digitizing gesture enters this path. Clipboard transfers,
        # native layer imports and suggestions never acquire hand-drawn provenance.
        try:
            authorize_tile(self.tile.path)
            geom = sketch.geometry()
            if geom.isEmpty() or not geom.isGeosValid():
                raise ValueError("The traced polygon is empty or invalid. Draw it again.")
            f = QgsFeature(self.labels.fields())
            f.setGeometry(geom)
            f["label"] = self.number
            f["provenance"] = "hand_drawn"
            for key in ("shadow_partial", "rooftop_solar"):
                f[key] = False
            self.copying = True
            try:
                with command(self.labels, "Draw GeoWatch label"):
                    if not self.labels.addFeature(f):
                        raise ValueError("The drawn polygon could not be added.")
            finally:
                self.copying = False
            self.labels.selectByIds([f.id()])
            self.labels.triggerRepaint()
            self.status.setText(f"Hand-drawn {self.number} added. F opens its form for shadow or rooftop-solar flags.")
        except Exception as exc:
            self.status.setText(str(exc))

    def remaining(self):
        if self.overlay and self.project.mapLayer(self.overlay):
            self.project.removeMapLayer(self.overlay)
            self.overlay = None
            self.status.setText("Unlabelled overlay hidden.")
            return
        geom = QgsGeometry.fromRect(QgsRectangle(*self.tile.bounds))
        polys = [f.geometry() for f in self.labels.getFeatures() if f.hasGeometry()]
        if polys:
            geom = geom.difference(QgsGeometry.unaryUnion(polys))
            if geom.lastError():
                raise ValueError(geom.lastError())
        if geom.isEmpty():
            self.status.setText("The full tile is covered by label polygons.")
            return
        layer = QgsVectorLayer(f"MultiPolygon?crs={self.tile.crs}", "Unlabelled area · snapshot", "memory")
        f = QgsFeature()
        f.setGeometry(geom)
        if not layer.dataProvider().addFeatures([f])[0]:
            raise ValueError("Could not create the gap overlay.")
        layer.updateExtents()
        layer.renderer().symbol().setColor(QColor("#ed24b3"))
        layer.setOpacity(.35)
        layer.setReadOnly(True)
        self.project.addMapLayer(layer)
        self.overlay = layer.id()
        self.status.setText(f"{geom.area():,.1f} m² unlabelled. Toggle U off and on to refresh.")

    def done(self):
        if self.labels.isEditable() and self.labels.isModified():
            ok = QMessageBox.question(self.dock, "Mark tile done", "Save your label edits before validation?")
            if ok != QMessageBox.Yes:
                return
            if not self.labels.commitChanges():
                raise ValueError("\n".join(self.labels.commitErrors()))
        settings = QSettings()
        interpreter = settings.value("GeoWatch/item21/python", "", str)
        if not interpreter or not Path(interpreter).is_file():
            interpreter, _ = QFileDialog.getOpenFileName(self.dock, "Select the GeoWatch environment's Python executable")
            if not interpreter:
                return
            settings.setValue("GeoWatch/item21/python", interpreter)
        env = {k:v for k,v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([interpreter, "-m", "tools.labelling.validate", str(self.tile.path)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        if result.returncode:
            self.status.setText("Validation needs attention. See the report.")
        else:
            self.log.write(self.tile.path, "", "done", result.stdout)
            self.status.setText("Tile passed validation. Completion is recorded in this QGIS profile.")
        report = QMessageBox(self.dock)
        report.setWindowTitle("Item 21 validation")
        report.setText(self.status.text())
        report.setDetailedText((result.stdout + "\n" + result.stderr).strip())
        report.exec_()

    def perform(self, action, name=None):
        try:
            if not self.tile or not self.labels:
                raise ValueError("Open a registered training or practice label project.")
            if Path(self.project.fileName()).parent.resolve() != self.tile.path:
                raise ValueError("The project folder changed. Reopen the generated project.")
            try:
                self.tile = authorize_tile(self.tile.path)
            except (OSError, ValueError):
                self.hide_suggestions()
                self.detach()
                self.enable_keys(False)
                raise
            if action in ("prev", "next"):
                self.browse(1 if action == "next" else -1)
            elif action in ("accept", "edit"):
                self.accept(action == "edit")
            elif action == "reject":
                self.candidate()
                self.log.write(self.tile.path, self.current, "reject")
                self.browse(1)
            elif action == "reopen":
                keys = self.log.rejected(self.tile.path)
                if keys:
                    pick, ok = QInputDialog.getItem(self.dock, "Reopen a rejection", "Candidate ID", sorted(keys), 0, False)
                    if ok:
                        self.log.write(self.tile.path, pick, "reopen")
                        self.current = None
                        self.browse(1)
                else:
                    self.status.setText("This tile has no rejected suggestions.")
            elif action == "class":
                self.choose_class(name)
            elif action == "draw":
                self.draw()
            elif action == "form":
                if self.labels.selectedFeatureCount() != 1:
                    raise ValueError("Select a single label to open its form.")
                self.iface.openFeatureForm(self.labels, self.labels.selectedFeatures()[0])
            elif action == "unlabelled":
                self.remaining()
            elif action == "time":
                meta = json.loads((self.tile.path/"metadata.json").read_text())
                name = meta.get("labeller")
                if not name:
                    name, ok = QInputDialog.getText(self.dock, "Labelling timer", "Labeller name")
                    if not ok:
                        return
                self.status.setText(timer(self.tile.path, name))
            elif action == "done":
                self.done()
        except Exception as exc:
            self.status.setText(str(exc))
            self.iface.messageBar().pushWarning("GeoWatch", str(exc))

    def unload(self):
        self.detach()
        self.iface.projectRead.disconnect(self.open_project)
        self.iface.newProjectCreated.disconnect(self.open_project)
        self.iface.removePluginMenu("GeoWatch", self.menu)
        for a in self.actions:
            self.iface.mapCanvas().removeAction(a)
            a.deleteLater()
        self.iface.removeDockWidget(self.dock)
        self.dock.deleteLater()
