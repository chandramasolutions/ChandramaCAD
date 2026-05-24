from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About ChandramaCAD")
        self.setFixedSize(400, 300)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 24)
        layout.setSpacing(10)

        # Brand header
        header = QHBoxLayout()
        diamond = QLabel("◆")
        diamond.setStyleSheet("color: #E55A28; font-size: 28px; font-weight: bold;")
        company_a = QLabel("CHANDRAMA")
        company_a.setStyleSheet("color: #E55A28; font-size: 22px; font-weight: bold;")
        company_b = QLabel(" CAD")
        company_b.setStyleSheet("color: #1A1A24; font-size: 22px; font-weight: 300;")
        header.addWidget(diamond)
        header.addSpacing(6)
        header.addWidget(company_a)
        header.addWidget(company_b)
        header.addStretch()
        layout.addLayout(header)

        layout.addSpacing(8)

        # Version
        ver_lbl = QLabel("Version 1.0.0")
        ver_lbl.setStyleSheet("color: #5A5A6A; font-size: 13px;")
        layout.addWidget(ver_lbl)

        # Description
        desc = QLabel(
            "Professional 2D CAD for 4-axis hotwire foam cutting.\n"
            "Part of the Chandrama three-app ecosystem:\n"
            "ChandramaCAD → ChandramaGCODE → ChandramaGRBL"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #5A5A6A; font-size: 12px; line-height: 1.5;")
        layout.addWidget(desc)

        layout.addSpacing(8)

        # Company
        company_lbl = QLabel("© 2024 Chandrama Solutions")
        company_lbl.setStyleSheet("color: #8A8A9A; font-size: 12px;")
        layout.addWidget(company_lbl)

        web_lbl = QLabel("chandramasolutions.com")
        web_lbl.setStyleSheet("color: #E55A28; font-size: 12px;")
        layout.addWidget(web_lbl)

        layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
