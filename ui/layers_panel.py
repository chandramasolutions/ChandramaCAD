from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QInputDialog, QColorDialog, QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from core.document import Document, Layer


class LayersPanel(QWidget):
    layer_changed = Signal()

    def __init__(self, document: Document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title = QLabel("LAYERS")
        title.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #8A8A9A; "
            "letter-spacing: 1px; padding-bottom: 2px;"
        )
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setFixedHeight(160)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemDoubleClicked.connect(self._on_rename)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._btn_add = QPushButton("+")
        self._btn_add.setFixedSize(28, 28)
        self._btn_add.setToolTip("Add layer")
        self._btn_add.clicked.connect(self._on_add)
        self._btn_add.setProperty("secondary", "true")

        self._btn_del = QPushButton("−")
        self._btn_del.setFixedSize(28, 28)
        self._btn_del.setToolTip("Delete layer")
        self._btn_del.clicked.connect(self._on_delete)
        self._btn_del.setProperty("outlined", "true")

        self._btn_color = QPushButton("⬛")
        self._btn_color.setFixedSize(28, 28)
        self._btn_color.setToolTip("Layer colour")
        self._btn_color.clicked.connect(self._on_color)
        self._btn_color.setProperty("outlined", "true")

        self._btn_vis = QPushButton("👁")
        self._btn_vis.setFixedSize(28, 28)
        self._btn_vis.setToolTip("Toggle visibility")
        self._btn_vis.clicked.connect(self._on_toggle_vis)
        self._btn_vis.setProperty("outlined", "true")

        for b in (self._btn_add, self._btn_del, self._btn_color, self._btn_vis):
            b.style().polish(b)
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        self._list.clear()
        for layer in self.document.layers:
            item = QListWidgetItem()
            vis_icon = "○" if not layer.visible else "●"
            item.setText(f"{vis_icon}  {layer.name}")
            item.setData(Qt.UserRole, layer.name)

            px = QPixmap(14, 14)
            px.fill(QColor(layer.color))
            item.setIcon(QIcon(px))

            if layer.name == self.document.active_layer:
                item.setForeground(QColor("#E55A28"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            if not layer.visible:
                item.setForeground(QColor("#AAAAAA"))

            self._list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        self.document.active_layer = name
        self.refresh()
        self.layer_changed.emit()

    def _on_rename(self, item: QListWidgetItem):
        old_name = item.data(Qt.UserRole)
        new_name, ok = QInputDialog.getText(
            self, "Rename Layer", "New name:", text=old_name
        )
        if ok and new_name and new_name != old_name:
            if not self.document.rename_layer(old_name, new_name):
                QMessageBox.warning(self, "Error", f"Layer '{new_name}' already exists.")
            self.refresh()
            self.layer_changed.emit()

    def _on_add(self):
        name, ok = QInputDialog.getText(self, "New Layer", "Layer name:")
        if ok and name:
            self.document.add_layer(name)
            self.document.active_layer = name
            self.refresh()
            self.layer_changed.emit()

    def _on_delete(self):
        item = self._list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        if name == "Default":
            QMessageBox.information(self, "Info", "Cannot delete the Default layer.")
            return
        reply = QMessageBox.question(
            self, "Delete Layer",
            f"Delete layer '{name}' and all its entities?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.document.remove_layer(name)
            self.refresh()
            self.layer_changed.emit()

    def _on_color(self):
        item = self._list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        layer = self.document.get_layer(name)
        if not layer:
            return
        color = QColorDialog.getColor(QColor(layer.color), self, "Layer Colour")
        if color.isValid():
            self.document.set_layer_color(name, color.name())
            self.refresh()
            self.layer_changed.emit()

    def _on_toggle_vis(self):
        item = self._list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        self.document.toggle_layer_visibility(name)
        self.refresh()
        self.layer_changed.emit()
