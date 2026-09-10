from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from posture_assessment.import_export import ExportOptions, ExportResult, UserExportService
from posture_assessment.services import UserService
from posture_assessment.ui.dialogs import show_error, show_info
from posture_assessment.ui.theme import set_primary
from posture_assessment.ui.workers import TaskWorker


class ExportDialog(QDialog):
    MODULES = ["体态检测", "步态检测", "骨盆检测", "脊柱评估", "关节活动度", "足底检测"]
    MODULE_LABELS = {
        "体态检测": "Posture Assessment",
        "步态检测": "Gait Assessment",
        "骨盆检测": "Pelvis Assessment",
        "脊柱评估": "Spine Assessment",
        "关节活动度": "Joint Range of Motion",
        "足底检测": "Foot Pressure Assessment",
    }

    def __init__(
        self,
        user_service: UserService,
        export_service: UserExportService,
        default_destination: Path,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.user_service = user_service
        self.export_service = export_service
        self._worker: TaskWorker | None = None
        self.setWindowTitle("Export User Assessment Data")
        self.resize(1220, 760)
        self._build_ui(default_destination)

    def _build_ui(self, destination: Path) -> None:
        root = QVBoxLayout(self)
        title = QLabel("Export User Assessment Data")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        subtitle = QLabel("Create a traceable ZIP package by user, assessment session, and data type.")
        subtitle.setObjectName("muted")
        root.addWidget(subtitle)
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)

        users_box = QGroupBox("1. Select Users and Sessions")
        users_layout = QVBoxLayout(users_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.user_checks: list[QCheckBox] = []
        container_layout = QVBoxLayout(container)
        page = self.user_service.search(page_size=5000)
        for user in page.items:
            check = QCheckBox(f"{user.name}（{user.patient_no}）")
            check.setProperty("userId", user.id)
            check.setChecked(len(self.user_checks) == 0)
            container_layout.addWidget(check)
            self.user_checks.append(check)
        container_layout.addStretch()
        scroll.setWidget(container)
        users_layout.addWidget(scroll)
        grid.addWidget(users_box, 0, 0)

        modules_box = QGroupBox("2. Select Assessment Modules")
        modules_layout = QGridLayout(modules_box)
        self.module_checks: list[QCheckBox] = []
        for index, module in enumerate(self.MODULES):
            check = QCheckBox(self.MODULE_LABELS[module])
            check.setProperty("module", module)
            check.setChecked(True)
            modules_layout.addWidget(check, index // 2, index % 2)
            self.module_checks.append(check)
        grid.addWidget(modules_box, 0, 1)

        content_box = QGroupBox("3. Select Data Content")
        content_layout = QHBoxLayout(content_box)
        self.xlsx = QCheckBox("Complete XLSX metrics")
        self.xlsx.setChecked(True)
        self.csv = QCheckBox("CSV module data")
        self.json = QCheckBox("Raw JSON structure")
        self.json.setChecked(True)
        self.landmarks = QCheckBox("Body skeleton and key points")
        self.landmarks.setChecked(True)
        self.quality = QCheckBox("Quality flags and confidence")
        self.quality.setChecked(True)
        for check in (self.xlsx, self.csv, self.json, self.landmarks, self.quality):
            content_layout.addWidget(check)
        grid.addWidget(content_box, 1, 0, 1, 2)

        security_box = QGroupBox("4. Security and Packaging")
        security_layout = QVBoxLayout(security_box)
        self.anonymize = QCheckBox("Anonymize (remove name, mobile, and address; create an anonymous ID)")
        self.zip_package = QCheckBox("Create a ZIP with manifest.json and SHA-256 checksums")
        self.zip_package.setChecked(True)
        security_layout.addWidget(self.anonymize)
        security_layout.addWidget(self.zip_package)
        destination_row = QHBoxLayout()
        destination_row.addWidget(QLabel("Export directory"))
        self.destination = QLineEdit(str(destination))
        destination_row.addWidget(self.destination, 1)
        choose = QPushButton("Browse")
        choose.clicked.connect(self._choose_destination)
        destination_row.addWidget(choose)
        security_layout.addLayout(destination_row)
        grid.addWidget(security_box, 2, 0, 1, 2)

        footer = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        footer.addWidget(self.progress, 1)
        footer.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.export_button = QPushButton("Start Export")
        set_primary(self.export_button)
        self.export_button.clicked.connect(self._start_export)
        footer.addWidget(self.export_button)
        root.addLayout(footer)

    def _choose_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Export Directory", self.destination.text())
        if path:
            self.destination.setText(path)

    def _start_export(self) -> None:
        options = ExportOptions(
            user_ids=[
                int(check.property("userId")) for check in self.user_checks if check.isChecked()
            ],
            modules=[check.property("module") for check in self.module_checks if check.isChecked()],
            include_xlsx=self.xlsx.isChecked(),
            include_csv=self.csv.isChecked(),
            include_json=self.json.isChecked(),
            include_landmarks=self.landmarks.isChecked(),
            include_quality=self.quality.isChecked(),
            anonymize=self.anonymize.isChecked(),
            zip_package=self.zip_package.isChecked(),
        )
        self.export_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        worker = TaskWorker(
            self.export_service.export, options, Path(self.destination.text())
        )
        worker.signals.result.connect(self._export_finished)
        worker.signals.error.connect(lambda message: show_error(self, "Export failed", message))
        worker.signals.finished.connect(self._task_finished)
        self._worker = worker
        QThreadPool.globalInstance().start(worker)

    def _task_finished(self) -> None:
        self.progress.setVisible(False)
        self.export_button.setEnabled(True)
        self._worker = None

    def _export_finished(self, result: ExportResult) -> None:
        show_info(
            self,
            "Export complete",
            f"Exported {result.user_count} users and {result.session_count} assessment sessions.\n\n"
            f"File: {result.output_path}\nSHA-256: {result.sha256[:24]}…",
        )
        self.accept()
