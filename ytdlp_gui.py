from __future__ import annotations

"""Minimal yt‑dlp GUI — now with a plain 720 p / 30 fps preset.

Run:
    pip install yt-dlp PyQt5
    python ytdlp_gui.py

Pack (optional):
    pip install pyinstaller
    pyinstaller --onefile --windowed ytdlp_gui.py
"""

import os
import shlex
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

        # Output folder ---------------------------------------------------
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Folder:"))
        self.out_in = QLineEdit()
        out_row.addWidget(self.out_in)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        out_row.addWidget(browse_btn)
        layout.addLayout(out_row)

        # Download button -------------------------------------------------
        self.dl_btn = QPushButton("Download")
        self.dl_btn.clicked.connect(self._start)
        layout.addWidget(self.dl_btn)

        # Log -------------------------------------------------------------
        self.log = QTextEdit(readOnly=True)
        layout.addWidget(self.log)

        self.worker: Optional[YtWorker] = None

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

        self.dl_btn.setEnabled(False)
        self.log.clear()

        self.worker = YtWorker(url, self.fmt_combo.currentText(), out_dir)
        self.worker.sig_log.connect(self.log.append)
        self.worker.finished.connect(lambda _: self.dl_btn.setEnabled(True))
        self.worker.start()


###############################################################################
# -------------------------- BACKGROUND WORKER ------------------------------ #
###############################################################################


def _stream(cmd: list[str]) -> subprocess.CompletedProcess:  # run + live log
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out_lines: list[str] = []
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            out_lines.append(line)
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(out_lines), "")


class YtWorker(QThread):
    sig_log = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, url: str, preset: str, out_dir: Path):
        super().__init__()
        self.url = url
        self.preset = preset
        self.out_dir = out_dir

    def _emit(self, txt: str) -> None:
        self.sig_log.emit(txt.rstrip())

    def run(self) -> None:
        cmd: list[str] = ["yt-dlp"]

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

        cmd += ["-o", str(self.out_dir / "%(title)s.%(ext)s"), self.url]

        self._emit("Running: " + " ".join(shlex.quote(x) for x in cmd))
        proc = _stream(cmd)
        self._emit(proc.stdout or "")
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
