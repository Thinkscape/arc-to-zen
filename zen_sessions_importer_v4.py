#!/usr/bin/env python3
"""
Zen Sessions Importer v4 - Proper Nested Folders

Supports nested folder structures with correct parentId relationships.
"""

import json
import logging
import struct
import uuid
import hashlib
import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import shutil
import copy

from src.profile_paths import resolve_zen_profile as resolve_zen_profile_path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOOKMARK_ROOT_GUIDS = {
    "root________",
    "menu________",
    "toolbar_____",
    "tags________",
    "unfiled_____",
    "mobile______",
}


def read_mozilla_lz4(filepath: Path) -> Dict[str, Any]:
    """Read Mozilla's LZ4-compressed JSON file."""
    import lz4.block

    with open(filepath, 'rb') as f:
        magic = f.read(8)
        if magic != b'mozLz40\x00':
            raise ValueError("Not a valid mozLz4 file")

        size_bytes = f.read(4)
        uncompressed_size = struct.unpack('<I', size_bytes)[0]
        compressed = f.read()
        decompressed = lz4.block.decompress(compressed, uncompressed_size=uncompressed_size)
        return json.loads(decompressed)


def backup_file(filepath: Path, label: str = "backup", timestamp: Optional[str] = None) -> Optional[Path]:
    """Create a timestamped backup next to a profile file."""
    if not filepath.exists():
        return None

    if timestamp:
        backup_path = filepath.with_name(f"{filepath.name}.codex-{label}-{timestamp}")
    else:
        backup_path = filepath.with_suffix(f"{filepath.suffix}.bak")

    shutil.copy2(filepath, backup_path)
    logger.info(f"✅ Backed up {filepath.name} to {backup_path.name}")
    return backup_path


def write_mozilla_lz4(filepath: Path, data: Dict[str, Any]):
    """Write data in Mozilla's LZ4-compressed JSON format."""
    import lz4.block

    backup_file(filepath)

    json_bytes = json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    logger.info(f"   JSON size: {len(json_bytes):,} bytes")

    compressed = lz4.block.compress(json_bytes, store_size=False)
    logger.info(f"   Compressed: {len(compressed):,} bytes")

    with open(filepath, 'wb') as f:
        f.write(b'mozLz40\x00')
        f.write(struct.pack('<I', len(json_bytes)))
        f.write(compressed)

    logger.info(f"✅ Wrote {filepath.name}")


def generate_uuid() -> str:
    """Generate a UUID in Zen's format."""
    return f"{{{uuid.uuid4()}}}"


def create_zen_tab(arc_tab: Dict, workspace_uuid: str, group_id: str, timestamp: int, tab_index: int) -> Dict:
    """Create a Zen tab entry matching Zen format (as of JAN 2026)."""
    url = arc_tab.get('url', 'about:blank')
    title = arc_tab.get('title', 'Untitled')
    is_pinned = bool(arc_tab.get('is_pinned', True) or arc_tab.get('is_essential', False))

    # Generate unique IDs
    sync_id = f"{timestamp}-{tab_index}"
    doc_id = tab_index + 1000
    docshell_uuid = generate_uuid()
    nav_key = generate_uuid()
    nav_id = generate_uuid()

    # Create proper entry structure
    entry = {
        "url": url,
        "title": title,
        "cacheKey": 0,
        "ID": doc_id,
        "docshellUUID": docshell_uuid,
        "resultPrincipalURI": None,
        "hasUserInteraction": False,
        "triggeringPrincipal_base64": '{"3":{}}',
        "docIdentifier": doc_id + 10000,
        "children": [],
        "transient": False,
        "navigationKey": nav_key,
        "navigationId": nav_id
    }

    # Create tab structure
    tab = {
        "entries": [entry],
        "lastAccessed": timestamp,
        "pinned": is_pinned,
        "hidden": False,
        "zenWorkspace": workspace_uuid,
        "zenSyncId": sync_id,
        "zenEssential": arc_tab.get('is_essential', False),
        "zenDefaultUserContextId": None,
        "zenPinnedIcon": None,
        "zenIsEmpty": False,
        "zenHasStaticIcon": False,
        "zenGlanceId": None,
        "zenIsGlance": False,
        "searchMode": None,
        "userContextId": 0,
        "attributes": {},
        "index": tab_index,
        "image": ""
    }

    if is_pinned:
        if group_id:
            tab["groupId"] = group_id
        tab["_zenPinnedInitialState"] = {
            "entry": entry.copy(),
            "image": None
        }
        tab["_zenIsActiveTab"] = False

    return tab


