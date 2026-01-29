# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based migration tool that converts Arc browser pinned sidebar tabs (with nested folders) into Zen browser workspaces with proper folder hierarchy. The tool preserves Arc's organizational structure including nested folders, tab ordering, and workspace assignments.

**Key Achievement:** Successfully migrated 850+ tabs with 83 nested folders across 4 workspaces, preserving Arc's exact visual ordering and 3+ level folder hierarchies.

## Common Commands

### Migration Commands
```bash
# Step 1: Extract Arc pinned tabs
python3 src/arc_pinned_tab_extractor.py

# Step 2: Run the migration to your Zen profile
python3 zen_sessions_importer_v4.py
```

**Prerequisites:**
- Python 3.7+
- `pip3 install lz4` (for Mozilla's LZ4 compression format)
- Close Zen browser before running migration
- Recommended: Create fresh Zen profile for testing

## Architecture Overview

### Migration Pipeline (2-Step Process)
1. **Arc Data Extraction** (`src/arc_pinned_tab_extractor.py`)
   - Extracts from `~/Library/Application Support/Arc/StorableSidebar.json`
   - Identifies Arc spaces and pinned sidebar tabs (NOT open tabs)
   - Preserves folder hierarchy and visual ordering via container childrenIds
   - Handles orphaned Essential tabs (creates separate "Orphaned" workspace)
   - Outputs: `arc_pinned_tabs_export.json`

2. **Zen Session Import** (`zen_sessions_importer_v4.py`)
   - Reads exported Arc data
   - Builds nested folder structure with proper parentId relationships
   - Creates Zen workspaces, folders, and tabs
   - Writes to `zen-sessions.jsonlz4` using Mozilla's LZ4 compression
   - Creates automatic backup before modifications

### Key Components

**`src/arc_pinned_tab_extractor.py`** - Arc data extraction (core component)
- Parses Arc's nested JSON structure with Firebase sync data
- Extracts ONLY pinned tabs (containers between 'pinned' and 'unpinned' markers)
- Preserves Arc's visual ordering using container childrenIds arrays
- Builds folder hierarchy with full path tracking
- Handles orphaned Essential tabs from inactive profiles
- Data classes: `ArcPinnedTab`, `ArcFolder`, `ArcSpace`
- Critical fix: `pinned_index < idx < unpinned_index` for correct container selection

**`zen_sessions_importer_v4.py`** - Zen session file writer
- Creates workspaces for each Arc space
- Implements nested folders with parentId relationships (not flat!)
- Generates proper Zen tab/folder/group structures
- Mozilla LZ4 compression: 8-byte magic header + 4-byte size + compressed JSON
- Folder creation order: sorted by depth (parents before children)

### Data Flow

**Arc Source:**
```
~/Library/Application Support/Arc/StorableSidebar.json
├── firebaseSyncState.syncData.spaceModels (space metadata: names, icons, colors)
├── sidebar.containers[1].items (all sidebar items as ID/data pairs)
│   ├── Each space has containerIDs: ['pinned', UUID, 'unpinned', UUID]
│   ├── PINNED items: containers BETWEEN 'pinned' and 'unpinned' markers
│   └── Container childrenIds arrays define visual ordering
└── Folder hierarchy via childrenIds and parentID relationships
```

**Intermediate Export:**
```json
arc_pinned_tabs_export.json
{
  "spaces": [
    {
      "space_name": "Work",
      "pinned_tabs": [
        {
          "title": "...",
          "url": "...",
          "folder_path": ["Jira", "OCP", "TLS 1.3"],  // Full hierarchy
          "is_essential": false
        }
      ],
      "folders": [...],
      "total_pinned_tabs": 203,
      "total_folders": 32
    }
  ]
}
```

**Zen Target:**
```
~/Library/Application Support/zen/Profiles/[profile]/zen-sessions.jsonlz4
(Mozilla LZ4 compressed JSON file - NOT SQL database!)

After decompression:
{
  "spaces": [{"uuid": "{...}", "name": "Work", ...}],
  "folders": [
    {"id": "1234", "name": "Jira", "parentId": null, "workspaceId": "{...}"},
    {"id": "5678", "name": "OCP", "parentId": "1234", "workspaceId": "{...}"},
    {"id": "9012", "name": "TLS 1.3", "parentId": "5678", "workspaceId": "{...}"}
  ],
  "groups": [{...}],  // Duplicates folder info
  "tabs": [
    {
      "entries": [{"url": "...", "title": "..."}],
      "groupId": "9012",  // Points to folder
      "zenWorkspace": "{...}",  // Points to workspace
      "pinned": true
    }
  ]
}
```

## Important Implementation Details

### Order Preservation (SOLVED - The Container childrenIds Solution)

**✅ SOLUTION IMPLEMENTED**: Arc's exact visual ordering is now preserved using container-based extraction.

**The Discovery:**
Arc's storage order ≠ display order. Each space has a **container UUID** (not "pinned" string) that contains a `childrenIds` array with items in **exact Arc display order**.

**Correct Data Structure:**
```json
// Each space has containerIDs like:
space_data.containerIDs = ['unpinned', 'uuid-1', 'pinned', 'uuid-2']

// The actual display order is in one of the UUID containers:
data.sidebar.containers[1].items['BDF69180-4E9B-4B4A-B1B4-D6950292683E'].childrenIds = [
  "ACEB0219-BA17-4ADC-BCCB-FF83840AE8DF",  // Finances folder (1st in Arc)
  "4A4CEAC3-53C4-4D04-9EED-B3967CD11904",  // Large Language Models (2nd)
  "BA5EC227-0247-4639-8125-0EA21C4554CC",  // Health folder (3rd)
  // ... etc in exact Arc visual order
]
```

**Key Insight:** The string "pinned" is just a logical identifier - the actual display order is stored in a **container UUID** with `childrenIds`.

**Implementation (Working):**
```python
def _get_space_display_order(self, space_id: str, items_lookup: Dict, data: Dict) -> List[str]:
    """Get display order using container childrenIds (Arc's true visual order)."""
    space_container_ids = self._get_space_container_ids(space_id, data)

    # Look for containers with childrenIds (skip 'pinned'/'unpinned' strings)
    for container_id in space_container_ids:
        if container_id in ['pinned', 'unpinned']:
            continue

        # Find this UUID in items and check for childrenIds
        container_data = items_lookup.get(container_id, {})
        children_ids = container_data.get('childrenIds', [])
        if children_ids:
            return children_ids  # This is the display order!

    return []
```

**Results Achieved:**
- **Before**: Site, Games, Large Language Models... (Arc index 6, 20, 24)
- **After**: Finances, Large Language Models, Health, Games... (Arc visual order) ✅
- **Perfect match**: Extraction now matches Arc sidebar exactly

**Process Flow:**
1. **Find space container UUIDs** from `space_data.containerIDs`
2. **Locate display container** that has `childrenIds` array
3. **Extract in order** using `childrenIds` sequence (not Arc index sorting)
4. **Process recursively** for folder contents using their own `childrenIds`

### Nested Folder Implementation (v4 Solution)

**The Challenge:** Arc folders can nest 3+ levels deep (e.g., `Jira > OCP > TLS 1.3`). Early versions created flat folders with concatenated names (`"Jira > OCP > TLS 1.3"`).

**The Solution:** Proper `parentId` relationships in Zen's folder structure.

**Algorithm:**
```python
# 1. Collect all unique folder paths from tabs
all_folder_paths = set()
for tab in arc_space['pinned_tabs']:
    folder_path = tab.get('folder_path', [])  # e.g., ["Jira", "OCP", "TLS 1.3"]
    if folder_path:
        for i in range(1, len(folder_path) + 1):
            all_folder_paths.add(tuple(folder_path[:i]))
# Result: {("Jira",), ("Jira", "OCP"), ("Jira", "OCP", "TLS 1.3")}

# 2. Sort by depth (shortest first) - parents before children
sorted_paths = sorted(all_folder_paths, key=len)

# 3. Create folders with proper parent references
for folder_path_tuple in sorted_paths:
    folder_name = folder_path_tuple[-1]
    parent_folder_id = None
    if len(folder_path_tuple) > 1:
        parent_path = folder_path_tuple[:-1]
        parent_folder_id = folder_map.get(parent_path)

    create_zen_folder(folder_name, workspace_uuid, timestamp, parent_folder_id)
    folder_map[folder_path_tuple] = folder_id
```

**Result:**
- Jira folder: `parentId: null` (root)
- OCP folder: `parentId: "1234"` (Jira's ID)
- TLS 1.3 folder: `parentId: "5678"` (OCP's ID)

### Safety Features
- **Read-only Arc access** - Arc's `StorableSidebar.json` is never modified
- **Automatic backups** - `zen-sessions.jsonlz4.bak` created before changes
- **No data loss** - Zen profile can be restored from backup
- **Arc remains intact** - Migration is one-way, Arc unchanged
- **Zen must be closed** - Prevents file locks on session file

### Generated Files
- `arc_pinned_tabs_export.json` - Extracted Arc data (gitignored)
- `zen-sessions.jsonlz4.bak` - Automatic backup of Zen session
- Temporary `__pycache__/` folders (gitignored)

## Technical Discoveries & Fixes

### 1. Zen Uses Compressed JSON, Not SQL (January 2025)
Early versions assumed Zen used Firefox-style SQL tables (`zen_pins`, `zen_workspaces`). Investigation of test profiles revealed Zen uses `zen-sessions.jsonlz4` - a compressed JSON file.

**Mozilla LZ4 Format:**
- 8-byte magic header: `mozLz40\x00`
- 4-byte uncompressed size (little-endian uint32)
- LZ4-compressed JSON data

### 2. Arc Extraction: Pinned vs Open Tabs (Critical Fix)
**Problem:** Initial extraction pulled currently open tabs instead of pinned sidebar tabs.

**Root Cause:** Incorrect container selection logic. Each space has:
```python
containerIDs = ['pinned', UUID1, 'unpinned', UUID2]
```

**Original (Wrong):** `if idx > pinned_index:` → Got containers AFTER pinned (open tabs!)

**Fixed:** `if pinned_index < idx < unpinned_index:` → Gets containers BETWEEN markers (pinned tabs!)

**Impact:** Now correctly migrates 852 pinned tabs instead of 524 open tabs.

### 3. Orphaned Essential Tabs
Arc's Essential tabs (top toolbar) can lose their space association. Solution: Create separate "Orphaned" workspace with 🔍 icon instead of mixing with existing spaces.

## Development Notes

- **Dependencies:** Python 3.7+ standard library + `lz4` module (`pip3 install lz4`)
- **Logging:** Extensive INFO-level logging for debugging
- **Error handling:** Graceful degradation with detailed error messages
- **Platform:** macOS tested (Linux/Windows support planned)
- **Testing:** Verified with 850+ tabs, 83 folders, 4 workspaces
- **Profile selection:** Edit `zen_sessions_importer_v4.py` line ~218 to target specific profile