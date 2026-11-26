"""Install the registered ward layers into the Render build artifact."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from boundaries.ingestion import ingest_boundary_layer
from configs.boundary_constants import KNOWN_BOUNDARY_SOURCES


def prepare():
    with TemporaryDirectory() as directory:
        source = Path(directory) / "source.geojson"
        for layer in KNOWN_BOUNDARY_SOURCES.values():
            response = requests.get(layer["source"]["source_url"], timeout=45)
            response.raise_for_status()
            if sha256(response.content).hexdigest() != layer["file_sha256"]:
                raise ValueError(f"Source checksum changed for {layer['boundary_layer_id']}")
            source.write_bytes(response.content)
            result = ingest_boundary_layer(str(source), layer)
            if result["status"] != "available":
                raise ValueError(result.get("error", "Ward layer unavailable"))


if __name__ == "__main__":
    prepare()
