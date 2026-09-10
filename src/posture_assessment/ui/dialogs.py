from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from posture_assessment.config import AppSettings
from posture_assessment.dongle import DongleAdapter
from posture_assessment.models import User
from posture_assessment.localization import display_module, display_sex, display_status
from posture_assessment.services import UserInput, UserService
from posture_assessment.ui.theme import set_primary

if TYPE_CHECKING:
    from posture_assessment.posture.service import PostureService


def show_error(parent: QWidget, title: str, message: str) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def show_info(parent: QWidget, title: str, message: str) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def confirm(parent: QWidget, title: str, message: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(
        QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
    )
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    box.button(QMessageBox.StandardButton.Ok).setText("OK")
    box.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
    return box.exec() == QMessageBox.StandardButton.Ok


class UserFormDialog(QDialog):
    def __init__(
        self,
        service: UserService,
        user: User | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self.user = user
        self.saved_user: User | None = None
        self.setWindowTitle("Edit Patient Profile" if user else "New Patient")
        self.setMinimumWidth(820)
        self._build_ui()
        if user:
            self._load_user(user)
        else:
            self.patient_no.setText(service.generate_patient_no())
        self._update_age()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        root.addLayout(grid)

        self.patient_no = QLineEdit()
        self.name = QLineEdit()
        self.sex = QComboBox()
        self.sex.addItems(["Male", "Female", "Unspecified"])
        self.birth_date = QDateEdit(calendarPopup=True)
        self.birth_date.setDisplayFormat("yyyy/MM/dd")
        self.birth_date.setMaximumDate(QDate.currentDate())
        self.birth_date.setDate(QDate(1990, 1, 1))
        self.birth_date.dateChanged.connect(self._update_age)
        self.age = QLineEdit()
        self.age.setReadOnly(True)
        self.mobile = QLineEdit()
        self.height = QDoubleSpinBox()
        self.height.setRange(0, 250)
        self.height.setDecimals(1)
        self.height.setSuffix(" cm")
        self.height.setSpecialValueText("Not entered")
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0, 300)
        self.weight.setDecimals(1)
        self.weight.setSuffix(" kg")
        self.weight.setSpecialValueText("Not entered")
        self.address = QLineEdit()
        self.email = QLineEdit()
        self.notes = QLineEdit()

        fields = [
            ("Patient ID *", self.patient_no, "Name *", self.name),
            ("Sex *", self.sex, "Birth Date *", self.birth_date),
            ("Age", self.age, "Mobile *", self.mobile),
            ("Height *", self.height, "Weight *", self.weight),
            ("Address *", self.address, "", None),
            ("Email", self.email, "Notes", self.notes),
        ]
        for row, (left_label, left, right_label, right) in enumerate(fields):
            grid.addWidget(QLabel(left_label), row, 0)
            grid.addWidget(left, row, 1)
            if right is not None:
                grid.addWidget(QLabel(right_label), row, 2)
                grid.addWidget(right, row, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.addWidget(self.address, 4, 1, 1, 3)

        hint = QLabel("Patient IDs must be unique. Email and notes are optional. Age is calculated from the birth date.")
        hint.setObjectName("muted")
        root.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText("Save")
        set_primary(save_button)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        root.addWidget(buttons)

    def _load_user(self, user: User) -> None:
        self.patient_no.setText(user.patient_no)
        self.name.setText(user.name)
        self.sex.setCurrentText({"男": "Male", "女": "Female", "未说明": "Unspecified"}.get(user.sex, user.sex))
        self.birth_date.setDate(
            QDate(user.birth_date.year, user.birth_date.month, user.birth_date.day)
        )
        self.mobile.setText(user.mobile or "")
        self.height.setValue(user.height_cm or 0)
        self.weight.setValue(user.weight_kg or 0)
        self.address.setText(user.address or "")
        self.email.setText(user.email or "")
        self.notes.setText(user.notes or "")

    def _update_age(self) -> None:
        selected = self.birth_date.date().toPython()
        today = date.today()
        age = today.year - selected.year - (
            (today.month, today.day) < (selected.month, selected.day)
        )
        self.age.setText(str(max(0, age)))

    def _as_input(self) -> UserInput:
        return UserInput(
            patient_no=self.patient_no.text(),
            name=self.name.text(),
            sex={"Male": "男", "Female": "女", "Unspecified": "未说明"}.get(self.sex.currentText(), self.sex.currentText()),
            birth_date=self.birth_date.date().toPython(),
            mobile=self.mobile.text(),
            height_cm=self.height.value() or None,
            weight_kg=self.weight.value() or None,
            address=self.address.text(),
            email=self.email.text(),
            notes=self.notes.text(),
        )

    def _save(self) -> None:
        try:
            if self.user:
                self.saved_user = self.service.update(self.user.id, self._as_input())
            else:
                self.saved_user = self.service.create(self._as_input())
        except Exception as exc:
            show_error(self, "Save failed", str(exc))
            return
        self.accept()


class UserDetailsDialog(QDialog):
    def __init__(self, service: UserService, user: User, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Patient Details and Assessment History")
        self.setMinimumSize(800, 500)
        root = QVBoxLayout(self)
        info = QFrame()
        info.setObjectName("card")
        form = QGridLayout(info)
        values = [
            ("Patient ID", user.patient_no, "Name", user.name),
            ("Sex", display_sex(user.sex), "Birth Date", f"{user.birth_date:%Y/%m/%d} ({user.age} years)"),
            (
                "Height / Weight",
                f"{user.height_cm or '-'} cm / {user.weight_kg or '-'} kg",
                "Contact",
                user.mobile or "-",
            ),
            ("Address", user.address or "-", "Profile Status", "Complete" if user.profile_complete else "Incomplete"),
        ]
        for row, item in enumerate(values):
            for col, text in enumerate(item):
                label = QLabel(str(text))
                if col % 2 == 0:
                    label.setStyleSheet("font-weight: 700; background:#f2f2f2; padding:8px;")
                form.addWidget(label, row, col)
        root.addWidget(info)
        title = QLabel("Assessment History")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Time", "Module", "Status", "Report"])
        table.horizontalHeader().setStretchLastSection(True)
        assessments = service.list_assessments(user.id)
        table.setRowCount(len(assessments))
        for row, item in enumerate(assessments):
            values = [
                item.started_at.strftime("%Y/%m/%d %H:%M"),
                display_module(item.assessment_type),
                display_status(item.status),
                "View" if item.report_path else "Not generated",
            ]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))
        root.addWidget(table, 1)
        close = QPushButton("Close")
        set_primary(close)
        close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(close)
        root.addLayout(footer)


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        dongle: DongleAdapter,
        parent: QWidget | None = None,
        posture_service: "PostureService | None" = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("System Settings")
        self.setMinimumWidth(620)
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Data directory", QLabel(str(settings.data_dir)))
        form.addRow("Database", QLabel(str(settings.database_path)))
        form.addRow("Export directory", QLabel(str(settings.export_dir)))
        form.addRow("Posture raw data", QLabel(str(settings.assessment_dir)))
        form.addRow("Camera backend", QLabel(settings.camera_backend))
        form.addRow("Threshold configuration", QLabel(str(settings.posture_threshold_path)))
        self.storage_status = QLabel("Not measured")
        form.addRow("Raw data usage", self.storage_status)
        self.dongle_status = QLabel()
        form.addRow("Security dongle", self.dongle_status)
        root.addLayout(form)
        check = QPushButton("Check Security Dongle Again")
        check.clicked.connect(lambda: self._refresh_dongle(dongle))
        root.addWidget(check)
        if posture_service is not None:
            sessions, total = posture_service.storage_summary()
            self.storage_status.setText(f"{sessions} sessions, {self._format_bytes(total)} (not deleted automatically)")
            cleanup_row = QHBoxLayout()
            self.cleanup_days = QSpinBox()
            self.cleanup_days.setRange(1, 3650)
            self.cleanup_days.setValue(180)
            self.cleanup_days.setSuffix(" days")
            cleanup_row.addWidget(QLabel("Clean up older than"))
            cleanup_row.addWidget(self.cleanup_days)
            cleanup_button = QPushButton("Clean Completed / Failed Session Raw Data")
            cleanup_button.clicked.connect(lambda: self._cleanup(posture_service))
            cleanup_row.addWidget(cleanup_button)
            root.addLayout(cleanup_row)
            session_row = QHBoxLayout()
            self.cleanup_session_no = QLineEdit()
            self.cleanup_session_no.setPlaceholderText("AS2026…")
            session_row.addWidget(QLabel("Specific session"))
            session_row.addWidget(self.cleanup_session_no)
            session_button = QPushButton("Clean Specific Session Raw Data")
            session_button.clicked.connect(
                lambda: self._cleanup_session(posture_service)
            )
            session_row.addWidget(session_button)
            root.addLayout(session_row)
        close = QPushButton("Close")
        set_primary(close)
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self._refresh_dongle(dongle)

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"

    def _cleanup(self, posture_service: "PostureService") -> None:
        days = self.cleanup_days.value()
        if not confirm(
            self,
            "Delete raw data?",
            f"RGB, depth, MKV, and joint files older than {days} days with completed or failed status will be permanently deleted.\n"
            "Structured metrics and report data will remain. This action cannot be undone.",
        ):
            return
        count, freed = posture_service.cleanup_older_than(days)
        sessions, total = posture_service.storage_summary()
        self.storage_status.setText(f"{sessions} sessions, {self._format_bytes(total)} (not deleted automatically)")
        show_info(self, "Cleanup complete", f"Cleaned {count} sessions and freed {self._format_bytes(freed)}.")

    def _cleanup_session(self, posture_service: "PostureService") -> None:
        session_no = self.cleanup_session_no.text().strip()
        if not session_no:
            show_error(self, "Missing session number", "Enter the assessment session number to clean.")
            return
        if not confirm(
            self,
            "Delete session raw data?",
            f"RGB, depth, MKV, and joint files for session {session_no} will be permanently deleted.\n"
            "Structured metrics and report data will remain. This action cannot be undone.",
        ):
            return
        try:
            freed = posture_service.cleanup_session_raw_data(session_no)
        except Exception as exc:
            show_error(self, "Cleanup failed", str(exc))
            return
        sessions, total = posture_service.storage_summary()
        self.storage_status.setText(f"{sessions} sessions, {self._format_bytes(total)} (not deleted automatically)")
        show_info(self, "Cleanup complete", f"Session {session_no} released {self._format_bytes(freed)}.")

    def _refresh_dongle(self, dongle: DongleAdapter) -> None:
        status = dongle.check()
        self.dongle_status.setText(status.message)
        self.dongle_status.setStyleSheet(
            "color:#2e9d5b; font-weight:700;" if status.available else "color:#d14949; font-weight:700;"
        )