def create_zen_empty_tab(workspace_uuid: str, group_id: str, timestamp: int, tab_index: int) -> Dict:
    """Create Zen's hidden about:blank anchor tab for a folder with no direct tabs."""
    sync_id = f"{timestamp}-{tab_index}-empty"
    doc_id = tab_index + 100000
    entry = {
        "url": "about:blank",
        "title": "about:blank",
        "cacheKey": 0,
        "ID": doc_id,
        "docshellUUID": generate_uuid(),
        "resultPrincipalURI": None,
        "hasUserInteraction": False,
        "triggeringPrincipal_base64": '{"3":{}}',
        "docIdentifier": doc_id + 10000,
        "children": [],
        "transient": True,
        "navigationKey": generate_uuid(),
        "navigationId": generate_uuid()
    }

    return {
        "entries": [entry],
        "lastAccessed": timestamp,
        "pinned": True,
        "hidden": False,
        "zenWorkspace": workspace_uuid,
        "zenSyncId": sync_id,
        "zenEssential": False,
        "zenDefaultUserContextId": None,
        "zenPinnedIcon": None,
        "zenIsEmpty": True,
        "zenHasStaticIcon": False,
        "zenGlanceId": None,
        "zenIsGlance": False,
        "searchMode": None,
        "userContextId": 0,
        "attributes": {},
        "index": tab_index,
        "image": None,
        "groupId": group_id,
        "_zenPinnedInitialState": {
            "entry": entry.copy(),
            "image": None
        },
        "_zenIsActiveTab": False
    }


def create_zen_folder(folder_name: str, workspace_uuid: str, timestamp: int, parent_folder_id: str = None) -> Tuple[Dict, Dict, str]:
    """Create a Zen folder and group entry with proper parent relationship."""
    stable_hash = hashlib.sha1(f"{folder_name}:{parent_folder_id or ''}".encode("utf-8")).hexdigest()
    folder_id = f"{timestamp}-{int(stable_hash[:8], 16) % 10000}"

    folder = {
        "pinned": True,
        "splitViewGroup": False,
        "id": folder_id,
        "name": folder_name,
        "collapsed": False,
        "saveOnWindowClose": True,
        "parentId": parent_folder_id,  # None for root folders, parent ID for subfolders
        "prevSiblingInfo": {
            "type": "start",
            "id": None
        },
        "emptyTabIds": [],
        "userIcon": "",
        "workspaceId": workspace_uuid
    }

    group = {
        "pinned": True,
        "splitView": False,
        "id": folder_id,
        "name": folder_name,
        "color": "zen-workspace-color",
        "collapsed": False,
        "saveOnWindowClose": True
    }

    return folder, group, folder_id


def folder_path_order(arc_space: Dict) -> Dict[Tuple[str, ...], int]:
    """Return Arc's sidebar order for each folder path."""
    folder_records = {
        folder.get("folder_id"): folder
        for folder in arc_space.get("folders", [])
        if folder.get("folder_id")
    }
    path_cache = {}

    def arc_folder_path(folder_id: str) -> Tuple[str, ...]:
        if folder_id in path_cache:
            return path_cache[folder_id]

        folder = folder_records[folder_id]
        parent_id = folder.get("parent_id")
        if parent_id in folder_records:
            path = arc_folder_path(parent_id) + (folder.get("title", "Untitled Folder"),)
        else:
            path = (folder.get("title", "Untitled Folder"),)

        path_cache[folder_id] = path
        return path

    return {
        arc_folder_path(folder_id): int(folder.get("index", 1_000_000))
        for folder_id, folder in folder_records.items()
    }


