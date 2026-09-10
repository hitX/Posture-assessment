from __future__ import annotations

import math
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, QTimer, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from posture_assessment.models import AssessmentSession, User
from posture_assessment.localization import (
    display_direction,
    display_disclaimer,
    display_level,
    display_metric,
    display_review_reason,
    display_sex,
)
from posture_assessment.posture.camera import DeviceInfo
from posture_assessment.posture.quality import FAILURE_MESSAGES
from posture_assessment.posture.service import PostureService
from posture_assessment.posture.types import (
    JOINT_INDEX,
    POSE_SEQUENCE,
    AnalysisResult,
    FrameBundle,
    PoseKind,
    QualityAssessment,
)
from posture_assessment.ui.dialogs import show_error, show_info
from posture_assessment.ui.theme import BORDER, PINK, set_primary
from posture_assessment.ui.workers import TaskWorker


class PostureUiState(str, Enum):
    IDLE = "待检测"
    DEVICE_CHECK = "设备自检"
    OVERVIEW = "五姿势概览"
    CAPTURE = "单姿势采集"
    REVIEW = "测量复核"
    ANALYZING = "分析中"
    RETAKE = "需重拍"
    RESULT = "已完成"


SKELETON_EDGES = (
    ("head", "neck"),
    ("neck", "spine_chest"),
    ("spine_chest", "spine_navel"),
    ("spine_navel", "pelvis"),
    ("spine_chest", "shoulder_left"),
    ("shoulder_left", "elbow_left"),
    ("elbow_left", "wrist_left"),
    ("spine_chest", "shoulder_right"),
    ("shoulder_right", "elbow_right"),
    ("elbow_right", "wrist_right"),
    ("pelvis", "hip_left"),
    ("hip_left", "knee_left"),
    ("knee_left", "ankle_left"),
    ("pelvis", "hip_right"),
    ("hip_right", "knee_right"),
    ("knee_right", "ankle_right"),
)


