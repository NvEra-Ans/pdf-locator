"""
Teste de regressao para dois bugs/pedidos reais do usuario sobre a Tela
de Leitura (janela do segundo monitor, usada na traducao simultanea):

1. BUG: minimizar o app principal minimizava a Tela de Leitura junto, e
   restaurar o app principal fazia ela voltar recentralizada, perdendo
   a posicao que o usuario tinha arrastado pro monitor 2. Causa raiz:
   MirrorWindow (e HistoryWindow) eram criadas com a janela principal
   como "parent" -- no Windows isso torna a janela filha "possuida"
   pela principal, agrupando minimizar/restaurar entre as duas. Pedido
   explicito do usuario: "quero que ela se mantenha ativa mesmo se eu
   minimizar o aplicativo". Corrigido criando as duas SEM parent.

2. PEDIDO: um modo tela cheia na Tela de Leitura, sem a barra do
   Windows (minimizar/maximizar/fechar), saindo com Esc (clicando na
   janela primeiro) ou clicando de novo no botao.

Nota: o ambiente de teste headless (QT_QPA_PLATFORM=offscreen) nao tem
um gerenciador de janelas de verdade, entao o comportamento real de
"minimizar junto" do Windows nao pode ser reproduzido aqui -- o que
este teste verifica é a CAUSA RAIZ estrutural (nenhuma das duas janelas
tem mais a principal como parent, que é o que causava o agrupamento) e
o comportamento do modo tela cheia, que o Qt processa e expõe via
isFullScreen() mesmo sem um window manager real.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pyside6 = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import QEvent

from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.ui.main_window import MainWindow
from app.ui.mirror_window import MirrorWindow


def _get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _build_main_window():
    tmp_dir = tempfile.mkdtemp()
    db_conn = DatabaseConnection(os.path.join(tmp_dir, "test_windows.db"))
    DatabaseSchemaManager(db_conn).initialize_database()
    return MainWindow(db_conn=db_conn)


def test_mirror_and_history_windows_have_no_parent():
    """Causa raiz do bug real: sem parent, o Windows não agrupa
    minimizar/restaurar entre a janela principal e estas duas."""
    _get_app()
    w = _build_main_window()

    w._toggle_mirror_window()
    assert w.mirror_window.parent() is None, (
        "Tela de Leitura ainda tem a janela principal como parent -- "
        "volta a minimizar/recentralizar junto (bug real reportado)"
    )

    w._show_history_window()
    assert w.history_window.parent() is None


def test_closing_main_window_also_closes_mirror_and_history():
    """Sem parent, o Qt não fecha mais essas janelas sozinho -- precisa
    do closeEvent explícito em MainWindow pra não deixar órfã."""
    _get_app()
    w = _build_main_window()
    w._toggle_mirror_window()
    w._show_history_window()

    assert w.mirror_window.isVisible()
    assert w.history_window.isVisible()

    w.close()

    assert not w.mirror_window.isVisible()
    assert not w.history_window.isVisible()


def test_mirror_window_fullscreen_toggle():
    _get_app()
    mw = MirrorWindow()
    mw.show()
    assert not mw.isFullScreen()

    mw._toggle_fullscreen()
    assert mw.isFullScreen()
    assert "Sair da Tela Cheia" in mw.btn_fullscreen.text()

    mw._toggle_fullscreen()
    assert not mw.isFullScreen()
    assert "Tela Cheia" in mw.btn_fullscreen.text()


def test_escape_key_exits_fullscreen_but_not_normal_mode():
    _get_app()
    mw = MirrorWindow()
    mw.show()
    mw._toggle_fullscreen()
    assert mw.isFullScreen()

    esc_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    mw.keyPressEvent(esc_event)
    assert not mw.isFullScreen(), "Esc não tirou a janela do modo tela cheia"

    # Esc fora do modo tela cheia não deve quebrar nada (só repassa pro
    # comportamento padrão do Qt).
    mw.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert not mw.isFullScreen()


if __name__ == "__main__":
    test_mirror_and_history_windows_have_no_parent()
    test_closing_main_window_also_closes_mirror_and_history()
    test_mirror_window_fullscreen_toggle()
    test_escape_key_exits_fullscreen_but_not_normal_mode()
    print("OK: Tela de Leitura independente da janela principal, tela cheia funcionando.")
