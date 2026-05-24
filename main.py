from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import sys
from chandrama_theme import get_stylesheet
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ChandramaCAD")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Chandrama Solutions")
    app.setOrganizationDomain("chandramasolutions.com")
    app.setStyleSheet(get_stylesheet())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
