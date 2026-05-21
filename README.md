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
- Auto-discovery for Arc desktop on Linux, because Arc desktop is currently
  known for macOS and Windows only.

## Requirements

- macOS.
- Python 3.10+.
- Arc Browser profile data at `~/Library/Application Support/Arc`.
- Zen Browser profile data at `~/Library/Application Support/zen`.
- Zen Browser must be closed before writing session files.
- For the desktop app: PySide6 and psutil from `requirements-desktop.txt`.
- For local desktop binary builds: PyInstaller from `requirements-build.txt`.

Install the Python dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

For the desktop app, install the desktop extras instead:

```bash
pip install -r requirements-desktop.txt
```

## Desktop App

Launch the GUI:

```bash
python desktop_app.py
```

The desktop app provides a small cross-platform wrapper around the migration
modules:

- Auto-detects likely Arc and Zen profiles on the current OS.
- Lets you browse for an Arc profile root and a Zen profile/root manually.
- Lets you choose optional migration steps: favicons, folder open/closed state,
  workspace icons, and workspace colors/themes.
- Includes a dangerous nuke option to clear the selected Zen profile before
  recreating data from Arc.
- Shows a confirmation dialog with the pending source, target, selected steps,
  and nuke setting before doing anything.
- Checks whether Zen is running, asks to close it, and only starts migration
  after Zen has exited.
- Streams progress output while each migration step runs.

The GUI writes the intermediate Arc export to a temporary directory and removes
it when the run finishes.

## Desktop Binary Builds

Install build dependencies:

```bash
pip install -r requirements-build.txt
```

Build a one-file executable for the current OS:

```bash
python scripts/build_desktop.py --version dev
```

The build script uses PyInstaller and writes release archives into
`release-artifacts/`:

- Windows: `arc-to-zen-<version>-windows-x64.zip`, containing `arc-to-zen.exe`.
- macOS/Linux: `arc-to-zen-<version>-<platform>.tar.gz`, containing the
  `arc-to-zen` executable.

The project does not cross-compile. Build each platform on a matching OS, which
is what the release GitHub Action does.

## Release Process

Normal development lands on `main` through regular commits and pull requests.
The CI workflow runs a Python syntax check on every push to `main` and every
pull request.

To publish downloadable desktop binaries:

```bash
git checkout main
git pull origin main
git tag v0.1.0
git push origin v0.1.0
```

Pushing a `v*` tag triggers `.github/workflows/release.yml`. The workflow builds
Linux x64, Windows x64, macOS x64, and macOS arm64 executables, then creates or
updates the matching GitHub Release with the generated archives attached.

The release workflow can also be run manually from GitHub Actions with an
existing tag name.

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

`desktop_app.py`, `zen_sessions_importer_v4.py`, and the sync scripts resolve
the Zen profile in this order:

1. Explicit `--zen-profile` argument or GUI selection.
2. `ZEN_PROFILE_PATH`, if set.
3. `ZEN_PROFILE_NAME`, matched against profile directory names.
4. Zen's `installs.ini` default profile.
5. Zen's `profiles.ini` default profile.
6. The first discovered profile containing `zen-sessions.jsonlz4`.

Examples:

```bash
ZEN_PROFILE_NAME="Default" python zen_sessions_importer_v4.py --nuke
ZEN_PROFILE_PATH="$HOME/Library/Application Support/zen/Profiles/xxxxxxxx.Default" python sync_arc_workspace_themes.py
```

Arc profile selection works similarly:

```bash
ARC_PROFILE_PATH="$HOME/Library/Application Support/Arc" python src/arc_pinned_tab_extractor.py
python src/arc_pinned_tab_extractor.py --arc-profile "$HOME/Library/Application Support/Arc"
```

The scanner checks:

- Arc macOS: `~/Library/Application Support/Arc`
- Arc Windows: `%LOCALAPPDATA%\Packages\TheBrowserCompany.Arc_*\LocalCache\Local\Arc`
- Zen macOS: `~/Library/Application Support/zen`
- Zen Windows: `%APPDATA%\zen`
- Zen Linux tarball/AppImage: `~/.zen`
- Zen Linux Flatpak candidates: `~/.var/app/app.zen_browser.zen/zen` and
  `~/.var/app/app.zen_browser.zen/.zen`

Arc desktop Linux is not scanned by default because current evidence points to
Arc desktop being macOS/Windows only.

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
├── requirements-desktop.txt
├── requirements-build.txt
├── desktop_app.py
├── scripts/
│   └── build_desktop.py
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── src/
│   ├── __init__.py
│   ├── arc_pinned_tab_extractor.py
│   └── profile_paths.py
├── zen_sessions_importer_v4.py
├── migrate_arc_favicons.py
├── sync_arc_folder_states.py
├── sync_arc_workspace_icons.py
└── sync_arc_workspace_themes.py
```

Generated files such as `arc_pinned_tabs_export.json`, local virtualenvs,
Python bytecode, local snapshots, PyInstaller build output, release archives,
and Zen backup files are ignored by Git.

## Technical Notes

Arc data sources:

- `StorableSidebar.json` contains spaces, pinned/unpinned sidebar containers,
  sidebar items, folders, tabs, icons, and workspace themes.
- `StorableWindows.json` contains expanded/collapsed sidebar state.
- `User Data/Default/Favicons` contains Chromium favicon bitmaps.
- `User Data/Profile */Favicons` is also scanned for non-default Chromium
  profiles.

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

Profile path references used by the scanner:

- [Zen Linux install docs](https://docs.zen-browser.app/guides/install-linux)
- [Zen Window Sync & Recovery docs](https://docs.zen-browser.app/user-manual/window-sync)
- [Zen session manager source](https://github.com/zen-browser/desktop/blob/dev/src/zen/sessionstore/ZenSessionManager.sys.mjs)
- [Zen Flatpak manifest](https://github.com/zen-browser/desktop/blob/dev/build/flatpak/app.zen_browser.zen.yml.template)
- [ArcEscape Arc export path notes](https://arcescape.com/blog/how-to-export-arc-browser-bookmarks)

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
  src/profile_paths.py \
  src/arc_pinned_tab_extractor.py \
  zen_sessions_importer_v4.py \
  migrate_arc_favicons.py \
  sync_arc_folder_states.py \
  sync_arc_workspace_icons.py \
  sync_arc_workspace_themes.py \
  desktop_app.py \
  scripts/build_desktop.py
```

The scripts are intentionally small and direct. The importer owns the Zen session
read/write helpers so the post-import sync scripts can reuse the same profile
resolution and Mozilla LZ4 handling.
