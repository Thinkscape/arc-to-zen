#!/usr/bin/env python3
"""Copy cached Arc favicons into Zen session tab images."""

import base64
import json
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from zen_sessions_importer_v4 import read_mozilla_lz4, resolve_zen_profile, write_mozilla_lz4


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def arc_favicons_uri() -> str:
    path = Path.home() / "Library" / "Application Support" / "Arc" / "User Data" / "Default" / "Favicons"
    return "file:" + str(path).replace(" ", "%20") + "?mode=ro&immutable=1"


def mime_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if data.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    return "image/png"


def data_uri(data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type(data)};base64,{encoded}"


def best_icon_for_url(con: sqlite3.Connection, url: str) -> Optional[str]:
    rows = con.execute(
        """
        SELECT b.width, b.height, b.image_data
        FROM icon_mapping m
        JOIN favicon_bitmaps b ON b.icon_id = m.icon_id
        WHERE m.page_url = ?
          AND b.image_data IS NOT NULL
          AND length(b.image_data) > 0
        """,
        (url,),
    ).fetchall()

    if not rows:
        return None

    def score(row: tuple[int, int, bytes]) -> tuple[int, int]:
        width, height, image = row
        size = width or height or 0
        return (abs(size - 32), len(image))

    return data_uri(min(rows, key=score)[2])


def load_arc_icons(export_file: Path) -> Dict[str, str]:
    with open(export_file, encoding="utf-8") as f:
        arc_data = json.load(f)

    urls = []
    for space in arc_data.get("spaces", []):
        for tab in space.get("pinned_tabs", []):
            url = tab.get("url")
            if url:
                urls.append(url)

    con = sqlite3.connect(arc_favicons_uri(), uri=True)
    try:
        icons = {}
        for url in sorted(set(urls)):
            icon = best_icon_for_url(con, url)
            if icon:
                icons[url] = icon
        return icons
    finally:
        con.close()


def tab_url(tab: Dict[str, Any]) -> Optional[str]:
    entries = tab.get("entries") or []
    if not entries:
        return None
    return entries[-1].get("url")


def apply_icons_to_tabs(tabs: list[Dict[str, Any]], icons: Dict[str, str]) -> int:
    updated = 0
    for tab in tabs:
        url = tab_url(tab)
        icon = icons.get(url or "")
        if not icon:
            continue

        if tab.get("image") != icon:
            tab["image"] = icon
            updated += 1

        pinned_state = tab.get("_zenPinnedInitialState")
        if isinstance(pinned_state, dict) and pinned_state.get("image") != icon:
            pinned_state["image"] = icon

    return updated


def backup(path: Path, timestamp: str):
    backup_path = path.with_name(f"{path.name}.codex-favicon-backup-{timestamp}")
    shutil.copy2(path, backup_path)
    logger.info(f"✅ Backed up {path.name} to {backup_path.name}")


def update_lz4_file(path: Path, icons: Dict[str, str], timestamp: str) -> int:
    if not path.exists():
        logger.info(f"Skipping missing file: {path}")
        return 0

    data = read_mozilla_lz4(path)
    if "windows" in data:
        tabs = []
        for window in data.get("windows", []):
            tabs.extend(window.get("tabs", []))
    else:
        tabs = data.get("tabs", [])

    updated = apply_icons_to_tabs(tabs, icons)
    if updated:
        backup(path, timestamp)
        write_mozilla_lz4(path, data)

    logger.info(f"{path.name}: updated {updated} tab images")
    return updated


def main() -> bool:
    export_file = Path("arc_pinned_tabs_export.json")
    if not export_file.exists():
        logger.error("Arc export not found. Run src/arc_pinned_tab_extractor.py first.")
        return False

    profile = resolve_zen_profile()
    icons = load_arc_icons(export_file)
    logger.info(f"Loaded {len(icons)} Arc favicon images for migrated URLs")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    files = [
        profile / "zen-sessions.jsonlz4",
        profile / "sessionstore.jsonlz4",
        profile / "sessionstore-backups" / "recovery.jsonlz4",
    ]

    total = 0
    for path in files:
        total += update_lz4_file(path, icons, timestamp)

    logger.info(f"Done. Updated {total} tab image fields across Zen session files.")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
