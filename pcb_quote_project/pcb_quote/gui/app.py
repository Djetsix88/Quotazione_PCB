import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor

from .main_window import MainWindow
from .styles import STYLE


def apply_palette(app: QApplication):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f7f9fb"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Text, QColor("#2c3e50"))
    palette.setColor(QPalette.Button, QColor("#6ea8fe"))
    palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor("#5b8def"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_palette(app)
    app.setStyleSheet(STYLE)

    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()