"""GeoWatch Item 21 QGIS plugin entry point."""


def classFactory(iface):
    from .plugin import ReviewPlugin
    return ReviewPlugin(iface)
