"""Temas claro/escuro da aplicação (QSS) e persistência da preferência do usuário."""

from PySide6.QtCore import QSettings

ORG_NAME = "AVozDoUltimoDia"
APP_SETTINGS_NAME = "LocalizadorCitacoes"

_FONT_STACK = '"Segoe UI", "Inter", "Noto Sans", Arial, sans-serif'

LIGHT_QSS = f"""
QWidget {{
    background-color: #F5F6F8;
    color: #1B1D21;
    font-family: {_FONT_STACK};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background-color: #F5F6F8;
}}
#HeaderBar {{
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E4E8;
}}
#AppTitleLabel {{
    font-size: 16px;
    font-weight: 600;
    color: #1B1D21;
}}
#AppVersionLabel {{
    font-size: 11px;
    color: #8A8F98;
}}
QLineEdit, QComboBox {{
    background-color: #FFFFFF;
    border: 1px solid #D6D9DE;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #C9A227;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid #C9A227;
}}
QPushButton {{
    background-color: #FFFFFF;
    border: 1px solid #D6D9DE;
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{
    background-color: #EFF1F4;
}}
QPushButton#PrimaryButton {{
    background-color: #8A6D1E;
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background-color: #755B18;
}}
QPushButton#ThemeToggle {{
    border-radius: 16px;
    padding: 6px 10px;
}}
QTableWidget {{
    background-color: #FFFFFF;
    alternate-background-color: #FAFAFB;
    gridline-color: #E8E9EC;
    border: 1px solid #E2E4E8;
    border-radius: 6px;
    font-size: 13px;
}}
QHeaderView::section {{
    background-color: #F0F1F4;
    color: #4A4E57;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #E2E4E8;
    font-weight: 600;
}}
QTableWidget::item:selected {{
    background-color: #F3E7C3;
    color: #1B1D21;
}}
#DetailPanel {{
    background-color: #FFFFFF;
    border: 1px solid #E2E4E8;
    border-radius: 8px;
}}
#DetailText {{
    font-size: 16px;
    line-height: 160%;
    color: #22242A;
    padding: 4px;
}}
#EntryBadge {{
    background-color: #F3E7C3;
    color: #6B5514;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 12px;
}}
QCheckBox {{
    spacing: 8px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #C7CAD1;
    border-radius: 5px;
    min-height: 24px;
}}
"""

DARK_QSS = f"""
QWidget {{
    background-color: #1B1D21;
    color: #E6E7EA;
    font-family: {_FONT_STACK};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background-color: #1B1D21;
}}
#HeaderBar {{
    background-color: #23262B;
    border-bottom: 1px solid #303339;
}}
#AppTitleLabel {{
    font-size: 16px;
    font-weight: 600;
    color: #F2E7C6;
}}
#AppVersionLabel {{
    font-size: 11px;
    color: #8A8F98;
}}
QLineEdit, QComboBox {{
    background-color: #23262B;
    border: 1px solid #3A3E45;
    border-radius: 6px;
    padding: 6px 8px;
    color: #E6E7EA;
    selection-background-color: #C9A227;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid #C9A227;
}}
QComboBox QAbstractItemView {{
    background-color: #23262B;
    color: #E6E7EA;
    selection-background-color: #3A3E45;
}}
QPushButton {{
    background-color: #262A30;
    border: 1px solid #3A3E45;
    border-radius: 6px;
    padding: 7px 14px;
    color: #E6E7EA;
}}
QPushButton:hover {{
    background-color: #2F333A;
}}
QPushButton#PrimaryButton {{
    background-color: #C9A227;
    color: #1B1D21;
    border: none;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background-color: #DCB637;
}}
QPushButton#ThemeToggle {{
    border-radius: 16px;
    padding: 6px 10px;
}}
QTableWidget {{
    background-color: #23262B;
    alternate-background-color: #26292F;
    gridline-color: #33363C;
    border: 1px solid #33363C;
    border-radius: 6px;
    color: #E6E7EA;
    font-size: 13px;
}}
QHeaderView::section {{
    background-color: #2A2D33;
    color: #C7CAD1;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #33363C;
    font-weight: 600;
}}
QTableWidget::item:selected {{
    background-color: #4A3E14;
    color: #F2E7C6;
}}
#DetailPanel {{
    background-color: #23262B;
    border: 1px solid #33363C;
    border-radius: 8px;
}}
#DetailText {{
    font-size: 16px;
    line-height: 160%;
    color: #E6E7EA;
    padding: 4px;
}}
#EntryBadge {{
    background-color: #4A3E14;
    color: #F2E7C6;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 12px;
}}
QCheckBox {{
    spacing: 8px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #3A3E45;
    border-radius: 5px;
    min-height: 24px;
}}
"""


class ThemeManager:
    """Persiste e aplica a preferência de tema (claro/escuro) do usuário."""

    def __init__(self):
        self._settings = QSettings(ORG_NAME, APP_SETTINGS_NAME)

    def is_dark(self) -> bool:
        return self._settings.value("theme/dark", False, type=bool)

    def set_dark(self, is_dark: bool) -> None:
        self._settings.setValue("theme/dark", is_dark)

    def stylesheet(self) -> str:
        return DARK_QSS if self.is_dark() else LIGHT_QSS
