from __future__ import annotations

"""Minimal yt‑dlp GUI — now with a plain 720 p / 30 fps preset.

YouTube periodically breaks older yt-dlp builds (e.g. yt-dlp issue #12482:
the web client only returns SABR streams, leaving just format 18 / 360p).
Use "Update yt-dlp", optionally pass browser cookies, and install a JS
runtime such as deno so yt-dlp can use its full set of YouTube clients.

Run:
    pip install yt-dlp PyQt5
    python ytdlp_gui.py

Pack (optional):
    pip install pyinstaller
    pyinstaller --onefile --windowed ytdlp_gui.py
"""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

###############################################################################
# ------------------------------ GUI LAYER ---------------------------------- #
###############################################################################


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("yt‑dlp Simple GUI")
        self.resize(600, 420)

        layout = QVBoxLayout(self)

        # URL -------------------------------------------------------------
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("YouTube URL:"))
        self.url_in = QLineEdit()
        url_row.addWidget(self.url_in)
        layout.addLayout(url_row)

        # Format ----------------------------------------------------------
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(
            [
                "Best Video/Audio",
                "Best Audio (mp3)",
                "Best Audio (m4a)",
                "720p 30 fps",
            ]
        )
        fmt_row.addWidget(self.fmt_combo)
        layout.addLayout(fmt_row)

        # Cookies ---------------------------------------------------------
        ck_row = QHBoxLayout()
        ck_row.addWidget(QLabel("Cookies from browser:"))
        self.ck_combo = QComboBox()
        self.ck_combo.addItems(
            ["None", "chrome", "firefox", "edge", "brave", "opera", "vivaldi", "safari", "chromium"]
        )
        ck_row.addWidget(self.ck_combo)
        layout.addLayout(ck_row)

        # Extra args ------------------------------------------------------
        extra_row = QHBoxLayout()
        extra_row.addWidget(QLabel("Extra yt-dlp args:"))
        self.extra_in = QLineEdit()
        self.extra_in.setPlaceholderText('e.g. --extractor-args "youtube:player_client=tv"')
        extra_row.addWidget(self.extra_in)
        layout.addLayout(extra_row)

        # Output folder ---------------------------------------------------
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Folder:"))
        self.out_in = QLineEdit()
        out_row.addWidget(self.out_in)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        out_row.addWidget(browse_btn)
        layout.addLayout(out_row)

        # Buttons ---------------------------------------------------------
        btn_row = QHBoxLayout()
        self.dl_btn = QPushButton("Download")
        self.dl_btn.clicked.connect(self._start)
        btn_row.addWidget(self.dl_btn)
        self.up_btn = QPushButton("Update yt-dlp")
        self.up_btn.clicked.connect(self._update)
        btn_row.addWidget(self.up_btn)
        layout.addLayout(btn_row)

        # Log -------------------------------------------------------------
        self.log = QTextEdit(readOnly=True)
        layout.addWidget(self.log)

        self.worker: Optional[_Worker] = None

    # ---------------------------------------------------------------------
    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.out_in.setText(folder)

    def _start(self) -> None:
        url = self.url_in.text().strip()
        if not url:
            self.log.append("Please enter a URL.")
            return

        out_dir = Path(self.out_in.text().strip() or os.getcwd())
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            extra = shlex.split(self.extra_in.text().strip())
        except ValueError as exc:
            self.log.append(f"Invalid extra args: {exc}")
            return

        cookies = self.ck_combo.currentText()
        self._run_worker(
            YtWorker(url, self.fmt_combo.currentText(), out_dir,
                     None if cookies == "None" else cookies, extra)
        )

    def _update(self) -> None:
        self._run_worker(UpdateWorker())

    def _run_worker(self, worker: _Worker) -> None:
        self.dl_btn.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.log.clear()

        self.worker = worker
        self.worker.sig_log.connect(self.log.append)
        self.worker.finished.connect(self._done)
        self.worker.start()

    def _done(self, _code: int) -> None:
        self.dl_btn.setEnabled(True)
        self.up_btn.setEnabled(True)


