#!/usr/bin/env python3
"""
yt_downloader.py — Unified YouTube Downloader
Supports both CLI and GUI modes.

Usage:
  GUI mode (default):       python yt_downloader.py
  CLI single video:         python yt_downloader.py -u URL
  CLI playlist:             python yt_downloader.py -u URL --playlist
  CLI with format:          python yt_downloader.py -u URL -f bestaudio/best
  CLI with output dir:      python yt_downloader.py -u URL -o ~/Downloads
  Help:                     python yt_downloader.py --help
"""

import sys
import os
import argparse

import yt_dlp


# ---------------------------------------------------------------------------
# Shared download logic
# ---------------------------------------------------------------------------

DEFAULT_FORMAT = "bestvideo+bestaudio/best"
FORMATS = {
    "MP4 (best video+audio)": "bestvideo+bestaudio/best",
    "Best (default)":         "best",
    "Audio only (MP3)":       "bestaudio/best",
    "720p MP4":               "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080p MP4":              "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
}


def build_ydl_opts(
    fmt: str,
    output_dir: str,
    playlist: bool,
    progress_hook=None,
    postprocess_hook=None,
) -> dict:
    """Return a yt_dlp options dict."""
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    # Determine merge format based on selected format
    is_audio_only = "bestaudio" in fmt and "bestvideo" not in fmt
    merge_fmt = None if is_audio_only else "mp4"

    hooks = []
    if progress_hook:
        hooks.append(progress_hook)

    postprocess_hooks = []
    if postprocess_hook:
        postprocess_hooks.append(postprocess_hook)

    opts = {
        "format":              fmt,
        "outtmpl":             outtmpl,
        "merge_output_format": merge_fmt,
        "noplaylist":          not playlist,
        "quiet":               True,
        "no_warnings":         True,
        "nocolor":             True,
        "progress_hooks":      hooks,
        "postprocessor_hooks": postprocess_hooks,
        "concurrent_fragment_downloads": 4,  # faster downloads via parallelism
    }

    if is_audio_only:
        opts["postprocessors"] = [{
            "key":            "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }]

    return opts


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

def run_cli(args: argparse.Namespace) -> int:
    """Run in CLI mode. Returns exit code."""
    url       = args.url
    fmt       = args.format
    playlist  = args.playlist
    output    = os.path.expanduser(args.output)
    os.makedirs(output, exist_ok=True)

    # Track per-file progress in terminal
    last_filename = [None]

    def progress_hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            fname   = d.get("filename", "")
            pct     = d.get("_percent_str", "?%").strip()
            speed   = d.get("_speed_str", "?").strip()
            eta     = d.get("_eta_str", "?").strip()
            if fname != last_filename[0]:
                if last_filename[0] is not None:
                    print()  # newline after previous file
                print(f"\n▶  {os.path.basename(fname)}")
                last_filename[0] = fname
            print(f"\r   {pct:>7}  speed: {speed:>12}  ETA: {eta:>8}", end="", flush=True)
        elif status == "finished":
            print(f"\r   ✓ Done: {os.path.basename(d.get('filename', ''))}")
            last_filename[0] = None

    ydl_opts = build_ydl_opts(fmt, output, playlist, progress_hook=progress_hook)

    print(f"Downloading: {url}")
    print(f"Format: {fmt} | Playlist: {playlist} | Output: {output}\n")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("\nAll downloads complete.")
        return 0
    except yt_dlp.utils.DownloadError as exc:
        print(f"\nDownload error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\nUnexpected error: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# GUI mode
# ---------------------------------------------------------------------------

def run_gui() -> int:
    """Launch the PyQt5 GUI. Returns exit code."""
    try:
        from PyQt5.QtWidgets import (
            QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
            QLineEdit, QCheckBox, QComboBox, QPushButton, QTextEdit,
            QMessageBox, QProgressBar, QFileDialog, QGroupBox,
        )
        from PyQt5.QtCore import QThread, pyqtSignal, Qt
        from PyQt5.QtGui import QFont, QColor, QPalette
    except ImportError:
        print("PyQt5 is not installed. Run:  pip install PyQt5", file=sys.stderr)
        return 1

    # -----------------------------------------------------------------------
    # Worker thread
    # -----------------------------------------------------------------------
    class DownloadThread(QThread):
        progress    = pyqtSignal(float)   # 0–100
        log         = pyqtSignal(str)
        finished_ok = pyqtSignal()
        error       = pyqtSignal(str)

        def __init__(self, url: str, ydl_opts: dict):
            super().__init__()
            self.url      = url
            self.ydl_opts = ydl_opts
            # Inject our hook
            self.ydl_opts["progress_hooks"]      = [self._progress_hook]
            self.ydl_opts["postprocessor_hooks"] = [self._postprocess_hook]

        def run(self):
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    ydl.download([self.url])
                self.finished_ok.emit()
            except yt_dlp.utils.DownloadError as exc:
                self.error.emit(str(exc))
            except Exception as exc:
                self.error.emit(str(exc))

        def _progress_hook(self, d: dict):
            status = d.get("status")
            if status == "downloading":
                pct_str = d.get("_percent_str", "0%").strip().replace("%", "")
                try:
                    pct = float(pct_str)
                except ValueError:
                    pct = 0.0
                self.progress.emit(pct)
                fname = os.path.basename(d.get("filename", ""))
                speed = d.get("_speed_str", "?").strip()
                eta   = d.get("_eta_str", "?").strip()
                self.log.emit(
                    f"[{pct:5.1f}%]  {fname}  —  speed: {speed}  ETA: {eta}"
                )
            elif status == "finished":
                self.progress.emit(100.0)
                self.log.emit(f"✓ Finished: {os.path.basename(d.get('filename', ''))}")

        def _postprocess_hook(self, d: dict):
            if d.get("status") == "finished":
                self.log.emit(f"✔ Post-processed: {os.path.basename(d.get('filepath', ''))}")

    # -----------------------------------------------------------------------
    # Main window
    # -----------------------------------------------------------------------
    class DownloaderWindow(QWidget):
        def __init__(self):
            super().__init__()
            self._thread: DownloadThread | None = None
            self._init_ui()

        def _init_ui(self):
            self.setWindowTitle("YouTube Downloader")
            self.setMinimumWidth(560)
            root = QVBoxLayout(self)
            root.setSpacing(10)
            root.setContentsMargins(16, 16, 16, 16)

            # --- URL row ---
            url_box = QGroupBox("Video / Playlist URL")
            url_layout = QVBoxLayout(url_box)
            self.url_input = QLineEdit()
            self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
            url_layout.addWidget(self.url_input)
            root.addWidget(url_box)

            # --- Options row ---
            opts_box = QGroupBox("Options")
            opts_layout = QVBoxLayout(opts_box)

            # Format
            fmt_row = QHBoxLayout()
            fmt_row.addWidget(QLabel("Format:"))
            self.format_combo = QComboBox()
            for label, value in FORMATS.items():
                self.format_combo.addItem(label, value)
            fmt_row.addWidget(self.format_combo, 1)
            opts_layout.addLayout(fmt_row)

            # Output dir
            dir_row = QHBoxLayout()
            dir_row.addWidget(QLabel("Save to:"))
            self.dir_input = QLineEdit(os.path.expanduser("~"))
            dir_row.addWidget(self.dir_input, 1)
            browse_btn = QPushButton("Browse…")
            browse_btn.clicked.connect(self._browse_dir)
            dir_row.addWidget(browse_btn)
            opts_layout.addLayout(dir_row)

            # Playlist checkbox
            self.playlist_cb = QCheckBox("Download entire playlist")
            opts_layout.addWidget(self.playlist_cb)

            root.addWidget(opts_box)

            # --- Progress ---
            self.progress_bar = QProgressBar()
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(True)
            root.addWidget(self.progress_bar)

            # --- Log ---
            self.log_box = QTextEdit()
            self.log_box.setReadOnly(True)
            self.log_box.setMinimumHeight(160)
            self.log_box.setFont(QFont("Courier New", 9))
            root.addWidget(self.log_box)

            # --- Buttons ---
            btn_row = QHBoxLayout()
            self.download_btn = QPushButton("⬇  Download")
            self.download_btn.setFixedHeight(36)
            self.download_btn.clicked.connect(self._start_download)
            self.cancel_btn = QPushButton("✕  Cancel")
            self.cancel_btn.setFixedHeight(36)
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.clicked.connect(self._cancel_download)
            btn_row.addWidget(self.download_btn)
            btn_row.addWidget(self.cancel_btn)
            root.addLayout(btn_row)

        # --- Slots ---

        def _browse_dir(self):
            d = QFileDialog.getExistingDirectory(self, "Select output folder",
                                                 self.dir_input.text())
            if d:
                self.dir_input.setText(d)

        def _start_download(self):
            url = self.url_input.text().strip()
            if not url:
                QMessageBox.warning(self, "Missing URL", "Please enter a YouTube URL.")
                return

            output   = self.dir_input.text().strip() or os.path.expanduser("~")
            fmt      = self.format_combo.currentData()
            playlist = self.playlist_cb.isChecked()

            os.makedirs(output, exist_ok=True)

            self.progress_bar.setValue(0)
            self.log_box.clear()
            self._set_busy(True)

            ydl_opts = build_ydl_opts(fmt, output, playlist)

            self._thread = DownloadThread(url, ydl_opts)
            self._thread.progress.connect(self._on_progress)
            self._thread.log.connect(self._on_log)
            self._thread.finished_ok.connect(self._on_done)
            self._thread.error.connect(self._on_error)
            self._thread.start()

        def _cancel_download(self):
            if self._thread and self._thread.isRunning():
                self._thread.terminate()
                self._thread.wait()
                self._on_log("⚠ Download cancelled by user.")
            self._set_busy(False)

        def _on_progress(self, pct: float):
            self.progress_bar.setValue(int(pct))

        def _on_log(self, msg: str):
            self.log_box.append(msg)
            self.log_box.verticalScrollBar().setValue(
                self.log_box.verticalScrollBar().maximum()
            )

        def _on_done(self):
            self._on_log("\n✅ All downloads complete!")
            self._set_busy(False)

        def _on_error(self, msg: str):
            self._on_log(f"\n❌ Error: {msg}")
            self._set_busy(False)
            QMessageBox.critical(self, "Download Error", msg)

        def _set_busy(self, busy: bool):
            self.download_btn.setEnabled(not busy)
            self.cancel_btn.setEnabled(busy)
            self.url_input.setEnabled(not busy)
            self.format_combo.setEnabled(not busy)
            self.dir_input.setEnabled(not busy)
            self.playlist_cb.setEnabled(not busy)

    app = QApplication(sys.argv)
    win = DownloaderWindow()
    win.show()
    return app.exec_()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="yt_downloader",
        description="YouTube Downloader — GUI by default, CLI with -u/--url",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-u", "--url",
        metavar="URL",
        help="Video or playlist URL (omit to launch GUI)",
    )
    parser.add_argument(
        "-f", "--format",
        metavar="FORMAT",
        default=DEFAULT_FORMAT,
        help=f"yt-dlp format string (default: {DEFAULT_FORMAT!r})",
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Download entire playlist",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="List built-in format presets and exit",
    )

    args = parser.parse_args()

    if args.list_formats:
        print("Built-in format presets:")
        for label, value in FORMATS.items():
            print(f"  {value!r:50s}  # {label}")
        return 0

    if args.url:
        return run_cli(args)
    else:
        return run_gui()


if __name__ == "__main__":
    sys.exit(main())