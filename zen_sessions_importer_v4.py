#!/usr/bin/env python3
"""
Zen Sessions Importer v4 - Proper Nested Folders

Supports nested folder structures with correct parentId relationships.
"""

import lz4.block
import json
import logging
import struct
import uuid
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def read_mozilla_lz4(filepath: Path) -> Dict[str, Any]:
    """Read Mozilla's LZ4-compressed JSON file."""
    with open(filepath, 'rb') as f:
        magic = f.read(8)
        if magic != b'mozLz40\x00':
            raise ValueError("Not a valid mozLz4 file")

        size_bytes = f.read(4)
        uncompressed_size = struct.unpack('<I', size_bytes)[0]
        compressed = f.read()
        decompressed = lz4.block.decompress(compressed, uncompressed_size=uncompressed_size)
        return json.loads(decompressed)


def write_mozilla_lz4(filepath: Path, data: Dict[str, Any]):
    """Write data in Mozilla's LZ4-compressed JSON format."""
    backup_path = filepath.with_suffix('.jsonlz4.bak')
    if filepath.exists():
        shutil.copy2(filepath, backup_path)
        logger.info(f"✅ Backed up to {backup_path.name}")

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
        "pinned": True,
        "hidden": False,
        "groupId": group_id,
        "zenWorkspace": workspace_uuid,
        "zenSyncId": sync_id,
        "zenEssential": arc_tab.get('is_essential', False),
        "zenDefaultUserContextId": None,
        "zenPinnedIcon": None,
        "zenIsEmpty": False,
        "zenHasStaticIcon": False,
        "zenGlanceId": None,
        "zenIsGlance": False,
        "_zenPinnedInitialState": {
            "entry": entry.copy(),
            "image": None
        },
        "_zenIsActiveTab": False,
        "searchMode": None,
        "userContextId": 0,
        "attributes": {},
        "index": tab_index,
        "image": ""
    }

    return tab


def create_zen_folder(folder_name: str, workspace_uuid: str, timestamp: int, parent_folder_id: str = None) -> Tuple[Dict, Dict, str]:
    """Create a Zen folder and group entry with proper parent relationship."""
    folder_id = f"{timestamp}-{abs(hash(folder_name + str(parent_folder_id))) % 10000}"

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

    # First, collect all unique folder paths from tabs
    all_folder_paths = set()
    for tab in arc_space['pinned_tabs']:
        folder_path = tab.get('folder_path', [])
        if folder_path:
            # Add each level of the path
            for i in range(1, len(folder_path) + 1):
                all_folder_paths.add(tuple(folder_path[:i]))

    # Sort by depth (shortest first) to create parents before children
    sorted_paths = sorted(all_folder_paths, key=len)

    counter = 0
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

        # Log with indentation to show hierarchy
        indent = "  " * (len(folder_path_tuple) - 1)
        parent_info = f" (parent: {parent_folder_id})" if parent_folder_id else " (root)"
        logger.info(f"   {indent}📂 Created folder: {folder_name}{parent_info}")

        counter += 1

    return folders, groups, folder_map


def main():
    """Import Arc tabs into Zen PROFILE profile with proper nested folders."""
    # Use PROFILE profile
    zen_profile = Path.home() / "Library" / "Application Support" / "zen" / "Profiles"
    profile = None
    for p in zen_profile.iterdir():
        if p.is_dir() and "PROFILE" in p.name:
            profile = p
            break

    if not profile:
        logger.error("❌ PROFILE profile not found")
        return False

    logger.info(f"✅ Using profile: {profile.name}")

    sessions_file = profile / "zen-sessions.jsonlz4"
    arc_export_file = Path("arc_pinned_tabs_export.json")

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
    zen_data['tabs'] = []
    zen_data['folders'] = []
    zen_data['groups'] = []

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
            # Determine which folder this tab belongs to
            folder_path = arc_tab.get('folder_path', [])

            if folder_path:
                folder_path_tuple = tuple(folder_path)
                group_id = folder_map.get(folder_path_tuple)
            else:
                # Tab has no folder - create a default folder for loose tabs
                default_folder_name = f"{space_name} Tabs"
                default_folder_key = (default_folder_name,)

                if default_folder_key not in folder_map:
                    folder, group, folder_id = create_zen_folder(
                        default_folder_name,
                        workspace_uuid,
                        base_timestamp + tab_index
                    )
                    zen_data['folders'].append(folder)
                    zen_data['groups'].append(group)
                    folder_map[default_folder_key] = folder_id
                    logger.info(f"   📂 Created default folder: {default_folder_name}")
                    tab_index += 1

                group_id = folder_map[default_folder_key]

            # Create tab
            zen_tab = create_zen_tab(arc_tab, workspace_uuid, group_id, base_timestamp + tab_index, tab_index)
            zen_data['tabs'].append(zen_tab)
            tab_index += 1

        logger.info(f"   ✅ Added {arc_space['total_pinned_tabs']} tabs")

    # Update timestamp
    zen_data['lastCollected'] = base_timestamp

    # Write back
    write_mozilla_lz4(sessions_file, zen_data)

    logger.info(f"\n🎉 Migration Complete!")
    logger.info(f"   Workspaces: {len(zen_data['spaces'])}")
    logger.info(f"   Folders: {len(zen_data['folders'])}")
    logger.info(f"   Tabs: {len(zen_data['tabs'])}")
    logger.info(f"\n💡 Open Zen Browser (PROFILE profile) to see your Arc tabs with proper nested folders!")

    return True


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
