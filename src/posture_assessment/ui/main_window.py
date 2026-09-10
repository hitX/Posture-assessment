from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from posture_assessment.config import AppSettings
from posture_assessment.dongle import DongleAdapter
from posture_assessment.import_export import UserExportService, UserImportService
from posture_assessment.models import AssessmentSession, User
from posture_assessment.pelvis.service import PelvisService
from posture_assessment.posture.service import PostureService
from posture_assessment.services import UserService
from posture_assessment.ui.dialogs import SettingsDialog
from posture_assessment.ui.pelvis_page import PelvisPage
from posture_assessment.ui.posture_page import PosturePage
from posture_assessment.ui.theme import NAV, PINK, PINK_DARK
from posture_assessment.ui.user_page import UserPage


class PlaceholderPage(QWidget):
    MODULE_LABELS = {
        "步态检测": "Gait Assessment",
        "脊柱评估": "Spine Assessment",
        "关节活动度": "Joint Range of Motion",
        "足底检测": "Foot Pressure Assessment",
        "查看报告": "View Reports",
        "生成": "Generate",
    }

    def __init__(self, module_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.module_name = module_name
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(self.MODULE_LABELS.get(module_name, module_name))
        self.title.setStyleSheet("font-size:32px; font-weight:700;")
        layout.addWidget(self.title, alignment=Qt.AlignmentFlag.AlignCenter)
        self.context = QLabel("This module will be implemented in a later phase.")
        self.context.setObjectName("muted")
        self.context.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.context, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_detection_context(self, user: User, assessment: AssessmentSession) -> None:
        self.context.setText(
            f"Current subject: {user.name} ({user.patient_no})\n"
            f"Assessment session: {assessment.session_no}\n\n"
            "The user information workflow has handed off the assessment."
        )


class MainWindow(QMainWindow):
    MODULES = [
        "用户信息",
        "体态检测",
        "步态检测",
        "骨盆检测",
        "脊柱评估",
        "关节活动度",
        "足底检测",
        "查看报告",
        "生成",
    ]
    MODULE_LABELS = {
        "用户信息": "User Profiles",
        "体态检测": "Posture Assessment",
        "步态检测": "Gait Assessment",
        "骨盆检测": "Pelvis Assessment",
        "脊柱评估": "Spine Assessment",
        "关节活动度": "Joint Range of Motion",
        "足底检测": "Foot Pressure Assessment",
        "查看报告": "View Reports",
        "生成": "Generate",
    }

    def __init__(
        self,
        settings: AppSettings,
        user_service: UserService,
        import_service: UserImportService,
        export_service: UserExportService,
        dongle: DongleAdapter,
        operator_name: str,
        parent: QWidget | None = None,
        posture_service: PostureService | None = None,
        pelvis_service: PelvisService | None = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.dongle = dongle
        self.operator_name = operator_name
        self.posture_service = posture_service or PostureService(user_service.db, settings)
        self.pelvis_service = pelvis_service or PelvisService(user_service.db, settings)
        self.setWindowTitle("Posture Assessment System")
        self.setMinimumSize(1200, 760)
        self._build_ui(user_service, import_service, export_service)

    def _build_ui(
        self,
        user_service: UserService,
        import_service: UserImportService,
        export_service: UserExportService,
    ) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        title_bar = QFrame()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet("background:#f6f6f6; border-bottom:1px solid #ddd;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 0, 12, 0)
        logo = QLabel("P  POSTURE")
        logo.setStyleSheet("color:#777; font-weight:700;")
        title_layout.addWidget(logo)
        title_layout.addStretch()
        title_layout.addWidget(QLabel(f"Operator: {self.operator_name}"))
        settings_button = QPushButton("Settings")
        settings_button.setStyleSheet("border:none; background:transparent;")
        settings_button.clicked.connect(self._open_settings)
        title_layout.addWidget(settings_button)
        root.addWidget(title_bar)

        nav = QFrame()
        nav.setFixedHeight(82)
        nav.setStyleSheet(f"background:{NAV};")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(22, 16, 22, 16)
        nav_layout.setSpacing(8)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.pages = QStackedWidget()
        self.page_indexes: dict[str, int] = {}
        for module in self.MODULES:
            button = QPushButton(self.MODULE_LABELS[module])
            button.setCheckable(True)
            button.setMinimumHeight(48)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.setStyleSheet(
                f"QPushButton {{ color:white; font-size:13px; font-weight:600; border:none; "
                f"border-radius:3px; padding:4px 6px; background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {PINK},stop:1 {PINK_DARK}); }}"
                "QPushButton:hover { border:1px solid white; }"
                "QPushButton:checked { border:2px solid white; background:#c53e50; }"
            )
            button.clicked.connect(lambda checked=False, name=module: self.show_module(name))
            self.nav_group.addButton(button)
            self.nav_buttons[module] = button
            nav_layout.addWidget(button, 1)
        nav_layout.addStretch()
        root.addWidget(nav)

        self.user_page = UserPage(
            user_service,
            import_service,
            export_service,
            self.settings.export_dir,
        )
        self.user_page.start_detection.connect(self._start_detection)
        self.page_indexes["用户信息"] = self.pages.addWidget(self.user_page)
        self.posture_page = PosturePage(self.posture_service, self.operator_name)
        self.posture_page.analysis_ready.connect(self._analysis_ready)
        self.page_indexes["体态检测"] = self.pages.addWidget(self.posture_page)
        for module in self.MODULES[2:]:
            if module == "骨盆检测":
                self.pelvis_page = PelvisPage(self.pelvis_service, self.operator_name)
                self.pelvis_page.analysis_ready.connect(self._pelvis_analysis_ready)
                page = self.pelvis_page
            else:
                page = PlaceholderPage(module)
            self.page_indexes[module] = self.pages.addWidget(page)
        root.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.nav_buttons["用户信息"].setChecked(True)
        self.show_module("用户信息")

    def show_module(self, module: str) -> None:
        # A single Azure Kinect cannot be owned by both worker processes at once.
        if module == "骨盆检测":
            self.posture_page.close_camera()
        elif module == "体态检测" and hasattr(self, "pelvis_page"):
            self.pelvis_page.close_camera()
        self.pages.setCurrentIndex(self.page_indexes[module])
        self.nav_buttons[module].setChecked(True)

    def _start_detection(self, user: User, assessment: AssessmentSession) -> None:
        self.posture_page.set_detection_context(user, assessment)
        self.pelvis_page.set_detection_context(user, assessment)
        self.show_module("体态检测")

    def _analysis_ready(self, assessment_id: int) -> None:
        page = self.pages.widget(self.page_indexes["查看报告"])
        if isinstance(page, PlaceholderPage):
            page.context.setText(
                f"Posture AnalysisResult is ready (session_id={assessment_id}).\n"
                "The report module can read the stable package through analysis_ready(session_id)."
            )

    def _pelvis_analysis_ready(self, assessment_id: int) -> None:
        page = self.pages.widget(self.page_indexes["查看报告"])
        if isinstance(page, PlaceholderPage):
            page.context.setText(
                f"PelvisAnalysisResult is ready (session_id={assessment_id}).\n"
                "The report module can read structured proxy metrics, quality data, the algorithm version, and the disclaimer."
            )

    def _open_settings(self) -> None:
        SettingsDialog(
            self.settings,
            self.dongle,
            self,
            posture_service=self.posture_service,
        ).exec()

    def closeEvent(self, event) -> None:
        self.posture_page.close_camera()
        self.pelvis_page.close_camera()
        super().closeEvent(event)
