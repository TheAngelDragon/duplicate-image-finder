from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QProgressBar, QFileDialog, QSplitter,
    QListWidget, QListWidgetItem, QMessageBox, QSlider,
    QGroupBox, QFormLayout
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QPixmap, QImage, QDesktopServices
from pathlib import Path
import io
from PIL import Image
from functions import (
    get_image_files, scan_exact, scan_similar,
    delete_file
)


class ScanWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, directory, mode, threshold=8):
        super().__init__()
        self.directory = directory
        self.mode = mode
        self.threshold = threshold
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def run(self):
        try:
            files = get_image_files(self.directory)
            if not files or self.is_cancelled():
                self.finished.emit([])
                return

            def cb(current, total):
                if not self.is_cancelled():
                    self.progress.emit(current, total)

            if self.mode == "quick":
                groups = scan_exact(files, cb, self.is_cancelled)
            else:
                groups = scan_similar(files, self.threshold, cb, self.is_cancelled)

            self.finished.emit(groups if not self.is_cancelled() else [])
        except Exception as e:
            if not self.is_cancelled():
                self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Duplicate Image Finder")
        self.resize(1200, 800)
        self.groups = []
        self.current_group = None
        self.current_index = 0
        self.worker = None

        self._apply_theme()
        self._build_ui()

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #FFFFFF;
                color: #0C2340;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QPushButton {
                background-color: #4169E1;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #5A82F0;
            }
            QPushButton:pressed {
                background-color: #2E4DB8;
            }
            QPushButton#deleteBtn {
                background-color: #C0392B;
            }
            QPushButton#deleteBtn:hover {
                background-color: #E74C3C;
            }
            QPushButton#cancelBtn {
                background-color: #E67E22;
            }
            QPushButton#cancelBtn:hover {
                background-color: #F39C12;
            }
            QComboBox, QSlider {
                border: 1px solid #4169E1;
                border-radius: 4px;
            }
            QProgressBar {
                border: 1px solid #4169E1;
                border-radius: 6px;
                text-align: center;
                height: 22px;
            }
            QProgressBar::chunk {
                background-color: #C9A227;
                border-radius: 5px;
            }
            QListWidget {
                border: 1px solid #D0D0D0;
                border-radius: 6px;
                background: #FAFAFA;
            }
            QListWidget::item:selected {
                background-color: #4169E1;
                color: white;
            }
            QGroupBox {
                border: 1px solid #C9A227;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #0C2340;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Top controls
        top = QHBoxLayout()
        self.btn_folder = QPushButton("Select Folder")
        self.btn_folder.clicked.connect(self.select_folder)
        self.lbl_folder = QLabel("No folder selected")
        self.lbl_folder.setStyleSheet("color: #555;")

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Quick Scan (Exact Matches)", "Deep Scan (Similar Images)"])
        self.combo_mode.currentIndexChanged.connect(self._toggle_threshold)

        # Threshold slider
        self.slider_threshold = QSlider(Qt.Horizontal)
        self.slider_threshold.setRange(0, 20)
        self.slider_threshold.setValue(8)
        self.slider_threshold.setTickPosition(QSlider.TicksBelow)
        self.slider_threshold.setTickInterval(2)
        self.slider_threshold.valueChanged.connect(self._update_threshold_label)
        self.lbl_threshold = QLabel("Threshold: 8")
        self.slider_threshold.setVisible(False)
        self.lbl_threshold.setVisible(False)

        self.btn_scan = QPushButton("Start Scan")
        self.btn_scan.clicked.connect(self.start_or_cancel_scan)
        self.btn_scan.setEnabled(False)

        top.addWidget(self.btn_folder)
        top.addWidget(self.lbl_folder, 1)
        top.addWidget(self.combo_mode)
        top.addWidget(self.lbl_threshold)
        top.addWidget(self.slider_threshold)
        top.addWidget(self.btn_scan)
        main_layout.addLayout(top)

        # Progress
        prog_layout = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.lbl_progress = QLabel("0 / 0")
        prog_layout.addWidget(self.progress, 1)
        prog_layout.addWidget(self.lbl_progress)
        main_layout.addLayout(prog_layout)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("<b>Duplicate Groups</b>"))
        self.list_groups = QListWidget()
        self.list_groups.itemClicked.connect(self.on_group_selected)
        left_layout.addWidget(self.list_groups)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.lbl_preview = QLabel("Select a group to preview")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setMinimumHeight(360)
        self.lbl_preview.setStyleSheet("border: 2px solid #C9A227; border-radius: 8px; background: #F8F8F8;")
        right_layout.addWidget(self.lbl_preview)

        info_group = QGroupBox("Selected File")
        info_layout = QFormLayout()
        self.lbl_name = QLabel("-")
        self.lbl_size = QLabel("-")
        self.lbl_modified = QLabel("-")
        self.lbl_sim = QLabel("-")
        self.lbl_path = QLabel("-")
        self.lbl_path.setWordWrap(True)
        info_layout.addRow("Name:", self.lbl_name)
        info_layout.addRow("Size:", self.lbl_size)
        info_layout.addRow("Modified:", self.lbl_modified)
        info_layout.addRow("Match:", self.lbl_sim)
        info_layout.addRow("Path:", self.lbl_path)
        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)

        right_layout.addWidget(QLabel("<b>Files in Group</b> (click to preview)"))
        self.list_files = QListWidget()
        self.list_files.itemClicked.connect(self.on_file_selected)
        right_layout.addWidget(self.list_files)

        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("Open Location")
        self.btn_open.clicked.connect(self.open_location)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("deleteBtn")
        self.btn_delete.clicked.connect(self.delete_current)
        self.btn_open.setVisible(False)
        self.btn_delete.setVisible(False)
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_delete)
        right_layout.addLayout(btn_layout)

        splitter.addWidget(right_widget)
        splitter.setSizes([350, 850])
        main_layout.addWidget(splitter, 1)

        self.folder_path = None

    def _update_threshold_label(self, value):
        self.lbl_threshold.setText(f"Threshold: {value}")

    def _toggle_threshold(self):
        is_deep = self.combo_mode.currentIndex() == 1
        self.slider_threshold.setVisible(is_deep)
        self.lbl_threshold.setVisible(is_deep)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder:
            self.folder_path = folder
            self.lbl_folder.setText(folder)
            self.btn_scan.setEnabled(True)

    def start_or_cancel_scan(self):
        if self.worker and self.worker.isRunning():
            self.cancel_scan()
        else:
            self.start_scan()

    def start_scan(self):
        if not self.folder_path:
            return

        self.btn_scan.setText("Cancel")
        self.btn_scan.setObjectName("cancelBtn")
        self.btn_scan.setStyleSheet("")  # force style refresh
        self.list_groups.clear()
        self.list_files.clear()
        self.lbl_preview.setText("Scanning...")
        self.groups = []
        self._hide_action_buttons()

        mode = "quick" if self.combo_mode.currentIndex() == 0 else "deep"
        threshold = self.slider_threshold.value()

        self.worker = ScanWorker(self.folder_path, mode, threshold)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.scan_finished)
        self.worker.error.connect(self.scan_error)
        self.worker.start()

    def cancel_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_preview.setText("Cancelling...")
            self.btn_scan.setEnabled(False)

    def update_progress(self, current, total):
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self.lbl_progress.setText(f"{current} / {total}")

    def scan_finished(self, groups):
        self.groups = groups
        self._reset_scan_button()
        self.progress.setValue(self.progress.maximum())
        self.populate_groups()
        if not groups:
            self.lbl_preview.setText("Scan cancelled" if self.worker and self.worker.is_cancelled() else "No duplicates found")
            if not (self.worker and self.worker.is_cancelled()):
                QMessageBox.information(self, "Done", "No duplicate images found.")
        else:
            if not (self.worker and self.worker.is_cancelled()):
                QMessageBox.information(self, "Scan finished!", f"Found {len(groups)} groups of duplicate images.")

    def scan_error(self, msg):
        self._reset_scan_button()
        QMessageBox.critical(self, "Error", msg)

    def _reset_scan_button(self):
        self.btn_scan.setText("Start Scan")
        self.btn_scan.setObjectName("")
        self.btn_scan.setEnabled(True)
        self.btn_scan.setStyleSheet("")

    def populate_groups(self):
        self.list_groups.clear()
        for i, group in enumerate(self.groups):
            avg_sim = sum(f["similarity"] for f in group) / len(group)
            item = QListWidgetItem(f"Group {i+1}  •  {len(group)} files  •  ~{avg_sim:.1f}%")
            item.setData(Qt.UserRole, i)
            self.list_groups.addItem(item)

    def on_group_selected(self, item):
        idx = item.data(Qt.UserRole)
        self.current_group = self.groups[idx]
        self.current_index = 0
        self.populate_file_list()
        self.show_preview(0)

    def populate_file_list(self):
        self.list_files.clear()
        if not self.current_group:
            return
        for f in self.current_group:
            text = f"{f['path'].name}  •  {f['size_str']}  •  {f['modified']}  •  {f['similarity']:.1f}%"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, f)
            self.list_files.addItem(item)

    def on_file_selected(self, item):
        data = item.data(Qt.UserRole)
        for i, f in enumerate(self.current_group):
            if f["path"] == data["path"]:
                self.show_preview(i)
                break

    def show_preview(self, index: int):
        if not self.current_group or index >= len(self.current_group):
            self._hide_action_buttons()
            return

        self.current_index = index
        info = self.current_group[index]

        self.lbl_name.setText(info["path"].name)
        self.lbl_size.setText(info["size_str"])
        self.lbl_modified.setText(info.get("modified", "Unknown"))
        self.lbl_sim.setText(f"{info['similarity']:.1f}%")
        self.lbl_path.setText(str(info["path"]))

        self.list_files.setCurrentRow(index)
        self._show_action_buttons()

        try:
            with Image.open(info["path"]) as img:
                img = img.convert("RGB")
                img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                qimg = QImage.fromData(buf.getvalue())
                pixmap = QPixmap.fromImage(qimg)
                self.lbl_preview.setPixmap(pixmap.scaled(
                    self.lbl_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
        except Exception as e:
            self.lbl_preview.setText(f"Preview error:\n{e}")

    def _show_action_buttons(self):
        self.btn_open.setVisible(True)
        self.btn_delete.setVisible(True)

    def _hide_action_buttons(self):
        self.btn_open.setVisible(False)
        self.btn_delete.setVisible(False)

    def open_location(self):
        if not self.current_group:
            return
        path = self.current_group[self.current_index]["path"]
        self._open_file_location(path)

    def _open_file_location(path: Path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))  

    def delete_current(self):
        if not self.current_group:
            return
        info = self.current_group[self.current_index]
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete:\n{info['path'].name}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        success, message = delete_file(info["path"])
        if not success:
            QMessageBox.warning(self, "Error", f"Could not delete file:\n{message}")
            return

        self.current_group.pop(self.current_index)

        if len(self.current_group) < 2:
            group_idx = self.list_groups.currentRow()
            if group_idx >= 0:
                self.groups.pop(group_idx)
            self.current_group = None
            self.list_files.clear()
            self.lbl_preview.setText("Group removed")
            self._hide_action_buttons()
            self.populate_groups()
            return

        self.populate_file_list()
        new_index = min(self.current_index, len(self.current_group) - 1)
        self.show_preview(new_index)
        self.populate_groups()