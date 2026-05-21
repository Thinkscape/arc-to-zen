# AGENTS.md

This repository contains Python scripts for migrating Arc Browser sidebar data
into Zen Browser on macOS.

## Current Migration Flow

Zen must be closed before any command that writes Zen profile files.

Desktop UI:

```bash
pip install -r requirements-desktop.txt
python desktop_app.py
```

CLI equivalent:

```bash
python src/arc_pinned_tab_extractor.py
python zen_sessions_importer_v4.py --nuke
python migrate_arc_favicons.py
python sync_arc_folder_states.py
python sync_arc_workspace_icons.py
python sync_arc_workspace_themes.py
```

`--nuke` is destructive for the target Zen profile: it clears tabs, folders,
pins, groups, closed-tab state, and regular bookmarks before importing Arc data.
Use `--nuke-only` to perform only that cleanup.

## Main Files

- `src/arc_pinned_tab_extractor.py`
  - Reads Arc `StorableSidebar.json`.
  - Exports Arc spaces, pinned tabs, temporary/unpinned tabs, essential tabs,
    folders, icons, and a basic color field.
  - Writes `arc_pinned_tabs_export.json`, which is ignored by Git.

- `src/profile_paths.py`
  - Discovers and validates Arc/Zen profile paths across supported platforms.
  - Arc scans macOS Application Support and Windows Store-package roots.
  - Zen scans macOS Application Support, Windows AppData, Linux tarball/AppImage
    `~/.zen`, and both documented/manifest-derived Flatpak roots.
  - Parses Zen `profiles.ini` and `installs.ini` before falling back to profile
    directories containing `zen-sessions.jsonlz4`.

- `desktop_app.py`
  - PySide6 GUI wrapper around the CLI scripts.
  - Lets users pick Arc/Zen profiles, optional migration steps, and nuke mode.
  - Confirms pending parameters, closes Zen before running, then streams CLI
    progress into the UI.
  - Uses a temporary export file so GUI runs do not leave `arc_pinned_tabs_export.json`.

- `zen_sessions_importer_v4.py`
  - Reads `arc_pinned_tabs_export.json`.
  - Resolves the Zen profile from `ZEN_PROFILE_PATH`, `ZEN_PROFILE_NAME`,
    Zen defaults, or the first profile containing `zen-sessions.jsonlz4`.
  - Writes `zen-sessions.jsonlz4`.
  - Also syncs `sessionstore.jsonlz4` and `sessionstore-backups/recovery.jsonlz4`
    so temporary/unpinned Arc tabs reopen as normal Zen tabs.
  - Preserves top-level pinned shortcuts instead of creating synthetic folders.
  - Creates hidden empty anchor tabs for folder-only parent folders so nested
    folder hierarchy survives in Zen.

- `migrate_arc_favicons.py`
  - Reads Arc's Chromium favicon database in read-only immutable SQLite mode.
  - Copies matching favicons into Zen tab `image` and pinned initial state.

- `sync_arc_folder_states.py`
  - Reads Arc `StorableWindows.json` expanded-item state.
  - Applies Zen folder/group `collapsed` state by matching workspace and folder
    path.

- `sync_arc_workspace_icons.py`
  - Maps Arc emoji icons and built-in icon names into Zen workspace icons.

- `sync_arc_workspace_themes.py`
  - Converts Arc gradient or single-color workspace themes into Zen workspace
    `theme.gradientColors`, `opacity`, and `texture`.

## Data Sources

Arc:

- `~/Library/Application Support/Arc/StorableSidebar.json`
- `~/Library/Application Support/Arc/StorableWindows.json`
- `~/Library/Application Support/Arc/User Data/Default/Favicons`

Zen:

- `~/Library/Application Support/zen/Profiles/<profile>/zen-sessions.jsonlz4`
- `~/Library/Application Support/zen/Profiles/<profile>/sessionstore.jsonlz4`
- `~/Library/Application Support/zen/Profiles/<profile>/sessionstore-backups/recovery.jsonlz4`
- `~/Library/Application Support/zen/Profiles/<profile>/places.sqlite`

## Implementation Notes

- Arc source files are read only.
- Zen JSONLZ4 files use Mozilla's format: 8-byte magic header, 4-byte
  little-endian uncompressed size, then an LZ4 block.
- Scripts create timestamped backups before mutating Zen profile files.
- Generated exports, snapshots, local virtualenvs, bytecode, and backup files
  should remain untracked.

## Verification

Syntax check:

```bash
python -m py_compile \
  src/profile_paths.py \
  src/arc_pinned_tab_extractor.py \
  zen_sessions_importer_v4.py \
  migrate_arc_favicons.py \
  sync_arc_folder_states.py \
  sync_arc_workspace_icons.py \
  sync_arc_workspace_themes.py \
  desktop_app.py
```

Run the theme/icon/folder/favicon sync scripts twice to check idempotence; the
second run should report zero changes when Zen files are already in sync.