def apply_folder_sibling_order(folders: List[Dict], path_by_id: Dict[str, Tuple[str, ...]], order_by_path: Dict[Tuple[str, ...], int]):
    """Set prevSiblingInfo so Zen restores nested folders in Arc's order."""
    siblings = {}
    for folder in folders:
        path = path_by_id.get(folder.get("id"))
        if not path:
            continue
        parent = path[:-1] or None
        siblings.setdefault(parent, []).append(folder)

    for sibling_folders in siblings.values():
        sibling_folders.sort(
            key=lambda folder: (
                order_by_path.get(path_by_id.get(folder.get("id"), ()), 1_000_000),
                path_by_id.get(folder.get("id"), ()),
            )
        )
        previous_id = None
        for folder in sibling_folders:
            folder["prevSiblingInfo"] = {"type": "group", "id": previous_id} if previous_id else {"type": "start", "id": None}
            previous_id = folder.get("id")


def build_folder_hierarchy(arc_space: Dict, workspace_uuid: str, base_timestamp: int) -> Tuple[List[Dict], List[Dict], Dict]:
    """Build nested folder structure from Arc folders.

    Returns:
        - folders: List of Zen folder objects
        - groups: List of Zen group objects
        - folder_map: Dict mapping Arc folder path tuples to Zen folder IDs
    """
    folders = []
    groups = []
    folder_map = {}  # Maps Arc folder path (as tuple) -> Zen folder ID

    order_by_path = folder_path_order(arc_space)
    all_folder_paths = set()
    all_folder_paths.update(order_by_path)

    for tab in arc_space['pinned_tabs']:
        folder_path = tab.get('folder_path', [])
        if folder_path:
            # Add each level of the path
            for i in range(1, len(folder_path) + 1):
                all_folder_paths.add(tuple(folder_path[:i]))

    # Sort by depth first so parents exist, then Arc's sidebar order for siblings.
    sorted_paths = sorted(
        all_folder_paths,
        key=lambda path: (len(path), order_by_path.get(path, 1_000_000), path),
    )

    counter = 0
    path_by_id = {}
    for folder_path_tuple in sorted_paths:
        folder_name = folder_path_tuple[-1]  # Last component is the folder name

        # Determine parent folder ID
        parent_folder_id = None
        if len(folder_path_tuple) > 1:
            parent_path = folder_path_tuple[:-1]
            parent_folder_id = folder_map.get(parent_path)

        # Create folder with proper parent relationship
        folder, group, folder_id = create_zen_folder(
            folder_name,
            workspace_uuid,
            base_timestamp + counter,
            parent_folder_id
        )

        folders.append(folder)
        groups.append(group)
        folder_map[folder_path_tuple] = folder_id
        path_by_id[folder_id] = folder_path_tuple

        # Log with indentation to show hierarchy
        indent = "  " * (len(folder_path_tuple) - 1)
        parent_info = f" (parent: {parent_folder_id})" if parent_folder_id else " (root)"
        logger.info(f"   {indent}📂 Created folder: {folder_name}{parent_info}")

        counter += 1

    apply_folder_sibling_order(folders, path_by_id, order_by_path)
    return folders, groups, folder_map


