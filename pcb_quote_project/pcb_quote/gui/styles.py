STYLE = """
QWidget {
    background: #f7f9fb;
    color: #2c3e50;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial;
    font-size: 10.5pt;
}

QGroupBox {
    border: 1px solid #d9e2ec;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #3a4a5a;
    font-weight: 600;
    background: transparent;
}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTableWidget, QPlainTextEdit {
    border: 1px solid #cbd6e2;
    border-radius: 6px;
    padding: 6px;
    background: #ffffff;
    selection-background-color: #e1efff;
}

QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QTableWidget:focus, QPlainTextEdit:focus {
    border: 1px solid #5b8def;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #6ea8fe, stop:1 #4d8ef7);
    color: white;
    border: 1px solid #4d8ef7;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #5b9bff; }
QPushButton:pressed { background: #4d8ef7; }

QTabWidget::pane {
    border: 1px solid #d9e2ec;
    border-radius: 8px;
    padding: 6px;
    background: #ffffff;
}
QTabBar::tab {
    background: #eaf0f7;
    border: 1px solid #d9e2ec;
    padding: 8px 12px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    color: #3a4a5a;
}
QTabBar::tab:selected {
    background: #ffffff;
    border-bottom-color: #ffffff;
    color: #1f3b57;
    font-weight: 600;
}

QHeaderView::section {
    background: #f0f4f9;
    padding: 6px;
    border: 1px solid #d9e2ec;
    font-weight: 600;
}

QTableWidget {
    gridline-color: #dfe7f1;
    alternate-background-color: #f6f9fc;
}

/* Make tables visually denser (less wasted vertical space) */
QTableView::item {
    padding: 3px;
}
QTableView {
    selection-background-color: #e1efff;
}

/* Scrollbars: more visible (thicker + stronger contrast) */
QScrollBar:vertical {
    background: #e6edf7;
    width: 16px;
    margin: 3px;
    border-radius: 8px;
}
QScrollBar::handle:vertical {
    background: #8aa3c7;
    min-height: 32px;
    border-radius: 8px;
}
QScrollBar::handle:vertical:hover {
    background: #6f90bf;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #e6edf7;
    height: 16px;
    margin: 3px;
    border-radius: 8px;
}
QScrollBar::handle:horizontal {
    background: #8aa3c7;
    min-width: 32px;
    border-radius: 8px;
}
QScrollBar::handle:horizontal:hover {
    background: #6f90bf;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QCheckBox {
    padding: 4px;
}
"""