#!/usr/bin/env python3
"""Sync Arc pinned-folder expanded/collapsed state into Zen."""

import json
import argparse
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from zen_sessions_importer_v4 import read_mozilla_lz4, resolve_zen_profile, write_mozilla_lz4
from src.profile_paths import arc_json_path


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

FolderKey = Tuple[str, Tuple[str, ...]]


def load_arc_json(name: str, arc_profile: str | Path | None = None) -> Dict[str, Any]:
    path = arc_json_path(name, arc_profile)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def expanded_arc_item_ids(windows_data: Dict[str, Any]) -> set[str]:
    expanded = set()
    for window in windows_data.get("windows", []):
        items = window.get("expandedItems", [])
        for i in range(0, len(items) - 1, 2):
            item_id = items[i]
            state = items[i + 1]
            if isinstance(item_id, str) and isinstance(state, dict) and "expanded" in state:
                expanded.add(item_id)
    return expanded


def alternating_pairs(values: list[Any]) -> Iterable[tuple[str, Any]]:
    for i in range(0, len(values) - 1, 2):
        if isinstance(values[i], str):
            yield values[i], values[i + 1]


def section_children(container_ids: list[str], marker: str, items_lookup: Dict[str, Any]) -> list[str]:
    if marker not in container_ids:
        return []

    children = []
    for container_id in container_ids[container_ids.index(marker) + 1 :]:
        if container_id in ("pinned", "unpinned"):
            break
        children.extend(items_lookup.get(container_id, {}).get("childrenIds", []))
    return children


def arc_folder_states(arc_profile: str | Path | None = None) -> Dict[FolderKey, bool]:
    sidebar = load_arc_json("StorableSidebar.json", arc_profile)
    windows = load_arc_json("StorableWindows.json", arc_profile)
    expanded_ids = expanded_arc_item_ids(windows)

    space_models = sidebar.get("firebaseSyncState", {}).get("syncData", {}).get("spaceModels", [])
    space_names = {
        space_id: space_data.get("value", {}).get("title", space_id)
        for space_id, space_data in alternating_pairs(space_models)
    }

    sidebar_container = sidebar.get("sidebar", {}).get("containers", [None, {}])[1]
    items_lookup = dict(alternating_pairs(sidebar_container.get("items", [])))

    states = {}

    def visit(space_name: str, path: tuple[str, ...], item_ids: list[str]):
        for item_id in item_ids:
            item = items_lookup.get(item_id, {})
            if "list" not in item.get("data", {}):
                continue

            folder_path = path + (item.get("title", "Untitled Folder"),)
            states[(space_name, folder_path)] = item_id in expanded_ids
            visit(space_name, folder_path, item.get("childrenIds", []))

    for space_id, space_data in alternating_pairs(sidebar_container.get("spaces", [])):
        space_name = space_names.get(space_id, space_id)
        pinned_children = section_children(space_data.get("containerIDs", []), "pinned", items_lookup)
        visit(space_name, (), pinned_children)

    return states


def zen_folder_paths(spaces: list[Dict[str, Any]], folders: list[Dict[str, Any]]) -> Dict[FolderKey, str]:
    space_names = {space.get("uuid"): space.get("name") for space in spaces}
    by_id = {folder.get("id"): folder for folder in folders}
    cache = {}

    def path_for(folder: Dict[str, Any]) -> tuple[str, ...]:
        folder_id = folder.get("id")
        if folder_id in cache:
            return cache[folder_id]

        parent_id = folder.get("parentId")
        if parent_id and parent_id in by_id:
            path = path_for(by_id[parent_id]) + (folder.get("name", ""),)
        else:
            path = (folder.get("name", ""),)

        cache[folder_id] = path
        return path

    mapping = {}
    for folder in folders:
        space_name = space_names.get(folder.get("workspaceId"))
        if not space_name:
            continue
        mapping[(space_name, path_for(folder))] = folder.get("id")

    return mapping


def set_folder_states(data: Dict[str, Any], states: Dict[FolderKey, bool]) -> tuple[int, int]:
    if "windows" in data:
        folders = data.get("windows", [{}])[0].get("folders", [])
        groups = data.get("windows", [{}])[0].get("groups", [])
        spaces = data.get("windows", [{}])[0].get("spaces", [])
    else:
        folders = data.get("folders", [])
        groups = data.get("groups", [])
        spaces = data.get("spaces", [])

    folder_ids = zen_folder_paths(spaces, folders)
    groups_by_id = {group.get("id"): group for group in groups}
    changed = 0
    matched = 0

    def folder_id_for(key: FolderKey) -> str | None:
        if key in folder_ids:
            return folder_ids[key]

        space_name, path = key
        for start in range(1, len(path)):
            suffix = path[start:]
            candidates = [
                folder_id
                for (candidate_space, candidate_path), folder_id in folder_ids.items()
                if candidate_space == space_name and candidate_path == suffix
            ]
            if len(candidates) == 1:
                return candidates[0]

        return None

    for key, expanded in states.items():
        folder_id = folder_id_for(key)
        if not folder_id:
            continue

        matched += 1
        collapsed = not expanded
        for obj in (next((folder for folder in folders if folder.get("id") == folder_id), None), groups_by_id.get(folder_id)):
            if isinstance(obj, dict) and obj.get("collapsed") != collapsed:
                obj["collapsed"] = collapsed
                changed += 1

    return matched, changed


def backup(path: Path, timestamp: str):
    backup_path = path.with_name(f"{path.name}.codex-folder-state-backup-{timestamp}")
    shutil.copy2(path, backup_path)
    logger.info(f"✅ Backed up {path.name} to {backup_path.name}")


def update_file(path: Path, states: Dict[FolderKey, bool], timestamp: str) -> tuple[int, int]:
    if not path.exists():
        logger.info(f"Skipping missing file: {path}")
        return 0, 0

    data = read_mozilla_lz4(path)
    matched, changed = set_folder_states(data, states)
    if changed:
        backup(path, timestamp)
        write_mozilla_lz4(path, data)

    logger.info(f"{path.name}: matched {matched} folders, changed {changed} collapsed fields")
    return matched, changed


def main() -> bool:
    parser = argparse.ArgumentParser(description="Sync Arc pinned-folder expanded/collapsed state into Zen.")
    parser.add_argument(
        "--arc-profile",
        help="Path to the Arc profile root containing StorableSidebar.json.",
    )
    parser.add_argument(
        "--zen-profile",
        help="Path to a Zen profile directory, or a Zen root containing profiles.ini.",
    )
    args = parser.parse_args()

    profile = resolve_zen_profile(args.zen_profile)
    states = arc_folder_states(args.arc_profile)
    expanded = sum(1 for value in states.values() if value)
    logger.info(f"Loaded Arc states for {len(states)} pinned folders: {expanded} expanded, {len(states) - expanded} collapsed")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    files = [
        profile / "zen-sessions.jsonlz4",
        profile / "sessionstore.jsonlz4",
        profile / "sessionstore-backups" / "recovery.jsonlz4",
    ]

    total_changed = 0
    for path in files:
        _, changed = update_file(path, states, timestamp)
        total_changed += changed

    logger.info(f"Done. Changed {total_changed} folder/group collapsed fields across Zen session files.")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
