from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from posture_assessment.import_export import UserExportService, UserImportService
from posture_assessment.localization import display_sex
from posture_assessment.models import User
from posture_assessment.services import UserService
from posture_assessment.ui.dialogs import (
    UserDetailsDialog,
    UserFormDialog,
    confirm,
    show_error,
    show_info,
)
from posture_assessment.ui.export_dialog import ExportDialog
from posture_assessment.ui.import_dialog import BatchImportDialog
from posture_assessment.ui.theme import set_primary


class UserPage(QWidget):
    start_detection = Signal(object, object)

    def __init__(
        self,
        user_service: UserService,
        import_service: UserImportService,
        export_service: UserExportService,
        export_dir,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.user_service = user_service
        self.import_service = import_service
        self.export_service = export_service
        self.export_dir = export_dir
        self.current_page = 1
        self.page_size = 20
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 34, 34, 24)
        root.setSpacing(18)
        filters = QHBoxLayout()
        self.patient_no = QLineEdit()
        self.patient_no.setPlaceholderText("Patient ID")
        self.patient_no.setMaximumWidth(180)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name")
        self.name.setMaximumWidth(180)
        self.mobile = QLineEdit()
        self.mobile.setPlaceholderText("Mobile")
        self.mobile.setMaximumWidth(180)
        for label, widget in (
            ("ID", self.patient_no),
            ("Name", self.name),
            ("Mobile", self.mobile),
        ):
            filters.addWidget(QLabel(label))
            filters.addWidget(widget)
        search = QPushButton("Search")
        set_primary(search)
        search.clicked.connect(self._search)
        filters.addWidget(search)
        clear = QPushButton("Clear")
        set_primary(clear)
        clear.clicked.connect(self._clear)
        filters.addWidget(clear)
        register = QPushButton("Register")
        set_primary(register)
        register.clicked.connect(self._create_user)
        filters.addWidget(register)
        import_button = QPushButton("Batch Import")
        import_button.clicked.connect(self._open_import)
        filters.addWidget(import_button)
        export_button = QPushButton("Export Assessment Data")
        export_button.clicked.connect(self._open_export)
        filters.addWidget(export_button)
        filters.addStretch()
        root.addLayout(filters)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(
            [
                "",
                "ID",
                "Name",
                "Birth Date",
                "Sex",
                "Phone",
                "Last Assessment",
                "Address",
                "Start",
                "View",
                "Edit",
                "Archive",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 32)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.total_label = QLabel()
        self.total_label.setObjectName("muted")
        footer.addWidget(self.total_label)
        footer.addStretch()
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self._previous_page)
        footer.addWidget(self.prev_button)
        self.page_label = QLabel()
        footer.addWidget(self.page_label)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self._next_page)
        footer.addWidget(self.next_button)
        root.addLayout(footer)

    def refresh(self) -> None:
        result = self.user_service.search(
            patient_no=self.patient_no.text(),
            name=self.name.text(),
            mobile=self.mobile.text(),
            page=self.current_page,
            page_size=self.page_size,
        )
        if self.current_page > result.pages:
            self.current_page = result.pages
            return self.refresh()
        self.table.setRowCount(len(result.items))
        for row, user in enumerate(result.items):
            latest = self.user_service.list_assessments(user.id)
            latest_time = latest[0].started_at.strftime("%Y/%m/%d %H:%M:%S") if latest else "-"
            values = [
                ">",
                user.patient_no,
                user.name,
                user.birth_date.strftime("%Y/%m/%d"),
                display_sex(user.sex),
                user.mobile or "-",
                latest_time,
                user.address or "Incomplete",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if not user.profile_complete:
                    item.setToolTip("Profile incomplete; complete it before starting an assessment.")
                self.table.setItem(row, col, item)
            self.table.setCellWidget(row, 8, self._action_button("Start", "Start assessment", lambda _, u=user: self._start_user(u)))
            self.table.setCellWidget(row, 9, self._action_button("View", "View details", lambda _, u=user: self._view_user(u)))
            self.table.setCellWidget(row, 10, self._action_button("Edit", "Edit profile", lambda _, u=user: self._edit_user(u)))
            self.table.setCellWidget(row, 11, self._action_button("Archive", "Archive patient", lambda _, u=user: self._archive_user(u)))
            self.table.setRowHeight(row, 48)
        self.total_label.setText(f"{result.total} records")
        self.page_label.setText(f"Page {result.page} / {result.pages}")
        self.prev_button.setEnabled(result.page > 1)
        self.next_button.setEnabled(result.page < result.pages)

    @staticmethod
    def _action_button(text: str, tooltip: str, callback) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setStyleSheet("font-size:13px;")
        button.clicked.connect(callback)
        return button

    def _search(self) -> None:
        self.current_page = 1
        self.refresh()

    def _clear(self) -> None:
        for widget in (self.patient_no, self.name, self.mobile):
            widget.clear()
        self.current_page = 1
        self.refresh()

    def _previous_page(self) -> None:
        self.current_page = max(1, self.current_page - 1)
        self.refresh()

    def _next_page(self) -> None:
        self.current_page += 1
        self.refresh()

    def _create_user(self) -> None:
        dialog = UserFormDialog(self.user_service, parent=self)
        if dialog.exec():
            self.current_page = 1
            self.refresh()
            show_info(self, "Saved", "The patient profile was created.")

    def _edit_user(self, user: User) -> None:
        dialog = UserFormDialog(self.user_service, user=user, parent=self)
        if dialog.exec():
            self.refresh()

    def _view_user(self, user: User) -> None:
        UserDetailsDialog(self.user_service, user, self).exec()

    def _archive_user(self, user: User) -> None:
        if not confirm(
            self,
            "Archive patient?",
            f"The profile for {user.name} will be archived. Existing reports will not be deleted.",
        ):
            return
        try:
            self.user_service.archive(user.id)
        except Exception as exc:
            show_error(self, "Archive failed", str(exc))
            return
        self.refresh()

    def _start_user(self, user: User) -> None:
        if not user.profile_complete:
            show_error(
                self,
                "Incomplete profile",
                "Complete the mobile number, height, weight, and address before starting an assessment.",
            )
            return
        if not confirm(
            self,
            "Start assessment",
            f"Subject: {user.name} ({user.patient_no})\n\nOnly one patient can be assessed at a time. Please confirm the information.",
        ):
            return
        try:
            assessment = self.user_service.start_assessment(user.id)
        except Exception as exc:
            show_error(self, "Cannot start assessment", str(exc))
            return
        self.refresh()
        self.start_detection.emit(user, assessment)

    def _open_import(self) -> None:
        dialog = BatchImportDialog(self.import_service, self)
        dialog.imported.connect(self.refresh)
        dialog.exec()
        self.refresh()

    def _open_export(self) -> None:
        ExportDialog(
            self.user_service,
            self.export_service,
            self.export_dir,
            self,
        ).exec()
