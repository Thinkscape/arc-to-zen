#!/usr/bin/env python3
"""Sync Arc workspace themes into Zen workspaces."""

import json
import argparse
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from zen_sessions_importer_v4 import read_mozilla_lz4, resolve_zen_profile, write_mozilla_lz4
from src.profile_paths import arc_json_path


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ZEN_COLOR_TYPE = "explicit-lightness"
DEFAULT_OPACITY = 0.5


def load_arc_sidebar(arc_profile: str | Path | None = None) -> Dict[str, Any]:
    path = arc_json_path("StorableSidebar.json", arc_profile)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def alternating_pairs(values: list[Any]) -> Iterable[tuple[str, Any]]:
    for i in range(0, len(values) - 1, 2):
        if isinstance(values[i], str):
            yield values[i], values[i + 1]


def nested(obj: Dict[str, Any], path: list[str]) -> Optional[Any]:
    current: Any = obj
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, number))


def arc_color_to_rgb(color: Optional[Dict[str, Any]]) -> Optional[list[int]]:
    if not isinstance(color, dict):
        return None

    rgb = []
    for component in ("red", "green", "blue"):
        if component not in color:
            return None
        rgb.append(round(clamp_float(color[component], 0.0, 1.0) * 255))
    return rgb


def gradient_payload(window_theme: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return nested(
        window_theme,
        ["background", "single", "_0", "style", "color", "_0", "blendedGradient", "_0"],
    )


def single_color_payload(window_theme: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return nested(
        window_theme,
        ["background", "single", "_0", "style", "color", "_0", "blendedSingleColor", "_0"],
    )


def arc_theme_colors(window_theme: Dict[str, Any]) -> list[list[int]]:
    gradient = gradient_payload(window_theme)
    if gradient:
        colors = [
            rgb
            for rgb in (arc_color_to_rgb(color) for color in gradient.get("baseColors", []))
            if rgb
        ]
        if colors:
            return colors[:3]

    single_color = single_color_payload(window_theme)
    if single_color:
        rgb = arc_color_to_rgb(single_color.get("color"))
        if rgb:
            return [rgb]

    primary_palette = window_theme.get("primaryColorPalette", {})
    for key in ("midTone", "shaded", "tintedLight"):
        rgb = arc_color_to_rgb(primary_palette.get(key))
        if rgb:
            return [rgb]

    return []


def arc_theme_modifiers(window_theme: Dict[str, Any]) -> Dict[str, Any]:
    gradient = gradient_payload(window_theme)
    if gradient and isinstance(gradient.get("modifiers"), dict):
        return gradient["modifiers"]

    single_color = single_color_payload(window_theme)
    if single_color and isinstance(single_color.get("modifiers"), dict):
        return single_color["modifiers"]

    return {}


def zen_color(rgb: list[int], is_primary: bool) -> Dict[str, Any]:
    return {
        "c": rgb,
        "isCustom": False,
        "algorithm": "",
        "isPrimary": is_primary,
        "lightness": 50,
        "type": ZEN_COLOR_TYPE,
    }


def zen_theme_from_arc(window_theme: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    colors = arc_theme_colors(window_theme)
    if not colors:
        return None

    modifiers = arc_theme_modifiers(window_theme)
    opacity = (
        clamp_float(modifiers.get("intensityFactor"), 0.2, 1.0)
        if "intensityFactor" in modifiers
        else DEFAULT_OPACITY
    )
    texture = (
        clamp_float(modifiers.get("noiseFactor"), 0.0, 1.0)
        if modifiers.get("overlay") == "grain"
        else 0
    )

    return {
        "type": "gradient",
        "gradientColors": [zen_color(rgb, index == 0) for index, rgb in enumerate(colors)],
        "opacity": opacity,
        "texture": texture,
    }


def arc_workspace_themes(arc_profile: str | Path | None = None) -> Dict[str, Dict[str, Any]]:
    sidebar = load_arc_sidebar(arc_profile)
    space_models = sidebar.get("firebaseSyncState", {}).get("syncData", {}).get("spaceModels", [])
    themes: Dict[str, Dict[str, Any]] = {}

    for _, model in alternating_pairs(space_models):
        value = model.get("value", {}) if isinstance(model, dict) else {}
        name = value.get("title")
        window_theme = value.get("customInfo", {}).get("windowTheme")
        if not name or not isinstance(window_theme, dict):
            continue

        theme = zen_theme_from_arc(window_theme)
        if theme:
            themes[name] = theme

    return themes


def update_space_themes(spaces: list[Dict[str, Any]], themes: Dict[str, Dict[str, Any]]) -> int:
    changed = 0
    for space in spaces:
        name = space.get("name")
        theme = themes.get(name)
        if not theme:
            continue

        if space.get("theme") != theme:
            old_colors = len(space.get("theme", {}).get("gradientColors", []))
            space["theme"] = theme
            changed += 1
            logger.info(
                "   %s: %s colors -> %s colors, opacity=%s, texture=%s",
                name,
                old_colors,
                len(theme["gradientColors"]),
                theme["opacity"],
                theme["texture"],
            )

    return changed


def backup(path: Path, timestamp: str) -> None:
    backup_path = path.with_name(f"{path.name}.codex-workspace-theme-backup-{timestamp}")
    shutil.copy2(path, backup_path)
    logger.info(f"✅ Backed up {path.name} to {backup_path.name}")


def spaces_from_session(data: Dict[str, Any]) -> list[Dict[str, Any]]:
    if "windows" in data:
        return data.get("windows", [{}])[0].get("spaces", [])
    return data.get("spaces", [])


def update_file(path: Path, themes: Dict[str, Dict[str, Any]], timestamp: str) -> int:
    if not path.exists():
        logger.info(f"Skipping missing file: {path}")
        return 0

    data = read_mozilla_lz4(path)
    changed = update_space_themes(spaces_from_session(data), themes)
    if changed:
        backup(path, timestamp)
        write_mozilla_lz4(path, data)

    logger.info(f"{path.name}: changed {changed} workspace themes")
    return changed


def main() -> bool:
    parser = argparse.ArgumentParser(description="Sync Arc workspace themes into Zen workspaces.")
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
    themes = arc_workspace_themes(args.arc_profile)
    logger.info(f"Loaded {len(themes)} Arc workspace themes")
    for name, theme in themes.items():
        colors = [color["c"] for color in theme["gradientColors"]]
        logger.info(
            "   %s: colors=%s opacity=%s texture=%s",
            name,
            colors,
            theme["opacity"],
            theme["texture"],
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    files = [
        profile / "zen-sessions.jsonlz4",
        profile / "sessionstore.jsonlz4",
        profile / "sessionstore-backups" / "recovery.jsonlz4",
    ]

    total = 0
    for path in files:
        total += update_file(path, themes, timestamp)

    logger.info(f"Done. Changed {total} workspace theme fields across Zen session files.")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
