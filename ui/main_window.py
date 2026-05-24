from __future__ import annotations
import os
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QSplitter, QStatusBar, QMenuBar, QMenu,
    QToolButton, QFileDialog, QMessageBox, QFrame,
    QSizePolicy, QDialog, QFormLayout, QDoubleSpinBox,
    QPushButton,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeySequence, QAction, QFont, QShortcut, QPixmap

from core.document import Document
from core.snap_engine import SnapEngine
from core.exporter import export_dxf, export_dat
from ui.canvas import (
    Canvas,
    TOOL_SELECT, TOOL_LINE, TOOL_POLYLINE, TOOL_RECTANGLE,
    TOOL_CIRCLE, TOOL_ARC, TOOL_SPLINE,
    TOOL_POLYGON, TOOL_ELLIPSE, TOOL_SEMICIRCLE, TOOL_GROOVE,
    TOOL_POINT,
    TOOL_MOVE, TOOL_COPY_TOOL, TOOL_ROTATE, TOOL_MIRROR,
    TOOL_OFFSET, TOOL_TRIM, TOOL_EXTEND,
    TOOL_FILLET, TOOL_CHAMFER, TOOL_BREAK,
    TOOL_TEXT, TOOL_DIM_LINEAR, TOOL_DIM_RADIAL,
)
from ui.toolbar_panel import ToolbarPanel
from ui.layers_panel import LayersPanel
from ui.properties_panel import PropertiesPanel
from ui.about_dialog import AboutDialog
from ui.scale_dialog import ScaleDialog
from ui.array_dialog import ArrayDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChandramaCAD")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        self.document = Document()
        self.snap_engine = SnapEngine()
        self._project_path: str | None = None

        self._build_ui()
        self._build_menus()
        self._build_shortcuts()
        self._wire_signals()
        self._update_title()

    # ── UI Construction ──────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top brand bar ────────────────────────────────
        top_bar = self._build_top_bar()
        root.addWidget(top_bar)

        # ── Horizontal toolbar (full-width, above canvas) ────
        self.toolbar_panel = ToolbarPanel()
        root.addWidget(self.toolbar_panel)

        # ── Horizontal splitter: canvas | right panel ────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        self.canvas = Canvas(self.document, self.snap_engine)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.addWidget(self.canvas)

        # Right panel: layers + properties stacked vertically
        right_panel = QWidget()
        right_panel.setFixedWidth(220)
        right_panel.setStyleSheet("background: #F8F9FA; border-left: 1px solid #E0E0E0;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.layers_panel = LayersPanel(self.document)
        right_layout.addWidget(self.layers_panel)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E0E0E0;")
        right_layout.addWidget(sep)

        self.properties_panel = PropertiesPanel()
        right_layout.addWidget(self.properties_panel)
        right_layout.addStretch()

        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)   # canvas expands
        splitter.setStretchFactor(1, 0)   # right panel fixed

        root.addWidget(splitter)

        # ── Status bar ───────────────────────────────────
        self._build_status_bar()

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setStyleSheet(
            "background: #FFFFFF; border-bottom: 1px solid #E0E0E0;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        # ◆ CHANDRAMA CAD branding
        diamond = QLabel("◆")
        diamond.setStyleSheet("color: #E55A28; font-size: 16px; font-weight: bold; padding-right: 4px;")
        company_a = QLabel("CHANDRAMA")
        company_a.setStyleSheet("color: #E55A28; font-size: 15px; font-weight: bold; letter-spacing: 1px;")
        company_b = QLabel(" CAD")
        company_b.setStyleSheet("color: #1A1A24; font-size: 15px; font-weight: 300; letter-spacing: 2px;")

        layout.addWidget(diamond)
        layout.addWidget(company_a)
        layout.addWidget(company_b)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #E0E0E0; margin: 8px 12px;")
        layout.addWidget(sep)

        # File menu button
        self._btn_file = self._menu_button("File")
        layout.addWidget(self._btn_file)

        # Help menu button
        self._btn_help = self._menu_button("Help")
        layout.addWidget(self._btn_help)

        layout.addStretch()
        return bar

    def _menu_button(self, text: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setStyleSheet(
            "QToolButton { background: transparent; color: #1A1A24; "
            "font-size: 13px; padding: 4px 10px; border-radius: 4px; }"
            "QToolButton:hover { background: #F0F2F5; color: #E55A28; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        return btn

    def _build_status_bar(self):
        self._status = QStatusBar()
        self._status.setStyleSheet(
            "QStatusBar { background: #F0F2F5; border-top: 1px solid #E0E0E0; "
            "color: #5A5A6A; font-size: 12px; padding: 2px 8px; }"
        )
        self.setStatusBar(self._status)

        self._lbl_tool = QLabel("Tool: Select")
        self._lbl_cursor = QLabel("X: 0.000   Y: 0.000 mm")
        self._lbl_snap = QLabel("Snap: Grid")
        self._lbl_zoom = QLabel("Zoom: 100%")
        self._lbl_layer = QLabel(f"Layer: {self.document.active_layer}")

        for lbl in (self._lbl_tool, self._lbl_cursor, self._lbl_snap,
                    self._lbl_zoom, self._lbl_layer):
            lbl.setStyleSheet("padding: 0 10px; border-right: 1px solid #E0E0E0;")
            self._status.addWidget(lbl)

        brand = QLabel("◆ ChandramaCAD v1.0")
        brand.setStyleSheet("color: #E55A28; font-size: 12px; font-weight: 600; padding: 0 10px;")
        self._status.addPermanentWidget(brand)

    # ── Menus ─────────────────────────────────────────────

    def _build_menus(self):
        # File menu
        file_menu = QMenu("File", self)
        file_menu.setStyleSheet(self._menu_style())

        self._act_new = QAction("New Project", self)
        self._act_new.setShortcut(QKeySequence("Ctrl+N"))
        self._act_open = QAction("Open Project…", self)
        self._act_open.setShortcut(QKeySequence("Ctrl+O"))
        self._act_save = QAction("Save Project", self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save_as = QAction("Save Project As…", self)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_export_dxf = QAction("Export DXF…", self)
        self._act_export_dxf.setShortcut(QKeySequence("Ctrl+E"))
        self._act_export_dat = QAction("Export DAT…", self)
        self._act_insert_image = QAction("Insert Image…", self)
        self._act_insert_image.setShortcut(QKeySequence("Ctrl+I"))
        self._act_exit = QAction("Exit", self)
        self._act_exit.setShortcut(QKeySequence("Alt+F4"))

        file_menu.addAction(self._act_new)
        file_menu.addAction(self._act_open)
        file_menu.addSeparator()
        file_menu.addAction(self._act_save)
        file_menu.addAction(self._act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self._act_export_dxf)
        file_menu.addAction(self._act_export_dat)
        file_menu.addSeparator()
        file_menu.addAction(self._act_insert_image)
        file_menu.addSeparator()
        file_menu.addAction(self._act_exit)

        self._btn_file.setMenu(file_menu)

        # Help menu
        help_menu = QMenu("Help", self)
        help_menu.setStyleSheet(self._menu_style())
        self._act_about = QAction("About ChandramaCAD", self)
        help_menu.addAction(self._act_about)
        self._btn_help.setMenu(help_menu)

        # Wire file actions
        self._act_new.triggered.connect(self._on_new)
        self._act_open.triggered.connect(self._on_open)
        self._act_save.triggered.connect(self._on_save)
        self._act_save_as.triggered.connect(self._on_save_as)
        self._act_export_dxf.triggered.connect(self._on_export_dxf)
        self._act_export_dat.triggered.connect(self._on_export_dat)
        self._act_insert_image.triggered.connect(self._on_insert_image)
        self._act_exit.triggered.connect(self.close)
        self._act_about.triggered.connect(self._on_about)

    def _menu_style(self) -> str:
        return (
            "QMenu { background: #FFFFFF; border: 1px solid #E0E0E0; "
            "border-radius: 6px; padding: 4px 0; }"
            "QMenu::item { padding: 6px 20px 6px 12px; color: #1A1A24; }"
            "QMenu::item:selected { background: #F0F2F5; color: #E55A28; }"
            "QMenu::separator { height: 1px; background: #E0E0E0; margin: 4px 8px; }"
        )

    # ── Keyboard shortcuts ────────────────────────────────

    def _build_shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(fn)
            return s

        sc("Escape",   lambda: self._select_tool(TOOL_SELECT))
        sc("L",        lambda: self._select_tool(TOOL_LINE))
        sc("P",        lambda: self._select_tool(TOOL_POLYLINE))
        sc("R",        lambda: self._select_tool(TOOL_RECTANGLE))
        sc("C",        lambda: self._select_tool(TOOL_CIRCLE))
        sc("A",        lambda: self._select_tool(TOOL_ARC))
        sc("E",        lambda: self._select_tool(TOOL_ELLIPSE))
        sc("Ctrl+Z",    self._on_undo)
        sc("Ctrl+Y",    self._on_redo)
        sc("Delete",    self._on_delete_selected)
        sc("G",         self._toggle_grid)
        sc("S",         self._toggle_snap)
        sc("F",         self.canvas.fit_to_screen)
        sc("+",         self._zoom_in)
        sc("-",         self._zoom_out)
        sc("Alt+S",     self._on_scale_selection)
        sc("Ctrl+I",    self._on_insert_image)
        # Drawing
        sc(".",         lambda: self._select_tool(TOOL_POINT))
        # Modify
        sc("M",         lambda: self._select_tool(TOOL_MOVE))
        sc("Ctrl+D",    lambda: self._select_tool(TOOL_COPY_TOOL))
        sc("Q",         lambda: self._select_tool(TOOL_ROTATE))
        sc("I",         lambda: self._select_tool(TOOL_MIRROR))
        sc("O",         lambda: self._select_tool(TOOL_OFFSET))
        sc("T",         lambda: self._select_tool(TOOL_TRIM))
        sc("X",         lambda: self._select_tool(TOOL_EXTEND))
        sc("N",         lambda: self._select_tool(TOOL_FILLET))
        sc("H",         lambda: self._select_tool(TOOL_CHAMFER))
        sc("B",         lambda: self._select_tool(TOOL_BREAK))
        # Array / Hotwire
        sc("Y",         lambda: self._select_tool("array_rect"))
        sc("U",         lambda: self._select_tool("array_circ"))
        sc("J",         lambda: self._select_tool("join"))
        sc("V",         lambda: self._select_tool("reverse"))
        sc("K",         lambda: self._select_tool("to_poly"))
        # Annotation
        sc("Ctrl+T",    lambda: self._select_tool(TOOL_TEXT))
        sc("D",         lambda: self._select_tool(TOOL_DIM_LINEAR))
        sc("Shift+D",   lambda: self._select_tool(TOOL_DIM_RADIAL))

    # ── Signal wiring ─────────────────────────────────────

    def _wire_signals(self):
        self.toolbar_panel.tool_selected.connect(self._select_tool)
        self.toolbar_panel.polygon_sides.connect(self.canvas.set_polygon_sides)
        self.toolbar_panel.zoom_in_clicked.connect(self._zoom_in)
        self.toolbar_panel.zoom_out_clicked.connect(self._zoom_out)
        self.toolbar_panel.fit_clicked.connect(self.canvas.fit_to_screen)
        self.toolbar_panel.scale_clicked.connect(self._on_scale_selection)

        self.canvas.cursor_moved.connect(self._on_cursor_moved)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        self.canvas.selection_changed.connect(self._on_selection_changed)
        self.canvas.entity_added.connect(self._on_entity_added)
        self.canvas.tool_changed.connect(self._on_tool_changed)

        self.layers_panel.layer_changed.connect(self._on_layer_changed)

    # ── Actions ───────────────────────────────────────────

    def _select_tool(self, tool: str):
        # Instant operations — don't change the canvas tool mode
        if tool == "join":
            self.canvas.op_join(); return
        elif tool == "reverse":
            self.canvas.op_reverse(); return
        elif tool == "to_poly":
            self.canvas.op_to_polyline(); return
        elif tool == "array_rect":
            self._on_array_rect(); return
        elif tool == "array_circ":
            self._on_array_circ(); return
        # Interactive tool selection
        self.canvas.set_tool(tool)
        self.toolbar_panel.set_active_tool(tool)
        tool_name = tool.replace("_", " ").title()
        self._lbl_tool.setText(f"Tool: {tool_name}")

    def _on_cursor_moved(self, x: float, y: float):
        self._lbl_cursor.setText(f"X: {x:.3f}   Y: {y:.3f} mm")
        snap = self.canvas._snap_result
        if snap:
            self._lbl_snap.setText(f"Snap: {snap.snap_type.title()}")

    def _on_zoom_changed(self, scale: float):
        pct = scale / 5.0 * 100
        self._lbl_zoom.setText(f"Zoom: {pct:.0f}%")

    def _on_selection_changed(self, entities):
        self.properties_panel.show_entities(entities)

    def _on_entity_added(self, entity):
        self.layers_panel.refresh()
        self._update_title()

    def _on_tool_changed(self, tool: str):
        self._lbl_tool.setText(f"Tool: {tool.replace('_', ' ').title()}")

    def _on_layer_changed(self):
        self.document.active_layer = self.layers_panel.document.active_layer
        self._lbl_layer.setText(f"Layer: {self.document.active_layer}")
        self.canvas.update()

    def _on_undo(self):
        if self.document.undo():
            self.canvas.update()
            self.layers_panel.refresh()
            self.properties_panel.show_entities([])
            self._update_title()

    def _on_redo(self):
        if self.document.redo():
            self.canvas.update()
            self.layers_panel.refresh()
            self.properties_panel.show_entities([])
            self._update_title()

    def _on_delete_selected(self):
        self.canvas.remove_selected_images()
        selected = self.document.selected_entities()
        if selected:
            ids = [e.id for e in selected]
            self.document.remove_entities(ids)
            self.properties_panel.show_entities([])
            self._update_title()
        self.canvas.update()

    def _toggle_grid(self):
        self.canvas.grid_visible = not self.canvas.grid_visible
        self.canvas.update()

    def _toggle_snap(self):
        self.snap_engine.grid_snap_enabled = not self.snap_engine.grid_snap_enabled
        self.snap_engine.endpoint_snap_enabled = self.snap_engine.grid_snap_enabled
        status = "On" if self.snap_engine.grid_snap_enabled else "Off"
        self._lbl_snap.setText(f"Snap: {status}")

    def _zoom_in(self):
        self.canvas._scale = min(200.0, self.canvas._scale * 1.25)
        self.canvas.zoom_changed.emit(self.canvas._scale)
        self.canvas.update()

    def _zoom_out(self):
        self.canvas._scale = max(0.1, self.canvas._scale / 1.25)
        self.canvas.zoom_changed.emit(self.canvas._scale)
        self.canvas.update()

    # ── File operations ───────────────────────────────────

    def _check_save(self) -> bool:
        if not self.document.is_modified:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "Save changes before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            return self._on_save()
        elif reply == QMessageBox.Discard:
            return True
        return False

    def _on_new(self):
        if not self._check_save():
            return
        self.document = Document()
        self.snap_engine = SnapEngine()
        self.canvas.document = self.document
        self.canvas.snap_engine = self.snap_engine
        self.canvas._images.clear()
        self.layers_panel.document = self.document
        self.layers_panel.refresh()
        self.properties_panel.show_entities([])
        self._project_path = None
        self.canvas.center_origin()
        self._update_title()

    def _on_open(self):
        if not self._check_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "ChandramaCAD Project (*.cad);;All Files (*)"
        )
        if not path:
            return
        try:
            self.document = Document.load_from_file(path)
            self.canvas.document = self.document
            self.layers_panel.document = self.document
            self.layers_panel.refresh()
            self.properties_panel.show_entities([])
            self._project_path = path
            self.canvas.fit_to_screen()
            self._update_title()
        except Exception as ex:
            QMessageBox.critical(self, "Open Error", str(ex))

    def _on_save(self) -> bool:
        if self._project_path:
            try:
                self.document.save_to_file(self._project_path)
                self._update_title()
                return True
            except Exception as ex:
                QMessageBox.critical(self, "Save Error", str(ex))
                return False
        return self._on_save_as()

    def _on_save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "", "ChandramaCAD Project (*.cad);;All Files (*)"
        )
        if not path:
            return False
        if not path.endswith(".cad"):
            path += ".cad"
        try:
            self.document.save_to_file(path)
            self._project_path = path
            self._update_title()
            return True
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))
            return False

    def _on_export_dxf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DXF", "", "DXF Files (*.dxf);;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(".dxf"):
            path += ".dxf"
        try:
            export_dxf(self.document, path)
            QMessageBox.information(self, "Export Complete",
                                    f"DXF exported to:\n{path}")
        except Exception as ex:
            QMessageBox.critical(self, "Export Error", str(ex))

    def _on_export_dat(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DAT (Airfoil)", "", "DAT Files (*.dat);;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(".dat"):
            path += ".dat"
        try:
            export_dat(self.document, path)
            QMessageBox.information(self, "Export Complete",
                                    f"DAT exported to:\n{path}")
        except Exception as ex:
            QMessageBox.critical(self, "Export Error", str(ex))

    def _on_array_rect(self):
        if not self.document.selected_entities():
            QMessageBox.information(self, "Array", "Select entities first, then run Array.")
            return
        dlg = ArrayDialog(self)
        dlg._tabs.setCurrentIndex(0)
        if dlg.exec() != QDialog.Accepted:
            return
        self.canvas.op_array_rect(
            dlg.rows, dlg.cols,
            dlg.row_spacing, dlg.col_spacing,
            dlg.array_angle,
        )
        self.layers_panel.refresh()
        self._update_title()

    def _on_array_circ(self):
        if not self.document.selected_entities():
            QMessageBox.information(self, "Array", "Select entities first, then run Array.")
            return
        dlg = ArrayDialog(self)
        dlg._tabs.setCurrentIndex(1)
        if dlg.exec() != QDialog.Accepted:
            return
        center = np.array([dlg.center_x, dlg.center_y])
        self.canvas.op_array_circ(
            dlg.count, center, dlg.fill_angle, dlg.rotate_items
        )
        self.layers_panel.refresh()
        self._update_title()

    def _on_insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Reference Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All Files (*)"
        )
        if not path:
            return

        # Check the image loads correctly
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.critical(self, "Image Error", f"Cannot load image:\n{path}")
            return

        # Ask for real-world width and opacity
        dlg = QDialog(self)
        dlg.setWindowTitle("Image Scale & Opacity")
        dlg.setModal(True)
        dlg.setMinimumWidth(280)
        dlg.setStyleSheet(
            "QDialog { background: #F8F9FA; }"
            "QLabel { color: #1A1A24; font-size: 13px; }"
            "QDoubleSpinBox { background: #FFFFFF; border: 1px solid #E0E0E0; "
            "border-radius: 3px; padding: 4px 8px; font-size: 13px; color: #1A1A24; }"
        )
        form = QFormLayout(dlg)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        width_spin = QDoubleSpinBox()
        width_spin.setRange(0.1, 100000.0)
        width_spin.setDecimals(2)
        width_spin.setValue(100.0)
        width_spin.setSuffix(" mm")
        form.addRow("Real width:", width_spin)

        opacity_spin = QDoubleSpinBox()
        opacity_spin.setRange(0.05, 1.0)
        opacity_spin.setDecimals(2)
        opacity_spin.setSingleStep(0.05)
        opacity_spin.setValue(0.5)
        form.addRow("Opacity:", opacity_spin)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("Insert")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            "QPushButton { background: #E55A28; color: #FFFFFF; border: none; "
            "border-radius: 4px; padding: 6px 18px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #CC4D22; }"
        )
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #1A1A24; border: 1px solid #E0E0E0; "
            "border-radius: 4px; padding: 6px 18px; font-size: 13px; }"
            "QPushButton:hover { background: #F0F2F5; }"
        )
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        form.addRow(btn_row)

        if dlg.exec() != QDialog.Accepted:
            return

        real_w_mm = width_spin.value()
        opacity   = opacity_spin.value()

        # Compute height preserving aspect ratio
        aspect    = pix.height() / max(pix.width(), 1)
        real_h_mm = real_w_mm * aspect

        # Place image centred at world origin (top-left = (-w/2, h/2))
        world_x = -real_w_mm / 2.0
        world_y =  real_h_mm / 2.0

        try:
            self.canvas.add_image(path, world_x, world_y, real_w_mm, real_h_mm, opacity)
        except ValueError as ex:
            QMessageBox.critical(self, "Image Error", str(ex))

    def _on_scale_selection(self):
        selected = self.document.selected_entities()
        has_sel  = bool(selected)
        dlg = ScaleDialog(has_selection=has_sel, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        factor = dlg.factor
        if factor == 1.0:
            return

        if not selected:
            QMessageBox.information(self, "Scale", "No entities selected. Select entities first.")
            return

        # Compute pivot
        if dlg.pivot_is_selection_center:
            all_pts = []
            for e in selected:
                bb = e.bounding_box()
                if bb is not None:
                    (x0, y0), (x1, y1) = bb
                    all_pts.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
            if all_pts:
                cx = sum(p[0] for p in all_pts) / len(all_pts)
                cy = sum(p[1] for p in all_pts) / len(all_pts)
                pivot = np.array([cx, cy])
            else:
                pivot = np.array([0.0, 0.0])
        else:
            pivot = np.array([0.0, 0.0])

        snap = self.document.begin_operation()
        for e in selected:
            e.scale(factor, pivot)
        self.document.commit_operation(snap)

        self.canvas.update()
        self.properties_panel.show_entities(selected)
        self._update_title()

    def _on_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def _update_title(self):
        name = os.path.basename(self._project_path) if self._project_path else "Untitled"
        mod = " *" if self.document.is_modified else ""
        self.setWindowTitle(f"ChandramaCAD — {name}{mod}")

    # ── Close guard ───────────────────────────────────────

    def closeEvent(self, event):
        if self._check_save():
            event.accept()
        else:
            event.ignore()
