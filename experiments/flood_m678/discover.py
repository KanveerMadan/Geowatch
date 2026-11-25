"""Reproduce metadata leads from two pinned public catalogues. Never fetch label assets."""
import argparse
import csv
import hashlib
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

ARCHIVES = {
    "glof.ods": ("23370149", "glofdatabase_v4-2.ods", "37b4516f8ce80824dacb455ac4dfc1a0"),
    "dfo.csv": ("19288171", "Global_Flood_Records.csv", "8fe3cd72474abe8d4d83641e2d33266f"),
}
FIELDS = ("source_row", "type", "country", "place", "driver_as_reported", "reported_date",
          "reported_min", "reported_max", "lat", "lon", "coordinate_role", "source_event_id")
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"


def archive(directory, name):
    record, remote, checksum = ARCHIVES[name]
    path = directory / name
    if not path.exists():
        with NamedTemporaryFile(dir=directory, delete=False) as tmp:
            pending = Path(tmp.name)
        try:
            url = f"https://zenodo.org/api/records/{record}/files/{remote}/content"
            with urllib.request.urlopen(url, timeout=90) as source, pending.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            if hashlib.md5(pending.read_bytes()).hexdigest() != checksum:
                raise ValueError(f"Publisher checksum mismatch for {name}")
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
    if hashlib.md5(path.read_bytes()).hexdigest() != checksum:
        raise ValueError(f"Cached file changed: {name}")
    return path


def glof_rows(path):
    # Read only the identity, location and date columns of the first worksheet.
    # The lake coordinates locate the source. They cannot stand in for a downstream reach.
    with zipfile.ZipFile(path) as z, z.open("content.xml") as stream:
        columns = None
        for _, row in ET.iterparse(stream, events=("end",)):
            if row.tag == TABLE + "table":
                break
            if row.tag != TABLE + "table-row":
                continue
            values = []
            for cell in row:
                if len(values) >= 17:
                    break
                value = cell.get(OFFICE+"date-value") or cell.get(OFFICE+"value") or "".join(cell.itertext())
                repeat = int(cell.get(TABLE+"number-columns-repeated", "1"))
                values.extend([value.strip()] * min(repeat, 17-len(values)))
            row.clear()
            if columns is None:
                columns = values
                if columns[13:16] != ["Date", "Date_Min", "Date_Max"]:
                    raise ValueError("GLOF date schema changed")
                row_number = 1
                continue
            row_number += 1
            data = dict(zip(columns, values))
            if row_number in (2, 3) or not any(values):
                continue
            yield (f"glof-v4.2:{row_number}", "M6", data["Country"],
                   " / ".join(filter(None,(data["Lake"], data["Glacier"], data["River"]))),
                   "glacial lake outburst", data["Date"], data["Date_Min"], data["Date_Max"],
                   data["Latitude"], data["Longitude"], "lake_source", data["ID_old"])


def dfo_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            cause = row["Main Cause"]
            key = cause.lower()
            if "glacial lake" in key:
                flood_type = "M6"
            elif re.search(r"dam|levee|levy", key):
                flood_type = "M7-review"
            elif re.search(r"snow\s*melt|ice jam|ice break", key):
                flood_type = "M8"
            else:
                continue
            start, end = (datetime.strptime(row[k], "%m/%d/%y").date().isoformat()
                          for k in ("Start Date", "End Date"))
            yield (f"dfo:{row['﹟']}", flood_type, row["Country"], "", cause, "", start, end,
                   "", "", "country_only", row["Glide ﹟"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    rows = list(glof_rows(archive(args.cache, "glof.ods")))
    rows.extend(dfo_rows(archive(args.cache, "dfo.csv")))
    if len({row[0] for row in rows}) != len(rows):
        raise ValueError("Duplicate source row ID")
    with NamedTemporaryFile("w", newline="", encoding="utf-8", dir=args.output.parent,
                            delete=False) as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(rows)
    Path(f.name).replace(args.output)


if __name__ == "__main__":
    main()