def point_cloud_pixmap(frame: FrameBundle, pose: PoseKind, width: int = 360, height: int = 520) -> QPixmap:
    depth = frame.depth_mm
    mask = (frame.body_mask > 0) & (depth > 0)
    rgb = np.zeros((*depth.shape, 3), dtype=np.uint8)
    if np.any(mask):
        values = depth[mask].astype(float)
        low, high = float(np.percentile(values, 2)), float(np.percentile(values, 98))
        normalized = np.clip((depth.astype(float) - low) / max(1.0, high - low), 0.0, 1.0)
        rgb[..., 0] = np.where(mask, 20 + normalized * 20, 4).astype(np.uint8)
        rgb[..., 1] = np.where(mask, 105 + (1 - normalized) * 80, 17).astype(np.uint8)
        rgb[..., 2] = np.where(mask, 205 + (1 - normalized) * 45, 35).astype(np.uint8)
        # Sparse highlight points make depth contours visible without fabricating a mesh.
        yy, xx = np.indices(depth.shape)
        dots = mask & (((xx + yy) % 5) == 0)
        rgb[dots] = (85, 210, 255)
    image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
    pixmap = QPixmap.fromImage(image).scaled(
        width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    canvas = QPixmap(width, height)
    canvas.fill(QColor("#06172d"))
    painter = QPainter(canvas)
    x_offset = (width - pixmap.width()) // 2
    y_offset = (height - pixmap.height()) // 2
    painter.drawPixmap(x_offset, y_offset, pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    joints = np.median(frame.joints_mm, axis=0) if frame.joints_mm.ndim == 3 else frame.joints_mm
    if pose in (PoseKind.LEFT, PoseKind.RIGHT, PoseKind.ADAMS):
        horizontal = joints[:, 2] - np.median(joints[:, 2])
    else:
        horizontal = joints[:, 0]
    vertical = joints[:, 1]
    px = width / 2 + horizontal * (width / 1000.0)
    py = height - 22 - vertical * (height / 1850.0)
    pen = QPen(QColor("#ff5a73"), 2)
    painter.setPen(pen)
    for start, end in SKELETON_EDGES:
        a, b = JOINT_INDEX[start], JOINT_INDEX[end]
        painter.drawLine(QPointF(px[a], py[a]), QPointF(px[b], py[b]))
    painter.setBrush(QColor("#ffd15c"))
    for index in (0, 2, 3, 5, 12, 18, 22, 19, 23, 20, 24, 26):
        painter.drawEllipse(QPointF(px[index], py[index]), 3.5, 3.5)
    painter.end()
    return canvas


class ReviewCanvas(QGraphicsView):
    annotations_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._background: QGraphicsPixmapItem | None = None
        self._annotations: list[QGraphicsLineItem] = []
        self._redo: list[tuple[QPointF, QPointF, str]] = []
        self._start: QPointF | None = None
        self.tool = "量尺"
        self.setMinimumSize(420, 560)

    def set_frame(self, frame: FrameBundle, pose: PoseKind) -> None:
        self.scene().clear()
        pixmap = point_cloud_pixmap(frame, pose, 420, 560)
        self._background = self.scene().addPixmap(pixmap)
        self.scene().setSceneRect(pixmap.rect())
        self._annotations.clear()
        self._redo.clear()
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag if tool == "拖动" else QGraphicsView.DragMode.NoDrag
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.tool not in {"拖动", "镜像"}:
            self._start = self.mapToScene(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._start is not None and event.button() == Qt.MouseButton.LeftButton:
            end = self.mapToScene(event.position().toPoint())
            if self.tool == "水平线":
                end.setY(self._start.y())
            elif self.tool == "垂线":
                end.setX(self._start.x())
            item = self.scene().addLine(
                self._start.x(), self._start.y(), end.x(), end.y(), QPen(QColor(PINK), 2)
            )
            item.setData(0, self.tool)
            self._annotations.append(item)
            self._redo.clear()
            self._start = None
            self.annotations_changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def zoom_in(self) -> None:
        self.scale(1.2, 1.2)

    def zoom_out(self) -> None:
        self.scale(1 / 1.2, 1 / 1.2)

    def mirror(self) -> None:
        self.scale(-1, 1)

    def undo(self) -> None:
        if not self._annotations:
            return
        item = self._annotations.pop()
        line = item.line()
        self._redo.append((line.p1(), line.p2(), str(item.data(0))))
        self.scene().removeItem(item)
        self.annotations_changed.emit()

    def redo(self) -> None:
        if not self._redo:
            return
        start, end, tool = self._redo.pop()
        item = self.scene().addLine(start.x(), start.y(), end.x(), end.y(), QPen(QColor(PINK), 2))
        item.setData(0, tool)
        self._annotations.append(item)
        self.annotations_changed.emit()

    def annotation_data(self) -> list[dict[str, Any]]:
        output = []
        for item in self._annotations:
            line = item.line()
            length = math.hypot(line.dx(), line.dy())
            output.append(
                {
                    "tool": str(item.data(0)),
                    "start": [round(line.x1(), 2), round(line.y1(), 2)],
                    "end": [round(line.x2(), 2), round(line.y2(), 2)],
                    "display_length_px": round(length, 2),
                    "manual_angle_deg": (
                        round(math.degrees(math.atan2(-line.dy(), line.dx())), 2)
                        if str(item.data(0)) == "角度"
                        else None
                    ),
                    "affects_automatic_measurement": False,
                }
            )
        return output

    def load_annotations(self, annotations: list[dict[str, Any]]) -> None:
        for annotation in annotations:
            start = annotation.get("start", [0.0, 0.0])
            end = annotation.get("end", [0.0, 0.0])
            item = self.scene().addLine(
                float(start[0]),
                float(start[1]),
                float(end[0]),
                float(end[1]),
                QPen(QColor(PINK), 2),
            )
            item.setData(0, str(annotation.get("tool", "量尺")))
            self._annotations.append(item)
        self._redo.clear()


class CaptureDialog(QDialog):
    capture_finished = Signal(object, object)

    def __init__(
        self,
        service: PostureService,
        assessment_id: int,
        pose: PoseKind,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self.assessment_id = assessment_id
        self.pose = pose
        self.thread_pool = QThreadPool.globalInstance()
        self._preview_busy = False
        self._capture_pending = False
        self._closing = False
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(66)
        self.preview_timer.timeout.connect(self._load_preview)
        self.setWindowTitle(f"Posture Assessment - {pose.label}")
        self.resize(980, 720)
        root = QVBoxLayout(self)
        self.instruction = QLabel(self._instruction_text())
        self.instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instruction.setStyleSheet("font-size:18px; font-weight:700;")
        root.addWidget(self.instruction)
        self.preview = QLabel("Loading depth preview…")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#05080c; color:white;")
        self.preview.setMinimumSize(760, 520)
        root.addWidget(self.preview, 1)
        footer = QHBoxLayout()
        self.status = QLabel("Preparing camera")
        footer.addWidget(self.status)
        footer.addStretch()
        self.capture_button = QPushButton("Save 2-second stable window")
        set_primary(self.capture_button)
        self.capture_button.setEnabled(False)
        self.capture_button.clicked.connect(self._capture)
        footer.addWidget(self.capture_button)
        root.addLayout(footer)
        self._load_preview()

    def _instruction_text(self) -> str:
        if self.pose is PoseKind.ADAMS:
            return "Wear fitted sportswear, bend the torso to 80–100°, and keep the back unobstructed."
        return f"Stand facing {self.pose.label} in the calibrated area, 1.8–2.2 m from the camera."

    def _load_preview(self) -> None:
        if self._preview_busy or self._capture_pending:
            return
        self._preview_busy = True
        worker = TaskWorker(self.service.preview, self.pose)
        worker.signals.result.connect(self._preview_ready)
        worker.signals.error.connect(self._preview_failed)
        self.thread_pool.start(worker)

    def _preview_ready(self, frame: FrameBundle) -> None:
        self._preview_busy = False
        self.preview.setPixmap(
            point_cloud_pixmap(frame, self.pose, 760, 520).scaled(
                self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self.status.setText("● Camera connected · Preview shows RGB-D body outline and skeleton")
        self.capture_button.setEnabled(True)
        if self._capture_pending:
            self._start_capture_worker()
        elif not self._closing and not self.preview_timer.isActive():
            self.preview_timer.start()

    def _preview_failed(self, message: str) -> None:
        self._preview_busy = False
        self.preview_timer.stop()
        self._failed("Preview failed", message)

    def _capture(self) -> None:
        self.preview_timer.stop()
        self.capture_button.setEnabled(False)
        self.capture_button.setText("Recording stable window…")
        self.status.setText("Stand naturally and remain still")
        self._capture_pending = True
        if self._preview_busy:
            return
        self._start_capture_worker()

    def _start_capture_worker(self) -> None:
        self._capture_pending = False
        worker = TaskWorker(self.service.capture_pose, self.assessment_id, self.pose)
        worker.signals.result.connect(self._capture_ready)
        worker.signals.error.connect(lambda message: self._failed("Capture failed", message))
        self.thread_pool.start(worker)

    def _capture_ready(self, payload) -> None:
        self.preview_timer.stop()
        capture, quality = payload
        self.capture_finished.emit(capture, quality)
        if quality.passed:
            self.accept()
            return
        messages = [FAILURE_MESSAGES.get(code, code) for code in quality.failure_codes]
        self.status.setText("Quality gate failed: " + "; ".join(messages))
        self.capture_button.setText("Recapture this pose")
        self.capture_button.setEnabled(True)

    def _failed(self, title: str, message: str) -> None:
        self._capture_pending = False
        self.status.setText(message)
        self.capture_button.setText("Retry")
        self.capture_button.setEnabled(True)
        show_error(self, title, message)

    def done(self, result: int) -> None:
        self._closing = True
        self.preview_timer.stop()
        super().done(result)


class PoseCard(QFrame):
    capture_requested = Signal(object)

    def __init__(self, pose: PoseKind, parent: QWidget | None = None):
        super().__init__(parent)
        self.pose = pose
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        self.number = QLabel(str(POSE_SEQUENCE.index(pose) + 1))
        self.number.setStyleSheet(f"color:{PINK}; font-size:18px; font-weight:700;")
        layout.addWidget(self.number)
        self.preview = QLabel("Body detected\nWaiting for capture")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(170, 300)
        self.preview.setStyleSheet("background:#f8f9fa; color:#aeb2b5;")
        layout.addWidget(self.preview, 1)
        self.button = QPushButton(pose.label)
        set_primary(self.button)
        self.button.clicked.connect(lambda: self.capture_requested.emit(self.pose))
        layout.addWidget(self.button)
        self.status = QLabel("Waiting")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

    def update_capture(self, frame: FrameBundle, quality: QualityAssessment) -> None:
        self.preview.setPixmap(point_cloud_pixmap(frame, self.pose, 180, 300))
        if quality.passed:
            self.status.setText("✓ Captured · Quality gate passed")
            self.status.setStyleSheet("color:#32945c;")
            self.button.setText(f"Recapture {self.pose.label}")
        else:
            self.status.setText("Recapture required")
            self.status.setStyleSheet(f"color:{PINK};")


class PosturePage(QWidget):
    analysis_ready = Signal(int)

    def __init__(
        self,
        service: PostureService,
        operator_name: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self.operator_name = operator_name
        self.user: User | None = None
        self.assessment: AssessmentSession | None = None
        self.state = PostureUiState.IDLE
        self.device_info: DeviceInfo | None = None
        self.qualities: dict[PoseKind, QualityAssessment] = {}
        self.frames: dict[PoseKind, FrameBundle] = {}
        self.result: AnalysisResult | None = None
        self.review_annotations: dict[PoseKind, list[dict[str, Any]]] = {}
        self._review_current_pose: PoseKind | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.patient_bar = QLabel("Select a subject from User Profiles first")
        self.patient_bar.setStyleSheet("background:white; border-bottom:1px solid #d5d7d9; padding:12px 28px;")
        root.addWidget(self.patient_bar)
        self.stack = QStackedWidget()
        self.overview_page = self._build_overview()
        self.review_page = self._build_review()
        self.analysis_page = self._build_analysis()
        self.result_page = self._build_result()
        for page in (self.overview_page, self.review_page, self.analysis_page, self.result_page):
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)

    def _build_overview(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(36, 24, 36, 20)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Azure Kinect Five-Pose Posture Capture")
        title.setObjectName("pageTitle")
        title_box.addWidget(title)
        self.device_label = QLabel(
            "Run device and environment checks first; simulation is available when hardware is unavailable."
        )
        self.device_label.setObjectName("muted")
        title_box.addWidget(self.device_label)
        header.addLayout(title_box)
        header.addStretch()
        self.self_check_button = QPushButton("Device and Environment Check")
        self.self_check_button.clicked.connect(self._device_check)
        header.addWidget(self.self_check_button)
        root.addLayout(header)
        cards = QHBoxLayout()
        cards.setSpacing(18)
        self.pose_cards: dict[PoseKind, PoseCard] = {}
        for pose in POSE_SEQUENCE:
            card = PoseCard(pose)
            card.capture_requested.connect(self._open_capture)
            card.button.setEnabled(False)
            cards.addWidget(card, 1)
            self.pose_cards[pose] = card
        root.addLayout(cards, 1)
        footer = QHBoxLayout()
        self.summary_label = QLabel("Poses: 0 / 5   Stable window: 2.0s   Depth coverage: -")
        self.summary_label.setObjectName("muted")
        footer.addWidget(self.summary_label)
        footer.addStretch()
        self.review_button = QPushButton("Measurement Review")
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._show_review)
        footer.addWidget(self.review_button)
        self.analyze_button = QPushButton("Start Analysis")
        set_primary(self.analyze_button)
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self._start_analysis)
        footer.addWidget(self.analyze_button)
        root.addLayout(footer)
        return page

    def _build_review(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        toolbar = QToolBar()
        tools = (
            ("量尺", "Ruler"),
            ("直尺", "Straightedge"),
            ("拖动", "Pan"),
            ("镜像", "Mirror"),
            ("水平线", "Horizontal Line"),
            ("垂线", "Vertical Line"),
            ("角度", "Angle"),
        )
        for tool, label in tools:
            action = toolbar.addAction(label)
            action.triggered.connect(lambda checked=False, name=tool: self._select_review_tool(name))
        toolbar.addSeparator()
        toolbar.addAction("Zoom In", lambda: self.review_canvas.zoom_in())
        toolbar.addAction("Zoom Out", lambda: self.review_canvas.zoom_out())
        toolbar.addAction("Undo", lambda: self.review_canvas.undo())
        toolbar.addAction("Redo", lambda: self.review_canvas.redo())
        root.addWidget(toolbar)
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.review_pose = QComboBox()
        for pose in POSE_SEQUENCE:
            self.review_pose.addItem(pose.label, pose)
        self.review_pose.currentIndexChanged.connect(self._refresh_review)
        left.addWidget(self.review_pose)
        self.review_canvas = ReviewCanvas()
        left.addWidget(self.review_canvas, 1)
        body.addLayout(left, 2)
        panel = QFrame()
        panel.setObjectName("card")
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(QLabel("Automatic Points and Quality Review"))
        self.quality_table = QTableWidget(0, 2)
        self.quality_table.setHorizontalHeaderLabels(["Quality Metric", "Automatic Value"])
        self.quality_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.quality_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        panel_layout.addWidget(self.quality_table)
        note = QLabel("Manual lines are saved as independent review annotations and do not overwrite automatic points or metrics.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        panel_layout.addWidget(note)
        buttons = QHBoxLayout()
        back = QPushButton("Return to Capture")
        back.clicked.connect(lambda: self.stack.setCurrentWidget(self.overview_page))
        buttons.addWidget(back)
        confirm = QPushButton("Confirm Review and Analyze")
        set_primary(confirm)
        confirm.clicked.connect(self._confirm_review)
        buttons.addWidget(confirm)
        panel_layout.addLayout(buttons)
        body.addWidget(panel, 1)
        root.addLayout(body, 1)
        return page

    def _build_analysis(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Posture Data Analysis")
        title.setObjectName("pageTitle")
        root.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        self.analysis_status = QLabel("Aligning five poses, RGB, depth point clouds, and body coordinates")
        root.addWidget(self.analysis_status, alignment=Qt.AlignmentFlag.AlignCenter)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 0)
        self.analysis_progress.setFixedWidth(720)
        root.addWidget(self.analysis_progress, alignment=Qt.AlignmentFlag.AlignCenter)
        stages = QHBoxLayout()
        for number, text in enumerate(("Sync and Calibration", "Body Segmentation", "Surface Proxy Points", "Cross-Pose Registration", "Metrics and Findings"), 1):
            label = QLabel(f"{number:02d}\n{text}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFrameShape(QFrame.Shape.Box)
            label.setMinimumSize(135, 70)
            stages.addWidget(label)
        root.addLayout(stages)
        return page

    def _build_result(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        title = QLabel("Posture Results Overview")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        self.result_visuals = QHBoxLayout()
        self.result_disclaimer = QLabel("For posture screening support only; not a medical diagnosis.")
        self.result_disclaimer.setWordWrap(True)
        self.result_disclaimer.setStyleSheet(f"color:{PINK}; font-weight:700;")
        root.addWidget(self.result_disclaimer)
        panel = QFrame()
        panel.setObjectName("card")
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(QLabel("Measurements and Actual Values"))
        self.result_table = QTableWidget(0, 4)
        self.result_table.setHorizontalHeaderLabels(["Metric", "Value", "Level", "Confidence"])
        self.result_table.setWordWrap(False)
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        self.result_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.result_table.verticalHeader().setDefaultSectionSize(30)
        self.result_table.setStyleSheet(
            "QTableWidget { font-size: 10px; } "
            "QHeaderView::section { font-size: 10px; font-weight: 700; padding: 4px; }"
        )
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        panel_layout.addWidget(self.result_table, 1)
        self.review_reason_label = QLabel()
        self.review_reason_label.setWordWrap(True)
        self.review_reason_label.setObjectName("muted")
        panel_layout.addWidget(self.review_reason_label)
        buttons = QHBoxLayout()
        retake = QPushButton("Recapture")
        retake.clicked.connect(lambda: self.stack.setCurrentWidget(self.overview_page))
        buttons.addWidget(retake)
        self.finalize_review_button = QPushButton("Confirm Cross-Pose Review")
        self.finalize_review_button.clicked.connect(self._finalize_cross_pose_review)
        buttons.addWidget(self.finalize_review_button)
        report = QPushButton("Posture Report Interface")
        set_primary(report)
        report.clicked.connect(self._report_hook)
        buttons.addWidget(report)
        panel_layout.addLayout(buttons)
        root.addWidget(panel, 1)
        return page

    def set_detection_context(self, user: User, assessment: AssessmentSession) -> None:
        self.user = user
        self.assessment = assessment
        self.state = PostureUiState.OVERVIEW
        self.qualities.clear()
        self.frames.clear()
        self.result = None
        self.review_annotations.clear()
        self._review_current_pose = None
        self.patient_bar.setText(
            f"Subject   ID: {user.patient_no}   Name: {user.name}   Sex: {display_sex(user.sex)}   "
            f"Age: {user.age}   Height: {user.height_cm:g} cm   Weight: {user.weight_kg:g} kg   "
            f"Session: {assessment.session_no}"
        )
        for card in self.pose_cards.values():
            card.status.setText("Waiting")
            card.status.setStyleSheet("")
            card.button.setText(card.pose.label)
            card.button.setEnabled(False)
            card.preview.clear()
            card.preview.setText("Body detected\nWaiting for capture")
        self.device_info = None
        self.device_label.setText("Run the device and environment check first")
        self.summary_label.setText("Poses: 0 / 5   Stable window: 2.0s   Depth coverage: -")
        self.review_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.stack.setCurrentWidget(self.overview_page)

    def _device_check(self) -> None:
        if self.assessment is None:
            show_error(self, "No subject selected", "Start a new assessment session from User Profiles first.")
            return
        self.state = PostureUiState.DEVICE_CHECK
        self.self_check_button.setEnabled(False)
        self.self_check_button.setText("Checking…")
        worker = TaskWorker(self.service.restart_camera)
        worker.signals.result.connect(self._device_ready)
        worker.signals.error.connect(self._device_failed)
        self.thread_pool.start(worker)

    def _device_ready(self, info: DeviceInfo) -> None:
        self.device_info = info
        mode = "Simulation mode" if info.is_mock else "Hardware mode"
        self.device_label.setText(
            f"✓ {info.model} · {mode} · {info.tracking_mode} · Serial: {info.serial_number}\n{info.message}"
        )
        self.self_check_button.setText("Run Check Again")
        self.self_check_button.setEnabled(True)
        for card in self.pose_cards.values():
            card.button.setEnabled(True)
        self.state = PostureUiState.OVERVIEW

    def _device_failed(self, message: str) -> None:
        self.device_label.setText("Device check failed: " + message)
        self.self_check_button.setText("Retry Device Check")
        self.self_check_button.setEnabled(True)
        self.state = PostureUiState.RETAKE
        show_error(self, "Device check failed", message)

    def _open_capture(self, pose: PoseKind) -> None:
        if self.assessment is None or self.device_info is None:
            show_error(self, "Device not ready", "Complete the device and environment check first.")
            return
        self.state = PostureUiState.CAPTURE
        dialog = CaptureDialog(self.service, self.assessment.id, pose, self)
        dialog.capture_finished.connect(lambda capture, quality, p=pose: self._capture_finished(p, quality))
        dialog.exec()
        self.state = PostureUiState.OVERVIEW

    def _capture_finished(self, pose: PoseKind, quality: QualityAssessment) -> None:
        self.qualities[pose] = quality
        self.review_annotations.pop(pose, None)
        if self._review_current_pose is pose:
            self._review_current_pose = None
        try:
            if self.assessment is not None:
                frame = self.service.representative_frame(self.assessment.id, pose)
                if frame is not None:
                    self.frames[pose] = frame
                    self.pose_cards[pose].update_capture(frame, quality)
        except Exception:
            pass
        passed = sum(item.passed for item in self.qualities.values())
        coverage = (
            sum(item.depth_coverage for item in self.qualities.values()) / len(self.qualities)
            if self.qualities
            else 0.0
        )
        self.summary_label.setText(
            f"Poses: {passed} / 5   Stable window: 2.0s   Average depth coverage: {coverage:.0%}"
        )
        ready = passed == len(POSE_SEQUENCE) and all(pose in self.qualities for pose in POSE_SEQUENCE)
        self.review_button.setEnabled(ready)
        self.analyze_button.setEnabled(ready)

    def _select_review_tool(self, tool: str) -> None:
        if tool == "镜像":
            self.review_canvas.mirror()
        else:
            self.review_canvas.set_tool(tool)

    def _show_review(self) -> None:
        self.state = PostureUiState.REVIEW
        self.stack.setCurrentWidget(self.review_page)
        self._refresh_review()

    def _refresh_review(self) -> None:
        if self._review_current_pose is not None:
            self.review_annotations[self._review_current_pose] = (
                self.review_canvas.annotation_data()
            )
        pose = self.review_pose.currentData()
        if not isinstance(pose, PoseKind) or pose not in self.frames:
            return
        self.review_canvas.set_frame(self.frames[pose], pose)
        self.review_canvas.load_annotations(self.review_annotations.get(pose, []))
        self._review_current_pose = pose
        quality = self.qualities[pose]
        values = [
            ("Valid depth coverage", f"{quality.depth_coverage:.0%}"),
            ("Body contour completeness", f"{quality.contour_coverage:.0%}"),
            ("Medium+ joints", f"{quality.joint_valid_count} / 32"),
            ("Pelvis stability", f"{quality.stability_mm:.1f} mm"),
            ("Trunk orientation deviation", f"{quality.orientation_std_deg:.1f}°"),
            ("Distance", f"{quality.distance_m:.2f} m"),
        ]
        self.quality_table.setRowCount(len(values))
        for row, (name, value) in enumerate(values):
            self.quality_table.setItem(row, 0, QTableWidgetItem(name))
            self.quality_table.setItem(row, 1, QTableWidgetItem(value))

    def _confirm_review(self) -> None:
        if self.assessment is None:
            return
        if self._review_current_pose is not None:
            self.review_annotations[self._review_current_pose] = (
                self.review_canvas.annotation_data()
            )
        annotations = [
            {**annotation, "pose": pose.value}
            for pose, pose_annotations in self.review_annotations.items()
            for annotation in pose_annotations
        ]
        self.service.record_review(
            self.assessment.id,
            self.operator_name,
            annotations,
            accepted=True,
            notes="Automatic values reviewed; manual annotations are stored separately.",
        )
        self._start_analysis()

    def _start_analysis(self) -> None:
        if self.assessment is None:
            return
        self.state = PostureUiState.ANALYZING
        self.stack.setCurrentWidget(self.analysis_page)
        worker = TaskWorker(self.service.analyze, self.assessment.id)
        worker.signals.result.connect(self._analysis_finished)
        worker.signals.error.connect(self._analysis_failed)
        self.thread_pool.start(worker)

    def _analysis_finished(self, result: AnalysisResult) -> None:
        self.result = result
        if result.retake_poses:
            self.state = PostureUiState.RETAKE
            self.stack.setCurrentWidget(self.overview_page)
            labels = "、".join(pose.label for pose in result.retake_poses)
            show_error(self, "Recapture Required", f"The following poses failed the hard quality gate: {labels}\nOther poses were retained.")
            return
        self.state = PostureUiState.RESULT
        self._populate_result(result)
        self.stack.setCurrentWidget(self.result_page)
        if self.assessment is not None and not result.review_reasons:
            self.analysis_ready.emit(self.assessment.id)

    def _analysis_failed(self, message: str) -> None:
        self.state = PostureUiState.RETAKE
        self.stack.setCurrentWidget(self.overview_page)
        show_error(self, "Posture analysis failed", message)

    def _populate_result(self, result: AnalysisResult) -> None:
        while self.result_visuals.count():
            item = self.result_visuals.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for pose in (PoseKind.FRONT, PoseKind.BACK, PoseKind.LEFT):
            if pose not in self.frames:
                continue
            label = QLabel()
            label.setPixmap(point_cloud_pixmap(self.frames[pose], pose, 260, 560))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_visuals.addWidget(label)
        important = [
            item
            for item in result.measurements
            if item.code
            in {
                "head_tilt_deg",
                "shoulder_line_angle_deg",
                "pelvic_shift_mm",
                "forward_head_mm",
                "spine_midline_deviation_deg",
                "adams_rotation_proxy_deg",
                "adams_height_diff_mm",
            }
        ]
        self.result_table.setRowCount(len(important))
        for row, item in enumerate(important):
            values = (
                display_metric(item.name),
                f"{item.value:g}{item.unit}" + (f" · {display_direction(item.direction)}" if item.direction else ""),
                display_level(item.screening_level),
                f"{item.confidence:.0f}%",
            )
            for column, value in enumerate(values):
                self.result_table.setItem(row, column, QTableWidgetItem(value))
        if result.review_reasons:
            self.review_reason_label.setText(
                "Cross-pose consistency review:\n"
                + "\n".join(display_review_reason(reason) for reason in result.review_reasons)
            )
            self.finalize_review_button.setVisible(True)
        else:
            self.review_reason_label.setText("All five pose quality gates and cross-pose consistency checks are complete.")
            self.finalize_review_button.setVisible(False)
        self.result_disclaimer.setText(
            display_disclaimer(result.disclaimer)
            + " All curvature, lateral-deviation, and surface-rotation metrics are proxy values."
        )

    def _report_hook(self) -> None:
        if self.assessment is None:
            return
        if self.result is not None and self.result.review_reasons:
            show_error(
                self,
                "Review Required",
                "Confirm the cross-pose differences first. The system will not directly average inconsistent measurements or generate report data early.",
            )
            return
        self.analysis_ready.emit(self.assessment.id)
        show_info(
            self,
            "Report Interface Ready",
            "The AnalysisResult package has been generated and analysis_ready(session_id) was emitted.\nPDF layout and export belong to a later report module.",
        )

    def _finalize_cross_pose_review(self) -> None:
        if self.assessment is None or self.result is None:
            return
        self.service.finalize_analysis_review(
            self.assessment.id,
            self.operator_name,
            "Cross-pose differences were manually reviewed; automatic values were not overwritten or directly averaged.",
        )
        self.result = AnalysisResult(
            assessment_session_id=self.result.assessment_session_id,
            pose_quality=self.result.pose_quality,
            measurements=self.result.measurements,
            retake_poses=self.result.retake_poses,
            review_reasons=(),
            algorithm_version=self.result.algorithm_version,
            threshold_version=self.result.threshold_version,
            disclaimer=self.result.disclaimer,
        )
        self.finalize_review_button.setVisible(False)
        self.review_reason_label.setText("Cross-pose differences were reviewed by the operator; automatic values remain unchanged.")
        self.analysis_ready.emit(self.assessment.id)

    def close_camera(self) -> None:
        self.service.close()
