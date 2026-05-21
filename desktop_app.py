#!/usr/bin/env python3
"""Simple cross-platform desktop UI for Arc to Zen migration."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import psutil
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QProgressBar,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    print("Missing desktop dependency:", exc)
    print("Install dependencies with: pip install -r requirements.txt")
    raise

from src.profile_paths import discover_arc_profiles, discover_zen_profiles, is_arc_profile, resolve_zen_profile


REPO_ROOT = Path(__file__).resolve().parent
APP_STYLESHEET = """
QWidget#Root {
    background: #f6f7f9;
}

QFrame#CardPanel,
QFrame#DangerPanel {
    border-radius: 12px;
    border: 1px solid #d9dde5;
}

QFrame#CardPanel {
    background: #ffffff;
}

QFrame#DangerPanel {
    background: #fff1f1;
    border-color: #efc2c2;
}

QLabel[role="cardTitle"] {
    color: #111827;
    font-size: 15px;
    font-weight: 650;
}

QLabel {
    color: #374151;
}

QComboBox,
QTextEdit {
    background: #ffffff;
    border: 1px solid #cfd5df;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: #dbeafe;
}

QComboBox:focus,
QTextEdit:focus {
    border-color: #3b82f6;
}

QCheckBox {
    spacing: 8px;
    color: #1f2937;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #cfd5df;
    border-radius: 8px;
    color: #111827;
    padding: 8px 14px;
}

QPushButton:hover {
    background: #f3f4f6;
}

QPushButton:pressed {
    background: #e5e7eb;
}

QPushButton:disabled {
    color: #9ca3af;
    background: #f3f4f6;
}

QPushButton#PrimaryButton {
    background: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background: #1d4ed8;
}

QProgressBar {
    background: #e5e7eb;
    border: 0;
    border-radius: 6px;
    height: 10px;
    text-align: center;
}

QProgressBar::chunk {
    background: #2563eb;
    border-radius: 6px;
}