def add_empty_folder_anchors(
    zen_data: Dict[str, Any],
    space_folders: List[Dict[str, Any]],
    workspace_uuid: str,
    timestamp: int,
    tab_index: int,
) -> int:
    """Add hidden placeholder tabs for folder groups that otherwise contain only subfolders."""
    direct_tab_counts = {}
    for tab in zen_data.get("tabs", []):
        if tab.get("zenWorkspace") != workspace_uuid or tab.get("zenIsEmpty"):
            continue
        group_id = tab.get("groupId")
        if group_id:
            direct_tab_counts[group_id] = direct_tab_counts.get(group_id, 0) + 1

    anchored = 0
    for folder in space_folders:
        folder_id = folder.get("id")
        if direct_tab_counts.get(folder_id):
            continue
        if folder.get("emptyTabIds"):
            continue

        empty_tab = create_zen_empty_tab(workspace_uuid, folder_id, timestamp + anchored, tab_index)
        folder["emptyTabIds"] = [empty_tab["zenSyncId"]]
        zen_data["tabs"].append(empty_tab)
        tab_index += 1
        anchored += 1
        logger.info(f"   📎 Added empty folder anchor: {folder.get('name')}")

    return tab_index


def resolve_zen_profile(profile_path: str | Path | None = None) -> Path:
    """Resolve the target Zen profile from args, env vars, installs.ini, or profiles.ini."""
    return resolve_zen_profile_path(profile_path)


def reset_session_window_state(window: Dict[str, Any]):
    """Remove current/open and recently closed tab state from one sessionstore window."""
    window["tabs"] = []
    window["folders"] = []
    window["groups"] = []
    window["splitViews"] = []
    window["splitViewData"] = []
    window["closedGroups"] = []
    window["_closedTabs"] = []
    window["_lastClosedTabGroupCount"] = -1
    window["lastClosedTabGroupId"] = None
    window["selected"] = 1


def reset_zen_session_state(data: Dict[str, Any], clear_window_history: bool = False):
    """Clear Zen session tabs, folders, groups, pins, and optional closed-tab history."""
    if "windows" in data:
        for window in data.get("windows", []):
            reset_session_window_state(window)
        data["savedGroups"] = []
        data["_closedWindows"] = []
        data["maxSplitViewId"] = 0
        return

    data["tabs"] = []
    data["folders"] = []
    data["groups"] = []
    data["splitViewData"] = []


def nuke_bookmarks(profile: Path, timestamp: str) -> int:
    """Remove all non-root Firefox/Zen bookmarks from places.sqlite."""
    places = profile / "places.sqlite"
    if not places.exists():
        logger.info("No places.sqlite found; skipping bookmark nuke")
        return 0

    for candidate in (places, places.with_name("places.sqlite-wal"), places.with_name("places.sqlite-shm")):
        backup_file(candidate, "nuke-backup", timestamp)

    con = sqlite3.connect(places)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        before = con.execute("SELECT count(*) FROM moz_bookmarks").fetchone()[0]
        placeholders = ",".join("?" for _ in BOOKMARK_ROOT_GUIDS)
        con.execute(f"DELETE FROM moz_bookmarks WHERE guid NOT IN ({placeholders})", tuple(BOOKMARK_ROOT_GUIDS))
        con.execute("DELETE FROM moz_bookmarks_deleted")
        con.commit()
        after = con.execute("SELECT count(*) FROM moz_bookmarks").fetchone()[0]
        removed = before - after
        logger.info(f"🧨 Removed {removed} bookmarks/folders from places.sqlite")
        return removed
    finally:
        con.close()


def nuke_session_file(path: Path, timestamp: str) -> bool:
    if not path.exists():
        logger.info(f"Skipping missing nuke target: {path}")
        return False

    data = read_mozilla_lz4(path)
    reset_zen_session_state(data, clear_window_history=True)
    backup_file(path, "nuke-backup", timestamp)
    write_mozilla_lz4(path, data)
    return True


