"""Review operations in the normal QGIS undoable layer editing buffer."""
from contextlib import contextmanager
from qgis.PyQt.QtCore import QVariant
from qgis.core import NULL, QgsFeature, QgsField, QgsGeometry, QgsWkbTypes

TRACE = ("provenance", "source", "source_id", "source_version", "candidate_id")


def value(feature, key):
    v = feature[key] if key in feature.fields().names() else None
    return "" if v is None or v == NULL else str(v)


@contextmanager
def command(layer, description):
    if not layer.isEditable() and not layer.startEditing():
        raise ValueError("The labels layer could not enter edit mode.")
    layer.beginEditCommand(description)
    try:
        yield
    except Exception:
        layer.destroyEditCommand()
        raise
    else:
        layer.endEditCommand()


def prepare_schema(layer):
    # Called only after a user requests an edit. Existing polygons keep NULL origins.
    for name in TRACE:
        if layer.fields().indexOf(name) < 0 and not layer.addAttribute(QgsField(name, QVariant.String)):
            raise ValueError(f"Cannot add the required field {name}.")
    cfg = layer.editFormConfig()
    for name in TRACE:
        cfg.setReadOnly(layer.fields().indexOf(name), True)
    layer.setEditFormConfig(cfg)


def assign(layer, fid, key, val):
    if not layer.changeAttributeValue(fid, layer.fields().indexOf(key), val):
        raise ValueError(f"Cannot change {key} on this label.")


def copy_candidate(layer, feature, allowed):
    """An explicit human accept. Copy the source unchanged and retain its identity."""
    label = value(feature, "class")
    if (value(feature, "hint_only").lower() not in ("0", "false") or
            label not in allowed or any(not value(feature, k) for k in TRACE[1:])):
        raise ValueError("This feature is a hint or lacks a reviewable class and source.")
    geometry = QgsGeometry(feature.geometry())
    if geometry.isEmpty() or not geometry.isGeosValid() or geometry.type() != QgsWkbTypes.PolygonGeometry:
        raise ValueError("This candidate has invalid or empty polygon geometry.")
    with command(layer, "Accept reviewed GeoWatch suggestion"):
        prepare_schema(layer)
        key = value(feature, "candidate_id")
        if any(value(f, "candidate_id") == key for f in layer.getFeatures()):
            raise ValueError("This candidate already has a label.")
        copied = QgsFeature(layer.fields())
        copied.setGeometry(geometry)
        copied["label"] = label
        for k in ("shadow_partial", "rooftop_solar"):
            copied[k] = False
        copied["provenance"] = "prelabel_kept"
        for k in TRACE[1:]:
            copied[k] = value(feature, k)
        if not layer.addFeature(copied):
            raise ValueError("The candidate could not be copied.")
    return copied.id()


def mark_change(layer, fid, candidates, geometry=None, field=None, new=None):
    """Mark an actual change to a kept candidate, including edits made via native tools."""
    label = layer.getFeature(fid)
    if value(label, "provenance") != "prelabel_kept":
        return
    entry = candidates.get(value(label, "candidate_id"))
    source = entry[0].getFeature(entry[1]) if entry else None
    if geometry is not None:
        changed = source is None or not geometry.isGeosEqual(source.geometry())
    elif field == "label":
        changed = source is None or str(new) != value(source, "class")
    else:
        return
    if changed:
        assign(layer, fid, "provenance", "prelabel_edited")
