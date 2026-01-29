# Arc to Zen Browser Migration Tool

A complete Python-based migration tool that converts Arc browser **pinned sidebar tabs** (with nested folders) into Zen browser workspaces with proper folder hierarchy and tab assignments.
Tested with Zen 1.18.2B

## 🚀 Quick Start

### Prerequisites

- **Python 3.7+**
- **Arc Browser** (with spaces and pinned tabs you want to migrate)
- **Zen Browser** (fresh profile recommended)
- **macOS** (current implementation - Linux/Windows support coming soon)
- **lz4 Python module** (for Zen's compressed session format)
- **The script defaults to importing to the PROFILE profile name** in Zen, you must edit zen_sessions_importer_v4.py to adjust to your profile name.

### Installation

1. Clone this repository:
```bash
git clone https://github.com/What-Do-I-Know/arc-2-zen.git
cd arc2zen
```

2. Install required Python dependency:
```bash
pip3 install lz4
```

### Quick Migration

**⚠️ IMPORTANT**: Close Zen browser before running the migration!

```bash
# Step 1: Extract Arc pinned tabs
python3 src/arc_pinned_tab_extractor.py

# Step 2: Run the migration to your Zen profile
python3 zen_sessions_importer_v4.py
```

That's it! Open Zen browser and select your profile to see all your Arc tabs.

## 📋 What Gets Migrated

### ✅ Fully Supported

- **Arc Spaces** → **Zen Workspaces** (each Arc space becomes a Zen workspace)
- **Pinned Sidebar Tabs** → **Zen Pinned Tabs** (actual pinned tabs from Arc's sidebar)
- **Nested Folders** → **Zen Nested Folders** (proper parent-child folder hierarchy)
  - Example: `Jira > ODocumentation > ProductA` becomes properly nested folders
- **Folder Hierarchy** → **Exact Structure** (3+ levels of nesting supported)
- **Tab URLs & Titles** → **Preserved** (all metadata intact)
- **Essential Tabs** → **Orphaned Workspace** (Arc's top toolbar tabs in separate space)
- **Display Order** → **Zen Sidebar Order** (Arc visual ordering preserved)

### ❌ Not Migrated

- **Currently Open Tabs** (only pinned sidebar tabs are migrated)
- **Arc Boosts, Easels** (Arc-specific features)
- **Folder Colors/Icons** (Zen uses its own styling)
- **Browsing History** (use separate tools if needed)

## 🔧 How It Works

### Architecture Overview

Zen Browser stores pinned tabs in a **compressed JSON file** (`zen-sessions.jsonlz4`), NOT in SQL tables. This tool:

1. **Extracts** Arc's pinned sidebar tabs from `StorableSidebar.json`
2. **Builds** proper nested folder hierarchy from Arc's folder paths
3. **Creates** Zen workspaces, folders, and tabs in the correct format
4. **Compresses** and writes to Zen's session file using Mozilla's LZ4 format

### Step-by-Step Process

#### Step 1: Extract Arc Data

```bash
python3 src/arc_pinned_tab_extractor.py
```

**What it does:**
- Reads `~/Library/Application Support/Arc/StorableSidebar.json`
- Extracts **pinned sidebar tabs** (not currently open tabs!)
- Identifies Arc spaces and their container structure
- Preserves folder hierarchy and tab ordering
- Handles Essential tabs (Arc's top toolbar)
- Creates `arc_pinned_tabs_export.json`

**Output:**
```
📌 Arc Pinned Tab Extractor
========================================
📊 Extraction Summary:
  Total spaces: 3
  Total pinned tabs: 852
  Total folders: 84

📋 Per-space breakdown:
  • Work: 203 tabs, 32 folders
  • Chat Space: 187 tabs, 24 folders
  • Other Links: 462 tabs, 28 folders
```

#### Step 2: Verify Zen Profile

Make sure you have a Zen profile. You can:
- Use an existing profile
- Create a new profile in Zen browser (strongly recommended)

**Find your profiles:**
```bash
ls ~/Library/Application\ Support/zen/Profiles/
```

You should see directories like `xxxxxxxx.PROFILE` or `xxxxxxxx.default`

#### Step 3: Run Migration

**⚠️ CRITICAL**: Close Zen browser before running this step!

```bash
python3 zen_sessions_importer_v4.py
```

**What it does:**
- Reads `arc_pinned_tabs_export.json`
- Creates Zen workspaces for each Arc space
- Builds nested folder structure with proper `parentId` relationships
- Creates tabs with correct `groupId` (folder) assignments
- Compresses and writes to `zen-sessions.jsonlz4`
- Creates backup of original session file

**Output:**
```
✅ Using profile: xxxxxxxx.PROFILE
✅ Arc export: 3 spaces, 888 tabs
📁 Created workspace: Work Stuff
📁 Created workspace: Chat Space
📁 Created workspace: Other Links

📦 Processing: Work Stuff
   200 tabs, 33 folders
   📂 Created folder: Jira (root)
     📂 Created folder: Documentation (parent: 1234...)
       📂 Created folder: ProductA (parent: 5678...)
   ✅ Added 203 tabs

🎉 Migration Complete!
   Workspaces: 4
   Folders: 83
   Tabs: 852
```

#### Step 4: Open Zen Browser

1. Launch Zen Browser
2. Select your profile (if you have multiple)
3. Check the sidebar for your workspaces
4. Expand folders to see nested structure
5. All tabs should be clickable with proper URLs

## 📁 Project Structure

```
arc2zen/
├── README.md                          # This file
├── CLAUDE.md                          # Development notes
├── .gitignore                         # Excludes generated files
│
├── src/
│   └── arc_pinned_tab_extractor.py    # ⭐ Extracts Arc pinned sidebar tabs
│
└── zen_sessions_importer_v4.py        # ⭐ Import exported Arc data into Zen
```

### Which Scripts to Use

**✅ Current Working Scripts:**
1. `src/arc_pinned_tab_extractor.py` - Extract Arc data
2. `zen_sessions_importer_v4.py` - Import to Zen (with nested folders)


## 🛠️ Advanced Usage

### Extract Only (No Migration)

To see what will be migrated without importing:

```bash
python3 src/arc_pinned_tab_extractor.py
cat arc_pinned_tabs_export.json | python3 -m json.tool | less
```

### Migrate to Specific Profile

Edit `zen_sessions_importer_v4.py` line ~218 to specify profile:

```python
# Change this line:
if p.is_dir() and "PROFILE" in p.name:

# To use a specific profile:
if p.is_dir() and "MyOwnProfile" in p.name:  # Your profile directory name
```

### Verify Migration

After migration, verify the data:

```bash
python3 << 'EOF'
import lz4.block, json, struct
from pathlib import Path

profile = Path.home() / "Library/Application Support/zen/Profiles/YOUR_PROFILE/zen-sessions.jsonlz4"
with open(profile, 'rb') as f:
    magic = f.read(8)
    size = struct.unpack('<I', f.read(4))[0]
    data = json.loads(lz4.block.decompress(f.read(), uncompressed_size=size))

print(f"Workspaces: {len(data['spaces'])}")
print(f"Folders: {len(data['folders'])}")
print(f"Tabs: {len(data['tabs'])}")
for space in data['spaces']:
    tabs = sum(1 for t in data['tabs'] if t.get('zenWorkspace') == space['uuid'])
    print(f"  {space['name']}: {tabs} tabs")
EOF
```

### Re-run Migration

If you need to re-run:

```bash
# Restore from backup if needed
cp zen-sessions.jsonlz4.bak zen-sessions.jsonlz4

# Or start fresh - delete all tabs/folders in Zen first
# Then re-run the migration
python3 zen_sessions_importer_v4.py
```

## 🔍 Technical Details

### Arc Data Structure

**Location:** `~/Library/Application Support/Arc/StorableSidebar.json`

**Key Structures:**
- `firebaseSyncState.syncData.spaceModels` - Space metadata (names, icons)
- `sidebar.containers[1].items` - All sidebar items (alternating ID/data pairs)
- Each space has `containerIDs` like `['pinned', UUID, 'unpinned', UUID]`
- **Pinned items** are in containers AFTER `'pinned'` but BEFORE `'unpinned'`
- **Open tabs** are in containers AFTER `'unpinned'` (not migrated)

**Folder Hierarchy:**
- Folders have `childrenIds` arrays
- Tabs have `parentID` pointing to their folder
- Nested structure built by traversing parent-child relationships

### Zen Data Structure

**Location:** `~/Library/Application Support/zen/Profiles/[profile]/zen-sessions.jsonlz4`

**Format:** Mozilla LZ4 compressed JSON
- 8-byte magic header: `mozLz40\x00`
- 4-byte uncompressed size (little-endian uint32)
- LZ4-compressed JSON data

**Key Structures:**
```json
{
  "spaces": [
    {
      "uuid": "{...}",
      "name": "Work",
      "containerTabId": 0,
      ...
    }
  ],
  "folders": [
    {
      "id": "1234-56",
      "name": "Jira",
      "parentId": null,  // null = root folder
      "workspaceId": "{...}",
      ...
    },
    {
      "id": "7890-12",
      "name": "Documentation",
      "parentId": "1234-56",  // Points to parent folder ID
      "workspaceId": "{...}",
      ...
    }
  ],
  "groups": [/* Duplicates folder info */],
  "tabs": [
    {
      "entries": [{"url": "...", "title": "..."}],
      "groupId": "7890-12",  // Which folder this tab is in
      "zenWorkspace": "{...}",  // Which workspace
      "pinned": true,
      ...
    }
  ]
}
```

### Nested Folder Implementation

The key to proper nested folders is the `parentId` field:

```python
# Root folder
folder = {
    "id": "1234-56",
    "name": "Jira",
    "parentId": None,  # Root level
    "workspaceId": workspace_uuid
}

# Subfolder
subfolder = {
    "id": "7890-12",
    "name": "Documentation",
    "parentId": "1234-56",  # Points to Key Jira
    "workspaceId": workspace_uuid
}

# Sub-subfolder
subsubfolder = {
    "id": "3456-78",
    "name": "ProductA",
    "parentId": "7890-12",  # Points to Documentation
    "workspaceId": workspace_uuid
}
```

### Orphaned Essential Tabs

Arc's "Essential tabs" (top toolbar with large icons) are sometimes not associated with any specific space. The extractor now:

1. Detects orphaned Essential tabs (no matching space/profile)
2. Creates a new "Orphaned" workspace with 🔍 icon
3. Adds all orphaned tabs to this workspace
4. Result: Separate workspace in Zen for these tabs

## 🛡️ Safety Features

- **Read-only Arc access** - Your Arc data is never modified
- **Automatic backups** - `zen-sessions.jsonlz4.bak` created before changes
- **No data loss** - Zen profile can be restored from backup
- **Arc remains intact** - Migration is one-way, Arc is unchanged

## 🐛 Troubleshooting

### Common Issues

**"Profile not found"**
```bash
# List available profiles
ls ~/Library/Application\ Support/zen/Profiles/

# Update zen_sessions_importer_v4.py to use your profile name
# Edit line ~218 to match your profile directory
```

**"No such file or directory: arc_pinned_tabs_export.json"**
```bash
# Run the extractor first
python3 src/arc_pinned_tab_extractor.py
```

**"ModuleNotFoundError: No module named 'lz4'"**
```bash
# Install lz4 Python module
pip3 install lz4
```

**"Wrong tabs migrated (open tabs instead of pinned)"**
- This was a bug in earlier versions
- Make sure you're using the latest `arc_pinned_tab_extractor.py`
- Look for the fix that extracts containers BETWEEN 'pinned' and 'unpinned'

**"Folders are flat instead of nested"**
- Use `zen_sessions_importer_v4.py` (not v3 or earlier)
- v4 creates proper `parentId` relationships

**"Cannot open Zen session file"**
- Make sure Zen browser is **completely closed** before migration
- Check Activity Monitor (Mac) to ensure no Zen processes running

### Data Recovery

If something goes wrong:

1. **Restore Zen session:**
   ```bash
   cd ~/Library/Application\ Support/zen/Profiles/YOUR_PROFILE/
   cp zen-sessions.jsonlz4.bak zen-sessions.jsonlz4
   ```

2. **Arc data is safe:**
   - Arc's `StorableSidebar.json` is never modified
   - You can re-run the migration anytime

3. **Re-extract Arc data:**
   ```bash
   python3 src/arc_pinned_tab_extractor.py
   ```

## 📊 Example Migration Output

### Before Migration (Arc)
```
Arc Browser Sidebar:
  📁 Work Space
    📂 Jira
      📂 Documentation
        📂 ProductA
          📄 Cipher list
          📄 Profile FAQ
      📂 crypto
        📄 Usage tracking
    📂 OnBoarding
      📄 Quarterly Review
      📄 Onboarding Plan
```

### After Migration (Zen)
```
Zen Browser Sidebar:
  🏢 Work Workspace
    📂 Jira (root folder)
      📂 Documentation (subfolder, parentId: Jira)
        📂 ProductA (sub-subfolder, parentId: Documentation)
          📄 Cipher list ✅
          📄 Profile FAQ ✅
      📂 crypto (subfolder, parentId: Jira)
        📄 Usage tracking ✅
    📂 OnBoarding (root folder)
      📄 Quarterly Review ✅
      📄 Onboarding Plan ✅
```

## 🎯 Verified Features

### ✅ Working

- **Nested folders** (3+ levels deep)
- **Proper URLs** (all tabs clickable)
- **Folder hierarchy** (parent-child relationships)
- **Multiple workspaces** (all Arc spaces migrated)
- **Tab ordering** (Arc sidebar order preserved)
- **Essential tabs** (in separate Orphaned workspace)
- **Large migrations** (tested with 850+ tabs)

### 🔬 Technical Achievements

1. **Correct Arc data extraction**
   - Fixed: Now extracts pinned sidebar tabs (not open tabs)
   - Uses containers between 'pinned' and 'unpinned' markers

2. **Nested folder structure**
   - Fixed: Proper `parentId` relationships
   - Folders sort by depth (parents before children)

3. **Zen session format**
   - Discovered: Zen uses LZ4-compressed JSON (not SQL tables)
   - Implemented: Mozilla's LZ4 compression with size header

4. **Orphaned tabs handling**
   - Creates separate "Orphaned" workspace (not mixed with other tabs)
   - Preserves all Essential tabs

## 🙏 Acknowledgments

- **Arc Browser team** - For creating an innovative browser with excellent organization
- **Zen Browser team** - For building a privacy-focused, customizable alternative
- **Claude Code** - For AI-assisted development, debugging, and problem-solving
- **Raf Cabezas** for building an earlier version of this tool (https://github.com/rafcabezas/arc2zen) which inspired me to adjust it to support folders & subfolders in Zen.
- **Community** - For testing and feedback

## 📄 License

MIT License - See LICENSE file for details.

**⚠️ Important**: Always backup your data before running migrations. This tool is provided as-is with no warranty. Test thoroughly before using on production data.


