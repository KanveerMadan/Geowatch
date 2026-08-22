#!/usr/bin/env python3
"""
push_water_annotations_to_drive.py

Walks local geowatch/data/pipeline_runs/<city_run_id>/ folders, finds each
city's osm_generated_annotations_water.json, and uploads it (or updates the
existing copy) into the matching city folder on Google Drive, under your
"Geowatch" root folder — same location as the existing
osm_generated_annotations.json (road) file.

SETUP (one-time):
  1. pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
  2. Go to https://console.cloud.google.com/apis/credentials
     - Create an OAuth Client ID (type: Desktop app)
     - Download the JSON, save it as credentials.json next to this script
  3. First run will open a browser window for you to authorize access to
     your Drive account. A token.json will be cached after that so you
     don't have to re-auth every time.

USAGE:
  python push_water_annotations_to_drive.py \\
      --local-root "/Users/kanveermadan/geowatch/data/pipeline_runs" \\
      --drive-root-name "Geowatch"

  Add --dry-run first to see what it WOULD do without uploading anything.
"""

import argparse
import io
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]
TARGET_FILENAME = "osm_generated_annotations_water.json"


def get_drive_service(creds_path="credentials.json", token_path="token.json"):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                sys.exit(
                    f"ERROR: {creds_path} not found. See the setup instructions "
                    f"in this script's docstring."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def find_folder_id(service, name, parent_id=None):
    """Find a folder by exact name, optionally scoped under a parent folder."""
    query = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"
    resp = service.files().list(
        q=query, spaces="drive", fields="files(id, name)"
    ).execute()
    files = resp.get("files", [])
    if not files:
        return None
    if len(files) > 1:
        print(f"  WARNING: multiple folders named '{name}' found under this "
              f"parent — using the first match ({files[0]['id']}).")
    return files[0]["id"]


def find_file_id(service, name, parent_id):
    query = (
        f"name = '{name}' and '{parent_id}' in parents and trashed = false"
    )
    resp = service.files().list(
        q=query, spaces="drive", fields="files(id, name)"
    ).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def upload_or_update(service, local_path, filename, parent_id, dry_run=False):
    existing_id = find_file_id(service, filename, parent_id)
    if dry_run:
        action = "UPDATE existing" if existing_id else "CREATE new"
        print(f"    [DRY RUN] Would {action} '{filename}' in folder {parent_id}")
        return

    media = MediaFileUpload(local_path, mimetype="application/json", resumable=True)
    if existing_id:
        service.files().update(fileId=existing_id, media_body=media).execute()
        print(f"    Updated existing '{filename}' (file id {existing_id})")
    else:
        metadata = {"name": filename, "parents": [parent_id]}
        created = service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute()
        print(f"    Created new '{filename}' (file id {created['id']})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local-root", required=True,
        help="Path to local geowatch/data/pipeline_runs directory"
    )
    parser.add_argument(
        "--drive-root-name", default="Geowatch",
        help="Name of the root Drive folder containing all city run folders "
             "(default: 'Geowatch')"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be uploaded without actually uploading"
    )
    args = parser.parse_args()

    if not os.path.isdir(args.local_root):
        sys.exit(f"ERROR: local root '{args.local_root}' is not a directory.")

    service = get_drive_service()

    print(f"Looking up Drive root folder '{args.drive_root_name}'...")
    root_id = find_folder_id(service, args.drive_root_name)
    if not root_id:
        sys.exit(
            f"ERROR: could not find a Drive folder named "
            f"'{args.drive_root_name}'. Check the name/spelling, or pass "
            f"--drive-root-name explicitly."
        )
    print(f"Found root folder id: {root_id}\n")

    run_dirs = sorted(
        d for d in os.listdir(args.local_root)
        if os.path.isdir(os.path.join(args.local_root, d))
    )

    found, missing_local, missing_drive_folder, uploaded = [], [], [], []

    for run_id in run_dirs:
        local_run_path = os.path.join(args.local_root, run_id)
        local_water_path = os.path.join(local_run_path, TARGET_FILENAME)

        print(f"[{run_id}]")

        if not os.path.exists(local_water_path):
            print(f"  SKIP — no local {TARGET_FILENAME} found.")
            missing_local.append(run_id)
            continue

        drive_folder_id = find_folder_id(service, run_id, parent_id=root_id)
        if not drive_folder_id:
            print(f"  SKIP — no matching Drive folder named '{run_id}' "
                  f"under '{args.drive_root_name}'.")
            missing_drive_folder.append(run_id)
            continue

        upload_or_update(
            service, local_water_path, TARGET_FILENAME, drive_folder_id,
            dry_run=args.dry_run
        )
        found.append(run_id)
        if not args.dry_run:
            uploaded.append(run_id)

    print("\n" + "=" * 60)
    print(f"Cities with local file + matching Drive folder: {len(found)}")
    print(f"  -> {found}")
    if missing_local:
        print(f"\nCities MISSING local {TARGET_FILENAME}: {len(missing_local)}")
        print(f"  -> {missing_local}")
        print(f"  (run merge_osm_water_masks.py for these first)")
    if missing_drive_folder:
        print(f"\nCities with no matching Drive folder found: {len(missing_drive_folder)}")
        print(f"  -> {missing_drive_folder}")
        print(f"  (check folder name spelling/casing on Drive)")
    if args.dry_run:
        print("\nThis was a DRY RUN — nothing was actually uploaded. "
              "Re-run without --dry-run to push for real.")
    else:
        print(f"\nUploaded/updated: {len(uploaded)} file(s).")
    print("=" * 60)


if __name__ == "__main__":
    main()