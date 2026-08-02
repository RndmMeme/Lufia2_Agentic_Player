#!/usr/bin/env python3
"""Point-and-click editor for Lufia II dungeon map annotations.

The editor deliberately separates the 16x16 navigation lattice from manual
visual markers. Manual markers default to a 32x32 character-body footprint and
snap their top-left corner to the 16-pixel lattice.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QAction,
    QColor,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


BASE_GRID_PX = 16
DEFAULT_MARKER_PX = 16
MARKER_SCHEMA = "lufia2-dungeon-curation-markers-v1"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


@dataclass(frozen=True)
class MarkerKind:
    name: str
    symbol: str
    color: str
    default_traversal: str
    default_action: str = ""


MARKER_KINDS = (
    MarkerKind("bush", "b", "#ef3340", "conditional", "sword"),
    MarkerKind("door", "D", "#24c8ff", "confirmed_walkable"),
    MarkerKind("stairs", "T", "#6f8cff", "confirmed_walkable"),
    MarkerKind("ladder", "H", "#58d6c7", "confirmed_walkable"),
    MarkerKind("wall", "W", "#ff4055", "blocked"),
    MarkerKind("water", "~", "#168fff", "blocked"),
    MarkerKind("lava", "^", "#ff5a1f", "blocked"),
    MarkerKind("chest", "C", "#ffd43b", "blocked", "open"),
    MarkerKind("monster", "M", "#c85cff", "conditional"),
    MarkerKind("npc", "N", "#ff78c8", "conditional", "talk_or_move_around"),
    MarkerKind("switch", "s", "#f2b84b", "conditional", "activate"),
    MarkerKind("puzzle", "P", "#ff9d42", "conditional"),
    MarkerKind("walkable", "o", "#27d980", "confirmed_walkable"),
    MarkerKind("blocked", "#", "#ff4055", "blocked"),
)
KIND_BY_NAME = {kind.name: kind for kind in MARKER_KINDS}


def snap_marker_origin(
    scene_x: float,
    scene_y: float,
    width: int = DEFAULT_MARKER_PX,
    height: int = DEFAULT_MARKER_PX,
    snap: int = 1,
) -> tuple[int, int]:
    """Center a marker on the click and snap its origin to the base grid."""
    x = round((scene_x - width / 2) / snap) * snap
    y = round((scene_y - height / 2) / snap) * snap
    return max(0, int(x)), max(0, int(y))


def column_label(x: int) -> str:
    result = ""
    value = x + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def coordinate_for_pixel(x: int, y: int) -> str:
    return f"{column_label(x // BASE_GRID_PX)}{y // BASE_GRID_PX + 1}"


def covered_coordinates(marker: dict) -> list[str]:
    coordinates = []
    start_x = marker["x_px"] // BASE_GRID_PX
    start_y = marker["y_px"] // BASE_GRID_PX
    end_x = (
        marker["x_px"] + marker["width_px"] - 1
    ) // BASE_GRID_PX
    end_y = (
        marker["y_px"] + marker["height_px"] - 1
    ) // BASE_GRID_PX
    for y in range(start_y, end_y + 1):
        for x in range(start_x, end_x + 1):
            coordinates.append(f"{column_label(x)}{y + 1}")
    return coordinates


def original_image(folder: Path) -> Path:
    images = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if len(images) != 1:
        raise ValueError(
            f"{folder.name}: expected one source image, found {len(images)}"
        )
    return images[0]


class MarkerItem(QGraphicsRectItem):
    def __init__(self, editor: "CurationEditor", marker: dict):
        super().__init__(
            0,
            0,
            marker["width_px"],
            marker["height_px"],
        )
        self.editor = editor
        self.marker = marker
        self.setPos(marker["x_px"], marker["y_px"])
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(20)
        self.label = QGraphicsSimpleTextItem(marker["symbol"], self)
        self.label.setBrush(QColor("#ffffff"))
        self.label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._position_label()
        self._drag_start: tuple[int, int] | None = None
        self.refresh_style()

    def _position_label(self) -> None:
        bounds = self.label.boundingRect()
        self.label.setPos(
            (self.rect().width() - bounds.width()) / 2,
            (self.rect().height() - bounds.height()) / 2,
        )

    def refresh_style(self) -> None:
        color = QColor(self.marker["color"])
        fill = QColor(color)
        fill.setAlpha(52)
        self.setBrush(fill)
        self.setPen(QPen(color, 2))
        self.label.setText(self.marker["symbol"])
        self._position_label()

    def mousePressEvent(self, event) -> None:
        if not (
            event.modifiers()
            & Qt.KeyboardModifier.ControlModifier
        ):
            self.editor.scene.clearSelection()
        self._drag_start = (
            int(self.pos().x()),
            int(self.pos().y()),
        )
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        snap = max(1, int(self.marker.get("snap_px", 1)))
        x = round(self.pos().x() / snap) * snap
        y = round(self.pos().y() / snap) * snap
        x = max(0, min(x, self.editor.image_width - self.marker["width_px"]))
        y = max(0, min(y, self.editor.image_height - self.marker["height_px"]))
        self.setPos(x, y)
        self.marker["x_px"] = int(x)
        self.marker["y_px"] = int(y)
        super().mouseReleaseEvent(event)
        if self._drag_start != (int(x), int(y)):
            self.editor.commit_change()
        self.editor.update_selected_details()


class MapView(QGraphicsView):
    def __init__(self, editor: "CurationEditor"):
        super().__init__()
        self.editor = editor
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._panning = False
        self._pan_start = QPoint()

    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        current = self.transform().m11()
        if 0.12 <= current * factor <= 12:
            self.scale(factor, factor)
        self.editor.update_zoom_label()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            while item is not None and not isinstance(item, MarkerItem):
                item = item.parentItem()
            if item is None:
                scene_position = self.mapToScene(event.position().toPoint())
                self.editor.place_marker(scene_position)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton and self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        step = (
            16
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier
            else 8
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            else 1
        )
        movement = {
            Qt.Key.Key_Left: (-step, 0),
            Qt.Key.Key_Right: (step, 0),
            Qt.Key.Key_Up: (0, -step),
            Qt.Key.Key_Down: (0, step),
        }.get(event.key())
        if movement and self.editor.selected_marker_items():
            self.editor.nudge_selected(*movement)
            event.accept()
            return
        super().keyPressEvent(event)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if not self.editor.grid_checkbox.isChecked():
            return
        painter.save()
        minor = QPen(QColor(50, 210, 255, 92), 0)
        major = QPen(QColor(50, 210, 255, 165), 0)
        left = int(rect.left() // BASE_GRID_PX) * BASE_GRID_PX
        top = int(rect.top() // BASE_GRID_PX) * BASE_GRID_PX
        right = min(self.editor.image_width, int(rect.right()) + BASE_GRID_PX)
        bottom = min(self.editor.image_height, int(rect.bottom()) + BASE_GRID_PX)
        for x in range(max(0, left), right + 1, BASE_GRID_PX):
            painter.setPen(major if x % 32 == 0 else minor)
            painter.drawLine(x, max(0, top), x, bottom)
        for y in range(max(0, top), bottom + 1, BASE_GRID_PX):
            painter.setPen(major if y % 32 == 0 else minor)
            painter.drawLine(max(0, left), y, right, y)
        painter.restore()


class CurationEditor(QMainWindow):
    def __init__(self, root: Path, initial_dungeon: str | None = None):
        super().__init__()
        self.root = root
        self.dungeon_folder: Path | None = None
        self.source_image: Path | None = None
        self.image_width = 1
        self.image_height = 1
        self.markers: list[dict] = []
        self.marker_items: dict[str, MarkerItem] = {}
        self.legacy_items: list[QGraphicsItem] = []
        self.history: list[list[dict]] = []
        self.history_index = -1
        self.dirty = False
        self._loading = False

        self.setWindowTitle("Lufia II Dungeon Curation Editor")
        self.resize(1500, 950)
        self.scene = QGraphicsScene(self)
        self.view = MapView(self)
        self.view.setScene(self.scene)
        self._build_ui()
        self._populate_dungeons(initial_dungeon)

    def _build_ui(self) -> None:
        toolbar = QToolBar("Map controls", self)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel("Dungeon: "))
        self.dungeon_combo = QComboBox()
        self.dungeon_combo.currentTextChanged.connect(self.load_dungeon)
        toolbar.addWidget(self.dungeon_combo)
        toolbar.addSeparator()

        self.grid_checkbox = QCheckBox("16px grid")
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(
            lambda _checked: self.view.viewport().update()
        )
        toolbar.addWidget(self.grid_checkbox)

        self.legacy_checkbox = QCheckBox("legacy 16px annotations")
        self.legacy_checkbox.setChecked(False)
        self.legacy_checkbox.toggled.connect(self._set_legacy_visible)
        toolbar.addWidget(self.legacy_checkbox)

        fit_action = QAction("Fit map", self)
        fit_action.setShortcut(QKeySequence("F"))
        fit_action.triggered.connect(self.fit_map)
        toolbar.addAction(fit_action)

        self.zoom_label = QLabel(" 100% ")
        toolbar.addWidget(self.zoom_label)

        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.undo)
        toolbar.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.redo)
        toolbar.addAction(redo_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save)
        toolbar.addAction(save_action)

        export_action = QAction("Export preview", self)
        export_action.triggered.connect(self.export_preview)
        toolbar.addAction(export_action)

        delete_action = QAction("Delete selected", self)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_action.triggered.connect(self.delete_selected)
        self.addAction(delete_action)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("Marker type"))
        self.kind_list = QListWidget()
        for kind in MARKER_KINDS:
            item = QListWidgetItem(f"{kind.symbol}   {kind.name}")
            item.setData(Qt.ItemDataRole.UserRole, kind.name)
            item.setForeground(QColor(kind.color))
            self.kind_list.addItem(item)
        self.kind_list.setCurrentRow(0)
        self.kind_list.currentItemChanged.connect(self._kind_changed)
        side_layout.addWidget(self.kind_list)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Marker size"))
        self.size_combo = QComboBox()
        self.size_combo.addItem("16 × 16 tile", (16, 16))
        self.size_combo.addItem("32 × 32 body", (32, 32))
        self.size_combo.addItem("32 × 64 sprite", (32, 64))
        size_row.addWidget(self.size_combo)
        side_layout.addLayout(size_row)

        snap_row = QHBoxLayout()
        snap_row.addWidget(QLabel("Position snap"))
        self.snap_combo = QComboBox()
        self.snap_combo.addItem("1 px — precise", 1)
        self.snap_combo.addItem("8 px — SNES half-tile", 8)
        self.snap_combo.addItem("16 px — navigation grid", 16)
        self.snap_combo.currentIndexChanged.connect(self._snap_changed)
        snap_row.addWidget(self.snap_combo)
        side_layout.addLayout(snap_row)

        details = QFormLayout()
        self.traversal_combo = QComboBox()
        self.traversal_combo.addItems(
            [
                "blocked",
                "conditional",
                "confirmed_walkable",
                "unverified",
                "unknown",
            ]
        )
        self.action_edit = QLineEdit()
        self.notes_edit = QLineEdit()
        self.coverage_label = QLabel("No marker selected")
        self.coverage_label.setWordWrap(True)
        details.addRow("Traversal", self.traversal_combo)
        details.addRow("Required action", self.action_edit)
        details.addRow("Notes", self.notes_edit)
        details.addRow("Selection", self.coverage_label)
        side_layout.addLayout(details)

        apply_button = QPushButton("Apply details to selected")
        apply_button.clicked.connect(self.apply_selected_details)
        side_layout.addWidget(apply_button)

        import_button = QPushButton("Import visible legacy boxes as editable")
        import_button.clicked.connect(self.import_legacy_as_editable)
        side_layout.addWidget(import_button)

        delete_button = QPushButton("Delete selected")
        delete_button.clicked.connect(self.delete_selected)
        side_layout.addWidget(delete_button)
        side_layout.addStretch(1)

        splitter = QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([1250, 250])
        self.setCentralWidget(splitter)
        self.scene.selectionChanged.connect(self.update_selected_details)
        self.statusBar().showMessage(
            "Left click places a snapped marker. Drag markers to move. "
            "Right drag pans. Mouse wheel zooms. Arrow keys nudge 1 px; "
            "Shift+arrow 8 px; Ctrl+arrow 16 px."
        )

    def _populate_dungeons(self, initial: str | None) -> None:
        folders = sorted(
            folder.name
            for folder in self.root.iterdir()
            if folder.is_dir() and any(
                path.suffix.lower() in IMAGE_SUFFIXES
                for path in folder.iterdir()
                if path.is_file()
            )
        )
        self.dungeon_combo.blockSignals(True)
        self.dungeon_combo.addItems(folders)
        if initial in folders:
            self.dungeon_combo.setCurrentText(initial)
        self.dungeon_combo.blockSignals(False)
        if folders:
            self.load_dungeon(self.dungeon_combo.currentText())

    def marker_path(self) -> Path:
        assert self.dungeon_folder is not None
        return self.dungeon_folder / "curation_markers.json"

    def _maybe_save(self) -> bool:
        if not self.dirty:
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved markers",
            "Save marker changes before switching dungeon?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            self.save()
        return True

    def load_dungeon(self, dungeon: str) -> None:
        if self._loading or not dungeon:
            return
        if self.dungeon_folder is not None and not self._maybe_save():
            self.dungeon_combo.blockSignals(True)
            self.dungeon_combo.setCurrentText(self.dungeon_folder.name)
            self.dungeon_combo.blockSignals(False)
            return
        self._loading = True
        try:
            folder = self.root / dungeon
            source = original_image(folder)
            pixmap = QPixmap(str(source))
            if pixmap.isNull():
                raise ValueError(f"Could not load {source}")
            self.scene.clear()
            self.marker_items.clear()
            self.legacy_items.clear()
            self.dungeon_folder = folder
            self.source_image = source
            self.image_width = pixmap.width()
            self.image_height = pixmap.height()
            image_item = QGraphicsPixmapItem(pixmap)
            image_item.setZValue(0)
            self.scene.addItem(image_item)
            self.scene.setSceneRect(0, 0, self.image_width, self.image_height)
            self._load_legacy_annotations()
            self.markers = self._load_markers()
            self._rebuild_marker_items()
            self.history = []
            self.history_index = -1
            self._push_history()
            self.dirty = False
            self.fit_map()
            self.setWindowTitle(
                f"Lufia II Dungeon Curation Editor — {dungeon}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
        finally:
            self._loading = False

    def _load_markers(self) -> list[dict]:
        path = self.marker_path()
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != MARKER_SCHEMA:
            raise ValueError(f"Unsupported marker schema in {path}")
        return [dict(marker) for marker in payload.get("markers", [])]

    def _load_legacy_annotations(self) -> None:
        assert self.dungeon_folder is not None
        path = self.dungeon_folder / "annotations.json"
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        annotations = payload.get("annotations", {})
        for coordinate, annotation in annotations.items():
            letters = "".join(ch for ch in coordinate if ch.isalpha())
            digits = "".join(ch for ch in coordinate if ch.isdigit())
            x = 0
            for character in letters:
                x = x * 26 + ord(character) - ord("A") + 1
            x = (x - 1) * BASE_GRID_PX
            y = (int(digits) - 1) * BASE_GRID_PX
            kind = KIND_BY_NAME.get(
                (annotation.get("object") or "").lower(),
                KIND_BY_NAME["blocked"]
                if annotation.get("traversal") == "blocked"
                else KIND_BY_NAME["walkable"],
            )
            item = QGraphicsRectItem(x, y, 16, 16)
            color = QColor(kind.color)
            color.setAlpha(160)
            item.setPen(QPen(color, 1))
            item.setZValue(5)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setData(0, coordinate)
            item.setData(1, dict(annotation))
            self.scene.addItem(item)
            self.legacy_items.append(item)
        self._set_legacy_visible(self.legacy_checkbox.isChecked())

    def _set_legacy_visible(self, visible: bool) -> None:
        for item in self.legacy_items:
            item.setVisible(visible)

    def _snapshot(self) -> list[dict]:
        return [dict(marker) for marker in self.markers]

    def _push_history(self) -> None:
        snapshot = self._snapshot()
        self.history = self.history[: self.history_index + 1]
        self.history.append(snapshot)
        self.history_index += 1

    def commit_change(self) -> None:
        self._sync_item_positions()
        self._push_history()
        self.dirty = True

    def _sync_item_positions(self) -> None:
        for item in self.marker_items.values():
            item.marker["x_px"] = int(item.pos().x())
            item.marker["y_px"] = int(item.pos().y())

    def _restore_snapshot(self, snapshot: list[dict]) -> None:
        self.markers = [dict(marker) for marker in snapshot]
        self._rebuild_marker_items()
        self.dirty = True

    def undo(self) -> None:
        if self.history_index <= 0:
            return
        self.history_index -= 1
        self._restore_snapshot(self.history[self.history_index])

    def redo(self) -> None:
        if self.history_index + 1 >= len(self.history):
            return
        self.history_index += 1
        self._restore_snapshot(self.history[self.history_index])

    def _rebuild_marker_items(self) -> None:
        for item in list(self.marker_items.values()):
            self.scene.removeItem(item)
        self.marker_items.clear()
        for marker in self.markers:
            item = MarkerItem(self, marker)
            self.scene.addItem(item)
            self.marker_items[marker["id"]] = item

    def selected_kind(self) -> MarkerKind:
        item = self.kind_list.currentItem()
        name = item.data(Qt.ItemDataRole.UserRole) if item else "bush"
        return KIND_BY_NAME[name]

    def _kind_changed(self) -> None:
        kind = self.selected_kind()
        self.traversal_combo.setCurrentText(kind.default_traversal)
        self.action_edit.setText(kind.default_action)

    def _snap_changed(self, _index: int) -> None:
        selected = self.selected_marker_items()
        if not selected:
            return
        snap = self.snap_combo.currentData()
        changed = False
        for item in selected:
            if item.marker.get("snap_px", 1) != snap:
                item.marker["snap_px"] = snap
                changed = True
        if changed:
            self.commit_change()
            self.statusBar().showMessage(
                f"Snap changed to {snap}px for {len(selected)} selected marker(s)."
            )

    def place_marker(self, scene_position: QPointF) -> None:
        if not (
            0 <= scene_position.x() < self.image_width
            and 0 <= scene_position.y() < self.image_height
        ):
            return
        kind = self.selected_kind()
        width, height = self.size_combo.currentData()
        snap = self.snap_combo.currentData()
        x, y = snap_marker_origin(
            scene_position.x(),
            scene_position.y(),
            width,
            height,
            snap,
        )
        x = min(x, max(0, self.image_width - width))
        y = min(y, max(0, self.image_height - height))
        marker = {
            "id": uuid.uuid4().hex[:12],
            "type": kind.name,
            "symbol": kind.symbol,
            "color": kind.color,
            "x_px": x,
            "y_px": y,
            "width_px": width,
            "height_px": height,
            "snap_px": snap,
            "traversal": self.traversal_combo.currentText(),
            "required_action": self.action_edit.text().strip() or None,
            "notes": self.notes_edit.text().strip() or None,
            "source": "manual",
        }
        self.markers.append(marker)
        item = MarkerItem(self, marker)
        self.scene.addItem(item)
        self.marker_items[marker["id"]] = item
        self.scene.clearSelection()
        item.setSelected(True)
        self.commit_change()

    def selected_marker_items(self) -> list[MarkerItem]:
        return [
            item
            for item in self.scene.selectedItems()
            if isinstance(item, MarkerItem)
        ]

    def update_selected_details(self) -> None:
        selected = self.selected_marker_items()
        if not selected:
            self.coverage_label.setText("No marker selected")
            return
        marker = selected[0].marker
        snap_index = self.snap_combo.findData(marker.get("snap_px", 1))
        if snap_index >= 0:
            self.snap_combo.blockSignals(True)
            self.snap_combo.setCurrentIndex(snap_index)
            self.snap_combo.blockSignals(False)
        self.traversal_combo.setCurrentText(marker["traversal"])
        self.action_edit.setText(marker.get("required_action") or "")
        self.notes_edit.setText(marker.get("notes") or "")
        coordinates = covered_coordinates(marker)
        self.coverage_label.setText(
            f"{marker['type']} at {marker['x_px']},{marker['y_px']} px\n"
            f"covers {', '.join(coordinates)}"
        )

    def apply_selected_details(self) -> None:
        selected = self.selected_marker_items()
        if not selected:
            return
        for item in selected:
            item.marker["traversal"] = self.traversal_combo.currentText()
            item.marker["required_action"] = (
                self.action_edit.text().strip() or None
            )
            item.marker["notes"] = self.notes_edit.text().strip() or None
            item.marker["snap_px"] = self.snap_combo.currentData()
        self.commit_change()
        self.update_selected_details()

    def import_legacy_as_editable(self) -> None:
        existing_coordinates = {
            marker.get("legacy_coordinate")
            for marker in self.markers
            if marker.get("legacy_coordinate")
        }
        imported = 0
        for legacy_item in self.legacy_items:
            coordinate = legacy_item.data(0)
            annotation = legacy_item.data(1) or {}
            if coordinate in existing_coordinates:
                continue
            object_type = (annotation.get("object") or "").lower()
            kind = KIND_BY_NAME.get(
                object_type,
                KIND_BY_NAME["blocked"]
                if annotation.get("traversal") == "blocked"
                else KIND_BY_NAME["walkable"],
            )
            rectangle = legacy_item.rect()
            marker = {
                "id": uuid.uuid4().hex[:12],
                "type": kind.name,
                "symbol": kind.symbol,
                "color": kind.color,
                "x_px": int(rectangle.x()),
                "y_px": int(rectangle.y()),
                "width_px": 16,
                "height_px": 16,
                "snap_px": self.snap_combo.currentData(),
                "traversal": annotation.get("traversal", kind.default_traversal),
                "required_action": annotation.get("required_action"),
                "notes": annotation.get("notes"),
                "source": "legacy_import",
                "legacy_coordinate": coordinate,
            }
            self.markers.append(marker)
            imported += 1
        if imported:
            self._rebuild_marker_items()
            self.commit_change()
        self.legacy_checkbox.setChecked(False)
        self.statusBar().showMessage(
            f"Imported {imported} legacy boxes as editable 16x16 markers."
        )

    def nudge_selected(self, dx: int, dy: int) -> None:
        selected = self.selected_marker_items()
        if not selected:
            return
        for item in selected:
            marker = item.marker
            x = max(
                0,
                min(
                    int(item.pos().x()) + dx,
                    self.image_width - marker["width_px"],
                ),
            )
            y = max(
                0,
                min(
                    int(item.pos().y()) + dy,
                    self.image_height - marker["height_px"],
                ),
            )
            item.setPos(x, y)
            marker["x_px"] = x
            marker["y_px"] = y
        self.commit_change()
        self.update_selected_details()

    def delete_selected(self) -> None:
        selected = self.selected_marker_items()
        if not selected:
            return
        ids = {item.marker["id"] for item in selected}
        self.markers = [
            marker for marker in self.markers if marker["id"] not in ids
        ]
        self._rebuild_marker_items()
        self.commit_change()

    def fit_map(self) -> None:
        self.view.fitInView(
            self.scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self.update_zoom_label()

    def update_zoom_label(self) -> None:
        self.zoom_label.setText(
            f" {self.view.transform().m11() * 100:.0f}% "
        )

    def save(self) -> None:
        if self.dungeon_folder is None or self.source_image is None:
            return
        self._sync_item_positions()
        payload = {
            "schema": MARKER_SCHEMA,
            "dungeon": self.dungeon_folder.name,
            "source_image": self.source_image.name,
            "base_grid_px": BASE_GRID_PX,
            "default_marker_size_px": {
                "width": DEFAULT_MARKER_PX,
                "height": DEFAULT_MARKER_PX,
            },
            "coordinate_semantics": {
                "marker_box": "visual/semantic footprint",
                "base_grid": "16x16 feet-anchor navigation reference",
                "snap": "marker origin uses per-marker 1, 8 or 16-pixel snap",
            },
            "markers": self._snapshot(),
        }
        path = self.marker_path()
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        self.dirty = False
        self.statusBar().showMessage(f"Saved {len(self.markers)} markers to {path}")

    def export_preview(self) -> None:
        if self.dungeon_folder is None or self.source_image is None:
            return
        self._sync_item_positions()
        image = Image.open(self.source_image).convert("RGBA")
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        for x in range(0, image.width + 1, BASE_GRID_PX):
            alpha = 105 if x % 32 == 0 else 52
            draw.line((x, 0, x, image.height), fill=(50, 210, 255, alpha))
        for y in range(0, image.height + 1, BASE_GRID_PX):
            alpha = 105 if y % 32 == 0 else 52
            draw.line((0, y, image.width, y), fill=(50, 210, 255, alpha))
        try:
            font = ImageFont.truetype("arial.ttf", 13)
        except OSError:
            font = ImageFont.load_default()
        for marker in self.markers:
            color = QColor(marker["color"])
            rgba = (color.red(), color.green(), color.blue(), 72)
            outline = (color.red(), color.green(), color.blue(), 255)
            x = marker["x_px"]
            y = marker["y_px"]
            right = x + marker["width_px"] - 1
            bottom = y + marker["height_px"] - 1
            draw.rectangle((x, y, right, bottom), fill=rgba, outline=outline, width=2)
            draw.text(
                ((x + right) / 2, (y + bottom) / 2),
                marker["symbol"],
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
                anchor="mm",
            )
        output = self.dungeon_folder / "navigation" / "manual_curation_preview.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.alpha_composite(image, overlay).convert("RGB").save(output)
        self.statusBar().showMessage(f"Exported preview to {output}")

    def closeEvent(self, event) -> None:
        if self._maybe_save():
            event.accept()
        else:
            event.ignore()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open the Lufia II point-and-click dungeon curation editor."
    )
    parser.add_argument(
        "--root",
        default="emulator/maps/Dungeons",
        help="Dungeon map root.",
    )
    parser.add_argument(
        "--dungeon",
        default="Cave_to_Sundletan",
        help="Initially selected dungeon folder.",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    editor = CurationEditor(Path(args.root), args.dungeon)
    editor.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
