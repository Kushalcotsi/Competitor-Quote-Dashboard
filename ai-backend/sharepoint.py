import argparse
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import msal
import requests


TENANT_ID = "1d9e1278-d015-4622-a20e-232c77fe0086"
CLIENT_ID = "4ad0c051-75f9-40dd-b2ab-646965e4a9b4"

SITE_HOSTNAME = "otsi365.sharepoint.com"
SITE_PATH = "/sites/Competitiveprice"
DEFAULT_DRIVE_FOLDER = "Quotes"
DEFAULT_DOWNLOAD_FOLDER = Path("downloads") / "sharepoint"
DEFAULT_SHAREPOINT_URL = (
    "https://otsi365.sharepoint.com/sites/Competitiveprice/Shared%20Documents/Forms/AllItems.aspx"
    "?id=%2Fsites%2FCompetitiveprice%2FShared%20Documents%2FQuotes"
)
SCOPES = ["Sites.Read.All", "Files.Read"]
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def graph_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    response = requests.get(url, headers=headers, timeout=60)
    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}
    if not response.ok:
        raise RuntimeError(f"Graph request failed ({response.status_code}) for {url}: {data}")
    return data


def acquire_token() -> str:
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to start device flow: {flow}")
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Failed to acquire access token: {result}")
    return result["access_token"]


def parse_sharepoint_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    hostname = parsed.hostname or SITE_HOSTNAME
    query = parse_qs(parsed.query)
    item_path = unquote(query.get("id", [""])[0])

    path_source = item_path or parsed.path
    parts = [part for part in path_source.split("/") if part]
    if len(parts) < 2 or parts[0].lower() != "sites":
        return hostname, SITE_PATH, DEFAULT_DRIVE_FOLDER

    site_path = f"/sites/{parts[1]}"
    folder = DEFAULT_DRIVE_FOLDER
    if len(parts) > 3 and parts[2].lower() == "shared documents":
        folder = "/".join(parts[3:])
    return hostname, site_path, folder


def get_site_id(headers: dict[str, str], hostname: str, site_path: str) -> str:
    site_path = "/" + site_path.strip("/")
    site = graph_get(f"{GRAPH_ROOT}/sites/{hostname}:{site_path}", headers)
    site_id = site["id"]
    print(f"Site: {hostname}{site_path}")
    print(f"Site ID: {site_id}")
    return site_id


def get_drive_id(headers: dict[str, str], site_id: str) -> str:
    drive = graph_get(f"{GRAPH_ROOT}/sites/{site_id}/drive", headers)
    drive_id = drive["id"]
    print(f"Drive: {drive.get('name', 'Documents')}")
    print(f"Drive ID: {drive_id}")
    return drive_id


def list_drive_items(headers: dict[str, str], drive_id: str, folder: str) -> list[dict[str, Any]]:
    folder = folder.strip("/")
    if folder:
        url = f"{GRAPH_ROOT}/drives/{drive_id}/root:/{folder}:/children"
    else:
        url = f"{GRAPH_ROOT}/drives/{drive_id}/root/children"

    items: list[dict[str, Any]] = []
    while url:
        page = graph_get(url, headers)
        items.extend(page.get("value", []))
        url = page.get("@odata.nextLink")
    return items


def download_file(headers: dict[str, str], drive_id: str, item: dict[str, Any], download_folder: Path) -> None:
    response = requests.get(
        f"{GRAPH_ROOT}/drives/{drive_id}/items/{item['id']}/content",
        headers=headers,
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(f"Failed to download {item['name']} ({response.status_code}): {response.text}")

    download_folder.mkdir(parents=True, exist_ok=True)
    target = download_folder / item["name"]
    target.write_bytes(response.content)
    print(f"Downloaded: {target}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download files from a SharePoint document library via Microsoft Graph.")
    parser.add_argument("--sharepoint-url", default=os.getenv("SHAREPOINT_URL", DEFAULT_SHAREPOINT_URL))
    parser.add_argument("--site-hostname", default=os.getenv("SHAREPOINT_SITE_HOSTNAME"))
    parser.add_argument("--site-path", default=os.getenv("SHAREPOINT_SITE_PATH"))
    parser.add_argument("--drive-folder", default=os.getenv("SHAREPOINT_DRIVE_FOLDER"))
    parser.add_argument("--download-folder", default=os.getenv("SHAREPOINT_DOWNLOAD_FOLDER", str(DEFAULT_DOWNLOAD_FOLDER)))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    url_hostname, url_site_path, url_drive_folder = parse_sharepoint_url(args.sharepoint_url)
    site_hostname = args.site_hostname or url_hostname
    site_path = args.site_path or url_site_path
    drive_folder = args.drive_folder if args.drive_folder is not None else url_drive_folder

    print("Signing in to Microsoft Graph...")
    token = acquire_token()
    headers = {"Authorization": f"Bearer {token}"}

    site_id = get_site_id(headers, site_hostname, site_path)
    drive_id = get_drive_id(headers, site_id)
    print(f"Listing folder: {drive_folder or '/'}")
    items = list_drive_items(headers, drive_id, drive_folder)
    files = [item for item in items if "file" in item]
    print(f"Found {len(files)} file(s).")

    download_folder = Path(args.download_folder)
    for item in files:
        download_file(headers, drive_id, item, download_folder)

    print("Done.")


if __name__ == "__main__":
    main()