QTextEdit {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 12px;
}
"""
ZEN_PROCESS_NAMES = {
    "zen",
    "zen.exe",
    "zen-bin",
    "zen-browser",
    "zen-browser-bin",
    "zen-browser.exe",
    "zen browser",
    "zen browser.exe",
}


@dataclass
class MigrationConfig:
    arc_profile: Path
    zen_profile: Path
    nuke: bool
    favicons: bool
    folder_states: bool
    workspace_icons: bool
    workspace_themes: bool


def format_path(path: Path) -> str:
    return str(path.expanduser())


def zen_processes() -> list[psutil.Process]:
    processes = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (process.info.get("name") or "").lower()
            exe_name = Path(process.info.get("exe") or name).name.lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        if name in ZEN_PROCESS_NAMES or exe_name in ZEN_PROCESS_NAMES:
            processes.append(process)

    return processes


def terminate_zen_processes(processes: list[psutil.Process]) -> list[psutil.Process]:
    for process in processes:
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(processes, timeout=15)
    return alive


def kill_zen_processes(processes: list[psutil.Process]) -> list[psutil.Process]:
    for process in processes:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(processes, timeout=5)
    return alive


class MigrationWorker(QThread):
    line = Signal(str)
    step = Signal(int, int, str)
    done = Signal(bool, str)

    def __init__(self, config: MigrationConfig):
        super().__init__()
        self.config = config

    def run(self):
        try:
            self._run()
        except Exception as exc:
            self.done.emit(False, str(exc))

    def _run(self):
        python = sys.executable
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["ARC_PROFILE_PATH"] = format_path(self.config.arc_profile)
        env["ZEN_PROFILE_PATH"] = format_path(self.config.zen_profile)

        with tempfile.TemporaryDirectory(prefix="arc-to-zen-") as temp_dir:
            export_file = Path(temp_dir) / "arc_pinned_tabs_export.json"
            steps = [
                (
                    "Extract Arc sidebar data",
                    [
                        python,
                        str(REPO_ROOT / "src" / "arc_pinned_tab_extractor.py"),
                        "--arc-profile",
                        format_path(self.config.arc_profile),
                        "--output",
                        str(export_file),
                    ],
                ),
                (
                    "Import tabs, folders, workspaces, and session state",
                    [
                        python,
                        str(REPO_ROOT / "zen_sessions_importer_v4.py"),
                        "--zen-profile",
                        format_path(self.config.zen_profile),
                        "--arc-export",
                        str(export_file),
                    ]
                    + (["--nuke"] if self.config.nuke else []),
                ),
            ]

            if self.config.favicons:
                steps.append(
                    (
                        "Copy favicons",
                        [
                            python,
                            str(REPO_ROOT / "migrate_arc_favicons.py"),
                            "--arc-profile",
                            format_path(self.config.arc_profile),
                            "--zen-profile",
                            format_path(self.config.zen_profile),
                            "--export-file",
                            str(export_file),
                        ],
                    )
                )

            if self.config.folder_states:
                steps.append(
                    (
                        "Sync pinned-folder open/closed state",
                        [
                            python,
                            str(REPO_ROOT / "sync_arc_folder_states.py"),
                            "--arc-profile",
                            format_path(self.config.arc_profile),
                            "--zen-profile",
                            format_path(self.config.zen_profile),
                        ],
                    )
                )

            if self.config.workspace_icons:
                steps.append(
                    (
                        "Sync workspace icons",
                        [
                            python,
                            str(REPO_ROOT / "sync_arc_workspace_icons.py"),
                            "--arc-profile",
                            format_path(self.config.arc_profile),
                            "--zen-profile",
                            format_path(self.config.zen_profile),
                        ],
                    )
                )

            if self.config.workspace_themes:
                steps.append(
                    (
                        "Sync workspace themes",
                        [
                            python,
                            str(REPO_ROOT / "sync_arc_workspace_themes.py"),
                            "--arc-profile",
                            format_path(self.config.arc_profile),
                            "--zen-profile",
                            format_path(self.config.zen_profile),
                        ],
                    )
                )

            for index, (title, command) in enumerate(steps, start=1):
                self.step.emit(index, len(steps), title)
                self.line.emit(f"\n[{index}/{len(steps)}] {title}")
                result = subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert result.stdout is not None
                for line in result.stdout:
                    self.line.emit(line.rstrip())
                return_code = result.wait()
                if return_code != 0:
                    raise RuntimeError(f"{title} failed with exit code {return_code}")

        self.done.emit(True, "Migration finished successfully.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: MigrationWorker | None = None
        self.setWindowTitle("Arc to Zen Migration")
        self.resize(900, 720)

        self.arc_combo = self._profile_combo(discover_arc_profiles())
        self.zen_combo = self._profile_combo(discover_zen_profiles())

        self.core_check = QCheckBox("Workspaces, pinned tabs, temporary tabs, folders, and Essentials")
        self.core_check.setChecked(True)
        self.core_check.setEnabled(False)

        self.favicons_check = QCheckBox("Favicons")
        self.favicons_check.setChecked(True)
        self.folder_states_check = QCheckBox("Pinned-folder open/closed state")
        self.folder_states_check.setChecked(True)
        self.workspace_icons_check = QCheckBox("Workspace icons")
        self.workspace_icons_check.setChecked(True)
        self.workspace_themes_check = QCheckBox("Workspace colors/themes")
        self.workspace_themes_check.setChecked(True)
        self.nuke_check = QCheckBox("Clear out Zen profile before migration (backups will be saved next to changed files)")
        self.nuke_check.setToolTip("Deletes existing Zen tabs, folders, pins, groups, closed-tab state, and regular bookmarks before importing.")

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.run_button = QPushButton("Start Migration")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.clicked.connect(self.start_migration)

        self._build_ui()

    def _profile_combo(self, profiles: list[Path]) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        for profile in profiles:
            combo.addItem(format_path(profile))
        return combo

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        profile_card, profile_body = self._card("Profiles")
        profile_layout = QFormLayout()
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setHorizontalSpacing(18)
        profile_layout.setVerticalSpacing(12)
        profile_layout.addRow("Source: Arc data folder", self._path_row(self.arc_combo, self.browse_arc))
        profile_layout.addRow("Target: Zen profile", self._path_row(self.zen_combo, self.browse_zen))
        profile_body.addLayout(profile_layout)
        layout.addWidget(profile_card)

        options_card, options_layout = self._card("Choose what to migrate")
        for checkbox in (
            self.core_check,
            self.favicons_check,
            self.folder_states_check,
            self.workspace_icons_check,
            self.workspace_themes_check,
        ):
            options_layout.addWidget(checkbox)
        layout.addWidget(options_card)

        danger_card, danger_layout = self._card("Danger Zone", danger=True)
        danger_layout.addWidget(self.nuke_check)
        layout.addWidget(danger_card)

        layout.addWidget(self.progress)
        layout.addWidget(self.log, stretch=1)
        layout.addWidget(self.run_button, alignment=Qt.AlignRight)

        self.setCentralWidget(root)

    def _card(self, title: str, danger: bool = False) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("DangerPanel" if danger else "CardPanel")
        frame.setFrameShape(QFrame.NoFrame)

        outer_layout = QVBoxLayout(frame)
        outer_layout.setContentsMargins(18, 16, 18, 16)
        outer_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setProperty("role", "cardTitle")
        outer_layout.addWidget(title_label)

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        outer_layout.addLayout(body_layout)

        return frame, body_layout

    def _path_row(self, combo: QComboBox, browse_callback) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(browse_callback)
        layout.addWidget(combo, stretch=1)
        layout.addWidget(browse_button)
        return row

    def browse_arc(self):
        selected = QFileDialog.getExistingDirectory(self, "Select Arc data folder")
        if selected:
            self.arc_combo.setEditText(selected)

    def browse_zen(self):
        selected = QFileDialog.getExistingDirectory(self, "Select Zen profile or Zen root")
        if selected:
            try:
                self.zen_combo.setEditText(format_path(resolve_zen_profile(selected)))
            except Exception:
                self.zen_combo.setEditText(selected)

    def selected_config(self) -> MigrationConfig:
        arc_profile = Path(self.arc_combo.currentText()).expanduser()
        if not is_arc_profile(arc_profile):
            raise ValueError(f"Arc profile must contain a valid StorableSidebar.json:\n{arc_profile}")

        zen_profile = resolve_zen_profile(self.zen_combo.currentText())
        return MigrationConfig(
            arc_profile=arc_profile,
            zen_profile=zen_profile,
            nuke=self.nuke_check.isChecked(),
            favicons=self.favicons_check.isChecked(),
            folder_states=self.folder_states_check.isChecked(),
            workspace_icons=self.workspace_icons_check.isChecked(),
            workspace_themes=self.workspace_themes_check.isChecked(),
        )

    def start_migration(self):
        try:
            config = self.selected_config()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid profile selection", str(exc))
            return

        if not self.confirm_operation(config):
            return

        if not self.ensure_zen_closed():
            return

        self.log.clear()
        self.log.append("Zen is closed. Starting migration.")
        self.progress.setValue(0)
        self.run_button.setEnabled(False)

        self.worker = MigrationWorker(config)
        self.worker.line.connect(self.append_log)
        self.worker.step.connect(self.update_step)
        self.worker.done.connect(self.finish_migration)
        self.worker.start()

    def confirm_operation(self, config: MigrationConfig) -> bool:
        options = [
            "Core tabs/folders/workspaces",
            "Favicons" if config.favicons else None,
            "Folder open/closed state" if config.folder_states else None,
            "Workspace icons" if config.workspace_icons else None,
            "Workspace colors/themes" if config.workspace_themes else None,
        ]
        details = "\n".join(
            [
                "Pending operation:",
                "",
                f"Arc profile: {config.arc_profile}",
                f"Zen profile: {config.zen_profile}",
                f"Nuke Zen first: {'YES' if config.nuke else 'no'}",
                "",
                "Selected migration steps:",
                *[f"- {option}" for option in options if option],
            ]
        )

        icon = QMessageBox.Warning if config.nuke else QMessageBox.Question
        response = QMessageBox(icon, "Confirm migration", details, QMessageBox.Cancel | QMessageBox.Ok, self)
        response.setDefaultButton(QMessageBox.Cancel if config.nuke else QMessageBox.Ok)
        return response.exec() == QMessageBox.Ok

    def ensure_zen_closed(self) -> bool:
        processes = zen_processes()
        if not processes:
            return True

        names = ", ".join(f"{process.info.get('name')} ({process.pid})" for process in processes)
        response = QMessageBox.question(
            self,
            "Close Zen Browser",
            f"Zen appears to be running:\n{names}\n\nClose Zen now before migration?",
            QMessageBox.Cancel | QMessageBox.Ok,
            QMessageBox.Cancel,
        )
        if response != QMessageBox.Ok:
            return False

        alive = terminate_zen_processes(processes)
        if alive:
            force = QMessageBox.warning(
                self,
                "Zen did not close",
                "Zen did not exit after a graceful close request. Force quit it now?",
                QMessageBox.Cancel | QMessageBox.Ok,
                QMessageBox.Cancel,
            )
            if force != QMessageBox.Ok:
                return False
            alive = kill_zen_processes(alive)

        if alive:
            QMessageBox.critical(self, "Zen is still running", "Zen is still running. Migration was not started.")
            return False

        return True

    def append_log(self, line: str):
        self.log.append(line)

    def update_step(self, current: int, total: int, title: str):
        self.progress.setMaximum(total)
        self.progress.setValue(current - 1)
        self.statusBar().showMessage(title)

    def finish_migration(self, ok: bool, message: str):
        self.progress.setValue(self.progress.maximum())
        self.run_button.setEnabled(True)
        self.statusBar().showMessage(message)
        if ok:
            self.log.append("\nMigration finished successfully.")
            QMessageBox.information(self, "Migration complete", message)
        else:
            self.log.append(f"\nMigration failed: {message}")
            QMessageBox.critical(self, "Migration failed", message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
