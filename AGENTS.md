# AGENTS.md

This repository contains a Python package to migrate all Arc workspaces data
into Zen.

## Current Migration Flow

Zen must be closed before any command that writes Zen profile files.

Desktop UI:

```bash
pip install -e ".[desktop]"
python desktop.py
```

Local desktop package build:

```bash
pip install -e ".[build]"
python scripts/build_desktop.py --version dev
```

CLI equivalent:

```bash
python cli.py --nuke
```

`--nuke` is destructive for the target Zen profile: it clears tabs, folders,
pins, groups, closed-tab state, and regular bookmarks before importing Arc data.
Use `--nuke-only` to perform only that cleanup.

## Main Files

- `src/arc2zen/extract.py`
  - Reads Arc `StorableSidebar.json`.
  - Exports Arc spaces, pinned tabs, temporary/unpinned tabs, essential tabs,
    folders, icons, and a basic color field.
  - Writes `arc_pinned_tabs_export.json`, which is ignored by Git.

- `src/arc2zen/profile_paths.py`
  - Discovers and validates Arc/Zen profile paths across supported platforms.
  - Arc scans macOS Application Support and Windows Store-package roots.
  - Zen scans macOS Application Support, Windows AppData, Linux tarball/AppImage
    `~/.zen`, and both documented/manifest-derived Flatpak roots.
  - Parses Zen `profiles.ini` and `installs.ini` before falling back to profile
    directories containing `zen-sessions.jsonlz4`.

- `src/arc2zen/migration.py`
  - Shared migration orchestration used by both CLI and GUI.
  - Owns the ordered step list for core import, favicons, folder states,
    workspace icons, and workspace themes.

- `src/arc2zen/cli.py`
  - Unified CLI with switches for profile selection, nuke mode, nuke-only mode,
    and optional migration elements.

- `src/arc2zen/desktop.py`
  - PySide6 GUI wrapper around the shared migration orchestrator.
  - Lets users pick Arc/Zen profiles, optional migration steps, and nuke mode.
  - Confirms pending parameters, closes Zen before running, then streams
    migration progress into the UI.
  - Uses a temporary export file so GUI runs do not leave `arc_pinned_tabs_export.json`.

- Root `cli.py` and `desktop.py`
  - Thin user-facing entrypoints for the packaged CLI and GUI.

- `scripts/build_desktop.py`
  - Builds a PyInstaller native-style package for the current OS.
  - macOS emits `Arc to Zen.app`, Windows emits a windowed app folder, and
    Linux emits an app folder with a `.desktop` entry.
  - Packages output into `release-artifacts/`.
  - Uses native builds, not cross-compilation.

- `assets/app-icon.svg`
  - Source app icon. It is an original Arc/Zen-inspired migration mark, not a
    direct copy of either browser logo.
  - Run `python scripts/generate_icon_assets.py` after editing it.

- `scripts/render_readme_screenshot.py`
  - Renders `docs/app-screenshot.png` from the actual Qt window.

- `.github/workflows/ci.yml`
  - Runs the Python syntax check on pushes to `main` and pull requests.

- `.github/workflows/release.yml`
  - Runs on pushed `v*` tags or manual dispatch for an existing tag.
  - Builds Linux x64, Windows x64, macOS x64, and macOS arm64 artifacts.
  - Creates or updates the matching GitHub Release with the build archives.

- `src/arc2zen/sessions.py`
  - Reads `arc_pinned_tabs_export.json`.
  - Resolves the Zen profile from `ZEN_PROFILE_PATH`, `ZEN_PROFILE_NAME`,
    Zen defaults, or the first profile containing `zen-sessions.jsonlz4`.
  - Writes `zen-sessions.jsonlz4`.
  - Also syncs `sessionstore.jsonlz4` and `sessionstore-backups/recovery.jsonlz4`
    so temporary/unpinned Arc tabs reopen as normal Zen tabs.
  - Preserves top-level pinned shortcuts instead of creating synthetic folders.
  - Creates hidden empty anchor tabs for folder-only parent folders so nested
    folder hierarchy survives in Zen.

- `src/arc2zen/favicons.py`
  - Reads Arc's Chromium favicon database in read-only immutable SQLite mode.
  - Copies matching favicons into Zen tab `image` and pinned initial state.

- `src/arc2zen/folder_states.py`
  - Reads Arc `StorableWindows.json` expanded-item state.
  - Applies Zen folder/group `collapsed` state by matching workspace and folder
    path.

- `src/arc2zen/workspace_icons.py`
  - Maps Arc emoji icons and built-in icon names into Zen workspace icons.

- `src/arc2zen/workspace_themes.py`
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
- Migration steps create timestamped backups before mutating Zen profile files.
- Generated exports, snapshots, local virtualenvs, bytecode, and backup files
  should remain untracked.

## Verification

Syntax check:

```bash
python -m py_compile \
  cli.py \
  desktop.py \
  src/arc2zen/*.py \
  scripts/build_desktop.py \
  scripts/generate_icon_assets.py \
  scripts/render_readme_screenshot.py
```

Release a new version:

```bash
git checkout main
git pull origin main
git tag v0.1.0
git push origin v0.1.0
```

Run the optional theme/icon/folder/favicon modules twice against a disposable
Zen profile to check idempotence; the second run should report zero changes
when Zen files are already in sync.
