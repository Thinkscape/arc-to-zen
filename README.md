# Arc to Zen Browser Migration Tool

A Python migration tool for moving Arc Browser sidebar data into Zen Browser.

The tool reads Arc's local sidebar/session metadata and writes Zen's compressed
session files. It now migrates pinned tabs, temporary open tabs, nested pinned
folders, workspace icons, workspace themes, folder open/closed state, and cached
favicons.

Tested on macOS with Zen Browser's `zen-sessions.jsonlz4` and Firefox-style
`sessionstore.jsonlz4` files.

## What Gets Migrated

Supported:

- Arc spaces to Zen workspaces.
- Arc pinned sidebar tabs to Zen pinned tabs.
- Arc Essential tabs to Zen essential pinned tabs.
- Arc temporary/unpinned tabs to normal open Zen tabs.
- Nested pinned folders, including folder-only parent folders.
- Top-level pinned shortcuts without wrapping them in synthetic folders.
- Workspace emoji icons and Arc/Zen built-in icon names.
- Workspace color themes, including Arc gradient/single colors, intensity, and grain.
- Pinned-folder expanded/collapsed state.
- Cached favicons from Arc's Chromium favicon database.

Not supported:

- Arc Boosts, Easels, and other Arc-only features.
- Full browsing history.
- Folder colors/icons beyond Zen's supported folder state.
- Cross-platform paths outside macOS.

## Requirements

- macOS.
- Python 3.10+.
- Arc Browser profile data at `~/Library/Application Support/Arc`.
- Zen Browser profile data at `~/Library/Application Support/zen`.
- Zen Browser must be closed before writing session files.

Install the Python dependency:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

Close Zen before running any import or sync command.

```bash
python src/arc_pinned_tab_extractor.py
python zen_sessions_importer_v4.py
python migrate_arc_favicons.py
python sync_arc_folder_states.py
python sync_arc_workspace_icons.py
python sync_arc_workspace_themes.py
```

For the cleanest recreation of Zen from Arc, use nuke mode:

```bash
python src/arc_pinned_tab_extractor.py
python zen_sessions_importer_v4.py --nuke
python migrate_arc_favicons.py
python sync_arc_folder_states.py
python sync_arc_workspace_icons.py
python sync_arc_workspace_themes.py
```

`--nuke` is destructive for the target Zen profile. It removes existing Zen tabs,
folders, pins, tab groups, closed tab state, and non-root bookmarks before
rebuilding from Arc. The scripts create timestamped backups next to the changed
Zen files before writing.

## Profile Selection

`zen_sessions_importer_v4.py` and the sync scripts resolve the Zen profile in
this order:

1. `ZEN_PROFILE_PATH`, if set.
2. `ZEN_PROFILE_NAME`, matched against profile directory names.
3. Zen's `installs.ini` default profile.
4. Zen's `profiles.ini` default profile.
5. The first profile containing `zen-sessions.jsonlz4`.

Examples:

```bash
ZEN_PROFILE_NAME="Default" python zen_sessions_importer_v4.py --nuke
ZEN_PROFILE_PATH="$HOME/Library/Application Support/zen/Profiles/xxxxxxxx.Default" python sync_arc_workspace_themes.py
```

## Commands

### Extract Arc Data

```bash
python src/arc_pinned_tab_extractor.py
```

Reads `StorableSidebar.json` and writes `arc_pinned_tabs_export.json`.

The export includes each Arc space, pinned tabs, temporary/unpinned tabs, folder
paths, folder records, essential-tab flags, workspace icons, and a basic color
field.

### Import Arc Data Into Zen

```bash
python zen_sessions_importer_v4.py
```

Writes Arc data into:

- `zen-sessions.jsonlz4`
- `sessionstore.jsonlz4`, when present
- `sessionstore-backups/recovery.jsonlz4`, when present

This importer clears the current session tab/folder/group state before importing
the extracted Arc data. Existing workspace records are reused by name when
possible.

Options:

```bash
python zen_sessions_importer_v4.py --nuke
python zen_sessions_importer_v4.py --nuke-only
```

`--nuke-only` clears the target Zen profile without importing Arc data afterward.

### Copy Favicons

```bash
python migrate_arc_favicons.py
```

Reads Arc's Chromium favicon cache at
`~/Library/Application Support/Arc/User Data/Default/Favicons` and embeds data
URI favicon images into matching Zen tabs.

### Sync Folder State

```bash
python sync_arc_folder_states.py
```

Reads Arc's `StorableWindows.json` expanded-item state and applies matching
collapsed/expanded state to Zen folders and groups.

### Sync Workspace Icons

```bash
python sync_arc_workspace_icons.py
```

Maps Arc emoji workspace icons and built-in icon names onto Zen workspace icons.

### Sync Workspace Themes

```bash
python sync_arc_workspace_themes.py
```

Translates Arc workspace theme data into Zen's saved workspace theme format:

- Arc gradient base colors to Zen `gradientColors`.
- Arc single workspace colors to a one-color Zen theme.
- Arc `intensityFactor` to Zen theme opacity.
- Arc grain/noise settings to Zen texture.

Workspaces without an Arc theme are left unchanged/default.

## Project Structure

```text
arc-to-zen/
├── README.md
├── requirements.txt
├── src/
│   └── arc_pinned_tab_extractor.py
├── zen_sessions_importer_v4.py
├── migrate_arc_favicons.py
├── sync_arc_folder_states.py
├── sync_arc_workspace_icons.py
└── sync_arc_workspace_themes.py
```

Generated files such as `arc_pinned_tabs_export.json`, local virtualenvs,
Python bytecode, local snapshots, and Zen backup files are ignored by Git.

## Technical Notes

Arc data sources:

- `StorableSidebar.json` contains spaces, pinned/unpinned sidebar containers,
  sidebar items, folders, tabs, icons, and workspace themes.
- `StorableWindows.json` contains expanded/collapsed sidebar state.
- `User Data/Default/Favicons` contains Chromium favicon bitmaps.

Zen data targets:

- `zen-sessions.jsonlz4` stores Zen workspaces, pinned tabs, folders, groups,
  split-view data, and workspace theme/icon metadata.
- `sessionstore.jsonlz4` and `sessionstore-backups/recovery.jsonlz4` store
  Firefox-style window session state. Updating these is required for temporary
  tabs to reopen as normal open tabs.
- `places.sqlite` stores bookmarks. Nuke mode deletes only non-root bookmark
  rows and keeps Firefox/Zen root bookmark records.

Zen's compressed JSON files use Mozilla LZ4 framing: an 8-byte magic header,
a 4-byte little-endian uncompressed size, then an LZ4 block.

## Safety

- Arc files are read-only inputs.
- Zen must be closed while writing session files.
- Every changed Zen JSONLZ4 file is backed up before writing.
- Nuke mode also backs up `places.sqlite` and its WAL/SHM files when present.
- To inspect the Arc export before import, run:

```bash
python src/arc_pinned_tab_extractor.py
python -m json.tool arc_pinned_tabs_export.json | less
```

## Development

Run a syntax check:

```bash
python -m py_compile \
  src/arc_pinned_tab_extractor.py \
  zen_sessions_importer_v4.py \
  migrate_arc_favicons.py \
  sync_arc_folder_states.py \
  sync_arc_workspace_icons.py \
  sync_arc_workspace_themes.py
```

The scripts are intentionally small and direct. The importer owns the Zen session
read/write helpers so the post-import sync scripts can reuse the same profile
resolution and Mozilla LZ4 handling.