###############################################################################
# -------------------------- BACKGROUND WORKER ------------------------------ #
###############################################################################


# Signs that YouTube only handed out format 18 (yt-dlp issue #12482 & co.)
_LIMITED_FORMAT_HINTS = (
    "SABR",
    "PO Token",
    "formats have been skipped",
    "JavaScript runtime",
    "Requested format is not available",
)


def _stream(cmd: list[str], on_line) -> subprocess.CompletedProcess:  # run + live log
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        msg = f"Could not find '{cmd[0]}'. Is it installed and on PATH?"
        on_line(msg)
        return subprocess.CompletedProcess(cmd, 127, msg, "")
    out_lines: list[str] = []
    for line in proc.stdout:
        out_lines.append(line)
        on_line(line)
    proc.wait()
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(out_lines), "")


class _Worker(QThread):
    sig_log = pyqtSignal(str)
    finished = pyqtSignal(int)

    def _emit(self, txt: str) -> None:
        self.sig_log.emit(txt.rstrip())


class UpdateWorker(_Worker):
    def run(self) -> None:
        exe = shutil.which("yt-dlp")
        self._emit(f"yt-dlp found at: {exe or 'not on PATH'}")
        proc = _stream(["yt-dlp", "-U"], self._emit) if exe else None
        if proc is None or proc.returncode != 0 or "pip" in proc.stdout:
            # pip installs can't self-update; fall back to pip
            self._emit("Updating via pip…")
            proc = _stream(
                [sys.executable, "-m", "pip", "install", "-U", "yt-dlp[default]"],
                self._emit,
            )
        if not shutil.which("deno"):
            self._emit(
                "\nTip: install deno (https://deno.com) so yt-dlp can solve YouTube's "
                "JS challenges and get all formats instead of just 360p."
            )
        self.finished.emit(proc.returncode)


class YtWorker(_Worker):
    def __init__(self, url: str, preset: str, out_dir: Path,
                 cookies_browser: Optional[str] = None, extra: Optional[list[str]] = None):
        super().__init__()
        self.url = url
        self.preset = preset
        self.out_dir = out_dir
        self.cookies_browser = cookies_browser
        self.extra = extra or []

    def run(self) -> None:
        cmd: list[str] = ["yt-dlp", "--newline"]

        # ----------------------------- preset logic
        if self.preset.startswith("Best Video"):
            cmd += ["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"]
        elif self.preset.startswith("Best Audio (mp3)"):
            cmd += ["-x", "--audio-format", "mp3"]
        elif self.preset.startswith("Best Audio (m4a)"):
            cmd += ["-x", "--audio-format", "m4a"]
        elif self.preset.startswith("720p"):
            cmd += [
                "-f",
                "bestvideo[height<=720][fps<=30]+bestaudio/best[height<=720][fps<=30]",
                "--merge-output-format",
                "mp4",
            ]
        else:
            cmd += ["-f", "best"]

        if self.cookies_browser:
            cmd += ["--cookies-from-browser", self.cookies_browser]

        cmd += self.extra
        cmd += ["-o", str(self.out_dir / "%(title)s.%(ext)s"), "--", self.url]

        self._emit("Running: " + " ".join(shlex.quote(x) for x in cmd))
        proc = _stream(cmd, self._emit)

        if any(h in proc.stdout for h in _LIMITED_FORMAT_HINTS):
            self._emit(
                "\nYouTube limited the available formats (see yt-dlp issue #12482).\n"
                "Try: 1) click \"Update yt-dlp\"; 2) install deno; 3) pick a browser under "
                "\"Cookies from browser\"; 4) add extra args such as\n"
                '   --extractor-args "youtube:player_client=tv"'
            )
        self.finished.emit(proc.returncode)


###############################################################################
# ------------------------------------------------------------------- __main__
###############################################################################


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