def nuke_zen_profile(profile: Path, timestamp: str):
    """Destructively clear Zen tabs, folders, pins, groups, closed tabs, and bookmarks."""
    logger.info("🧨 Nuke mode: clearing Zen tabs, folders, pins, groups, closed tab state, and bookmarks")
    nuke_session_file(profile / "zen-sessions.jsonlz4", timestamp)
    nuke_session_file(profile / "sessionstore.jsonlz4", timestamp)
    nuke_session_file(profile / "sessionstore-backups" / "recovery.jsonlz4", timestamp)
    nuke_bookmarks(profile, timestamp)


def sync_sessionstore(profile: Path, zen_data: Dict[str, Any], nuke: bool = False):
    """Update Firefox/Zen sessionstore files so temporary tabs restore as open tabs."""
    session_paths = [
        profile / "sessionstore.jsonlz4",
        profile / "sessionstore-backups" / "recovery.jsonlz4",
    ]

    space_ids = {space.get("uuid") for space in zen_data.get("spaces", [])}

    for session_path in session_paths:
        if not session_path.exists():
            logger.info(f"   Skipping missing sessionstore file: {session_path.name}")
            continue

        session_data = read_mozilla_lz4(session_path)
        windows = session_data.get("windows", [])
        if not windows:
            logger.info(f"   Skipping sessionstore without windows: {session_path.name}")
            continue

        if nuke:
            reset_zen_session_state(session_data, clear_window_history=True)

        window = windows[0]
        window["spaces"] = copy.deepcopy(zen_data.get("spaces", []))
        window["folders"] = copy.deepcopy(zen_data.get("folders", []))
        window["groups"] = copy.deepcopy(zen_data.get("groups", []))
        window["splitViewData"] = copy.deepcopy(zen_data.get("splitViewData", {}))
        window["tabs"] = copy.deepcopy(zen_data.get("tabs", []))

        if window["tabs"]:
            selected = window.get("selected", 1)
            if not isinstance(selected, int):
                selected = 1
            window["selected"] = max(1, min(selected, len(window["tabs"])))

        if window.get("activeZenSpace") not in space_ids and zen_data.get("spaces"):
            window["activeZenSpace"] = zen_data["spaces"][0].get("uuid")

        write_mozilla_lz4(session_path, session_data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Arc sidebar data into Zen session files.")
    parser.add_argument(
        "--zen-profile",
        help="Path to a Zen profile directory, or a Zen root containing profiles.ini.",
    )
    parser.add_argument(
        "--arc-export",
        default="arc_pinned_tabs_export.json",
        help="Path to the Arc export JSON produced by arc_pinned_tab_extractor.py.",
    )
    parser.add_argument(
        "--nuke",
        action="store_true",
        help="Before importing, remove all Zen tabs, folders, pins, tab groups, closed tab state, and regular bookmarks.",
    )
    parser.add_argument(
        "--nuke-only",
        action="store_true",
        help="Only perform the destructive Zen cleanup; do not import Arc data afterward.",
    )
    return parser.parse_args()


def main():
    """Import Arc tabs into the resolved Zen profile with proper nested folders."""
    args = parse_args()

    try:
        profile = resolve_zen_profile(args.zen_profile)
    except Exception as e:
        logger.error(f"❌ Zen profile not found: {e}")
        return False

    logger.info(f"✅ Using profile: {profile.name}")
    nuke_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.nuke or args.nuke_only:
        nuke_zen_profile(profile, nuke_timestamp)
        if args.nuke_only:
            return True

    sessions_file = profile / "zen-sessions.jsonlz4"
    if not sessions_file.exists():
        logger.error(f"❌ Zen session file not found: {sessions_file}")
        return False

    arc_export_file = Path(args.arc_export).expanduser()

    if not arc_export_file.exists():
        logger.error("❌ Arc export not found. Run arc_pinned_tab_extractor.py first.")
        return False

    # Load Arc export
    with open(arc_export_file, 'r') as f:
        arc_data = json.load(f)

    total_tabs = sum(s['total_pinned_tabs'] for s in arc_data['spaces'])
    logger.info(f"✅ Arc export: {len(arc_data['spaces'])} spaces, {total_tabs} tabs")

    # Read current Zen sessions
    zen_data = read_mozilla_lz4(sessions_file)
    logger.info(f"✅ Current Zen: {len(zen_data['spaces'])} workspaces, {len(zen_data.get('tabs', []))} tabs")

    # Clear existing tabs, folders, groups (fresh start)
    reset_zen_session_state(zen_data)

    # Create workspaces for Arc spaces
    base_timestamp = int(datetime.now().timestamp() * 1000)

    # Create workspace mapping
    workspace_map = {}
    for arc_space in arc_data['spaces']:
        space_name = arc_space['space_name']

        # Check if workspace already exists
        existing = next((s for s in zen_data['spaces'] if s['name'] == space_name), None)

        if existing:
            workspace_map[space_name] = existing['uuid']
            logger.info(f"📁 Using existing workspace: {space_name}")
        else:
            # Create new workspace
            new_workspace = {
                "uuid": generate_uuid(),
                "name": space_name,
                "theme": {
                    "type": "gradient",
                    "gradientColors": [],
                    "opacity": 0.5,
                    "texture": 0
                },
                "containerTabId": 0,
                "hasCollapsedPinnedTabs": False
            }
            zen_data['spaces'].append(new_workspace)
            workspace_map[space_name] = new_workspace['uuid']
            logger.info(f"📁 Created workspace: {space_name} -> {new_workspace['uuid']}")

    # Import tabs and folders with proper nesting
    tab_index = 0

    for arc_space in arc_data['spaces']:
        space_name = arc_space['space_name']
        workspace_uuid = workspace_map[space_name]

        logger.info(f"\n📦 Processing: {space_name}")
        logger.info(f"   {arc_space['total_pinned_tabs']} tabs, {arc_space['total_folders']} folders")

        # Build nested folder structure
        space_folders, space_groups, folder_map = build_folder_hierarchy(
            arc_space,
            workspace_uuid,
            base_timestamp + tab_index
        )

        zen_data['folders'].extend(space_folders)
        zen_data['groups'].extend(space_groups)
        tab_index += len(space_folders)

        # Process tabs
        for arc_tab in arc_space['pinned_tabs']:
            is_pinned = bool(arc_tab.get('is_pinned', True) or arc_tab.get('is_essential', False))
            # Determine which folder this tab belongs to
            folder_path = arc_tab.get('folder_path', [])

            if is_pinned:
                if folder_path:
                    folder_path_tuple = tuple(folder_path)
                    group_id = folder_map.get(folder_path_tuple)
                else:
                    # Arc allows pinned shortcuts directly at the workspace root.
                    group_id = None
            else:
                group_id = None

            # Create tab
            zen_tab = create_zen_tab(arc_tab, workspace_uuid, group_id, base_timestamp + tab_index, tab_index)
            zen_data['tabs'].append(zen_tab)
            tab_index += 1

        logger.info(f"   ✅ Added {arc_space['total_pinned_tabs']} tabs")
        tab_index = add_empty_folder_anchors(
            zen_data,
            space_folders,
            workspace_uuid,
            base_timestamp + tab_index,
            tab_index,
        )

    # Update timestamp
    zen_data['lastCollected'] = base_timestamp

    # Write back
    write_mozilla_lz4(sessions_file, zen_data)
    sync_sessionstore(profile, zen_data, nuke=args.nuke)

    logger.info(f"\n🎉 Migration Complete!")
    logger.info(f"   Workspaces: {len(zen_data['spaces'])}")
    logger.info(f"   Folders: {len(zen_data['folders'])}")
    logger.info(f"   Tabs: {len(zen_data['tabs'])}")
    logger.info(f"\n💡 Open Zen Browser ({profile.name} profile) to see your Arc tabs with proper nested folders!")

    return True


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
