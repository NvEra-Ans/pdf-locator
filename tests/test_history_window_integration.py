"""
Teste de integração de ponta a ponta do Histórico de Pesquisas: uma
busca real feita pela MainWindow (do jeito que o usuário faz de
verdade, digitando página e clicando Pesquisar) precisa aparecer na
HistoryWindow, e uma busca sem resultado NÃO deve aparecer.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pyside6 = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer

from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.ui.main_window import MainWindow


def _get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _spin_until(condition_fn, timeout_ms=3000):
    """A busca roda numa QThread separada -- processa o loop de eventos
    até a condição ficar verdadeira (ou estourar o tempo limite), em vez
    de travar o teste com um sleep fixo."""
    app = QApplication.instance()
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)

    elapsed = 0
    step = 20
    while not condition_fn() and elapsed < timeout_ms:
        app.processEvents()
        QTimer.singleShot(step, loop.quit)
        loop.exec()
        elapsed += step
    return condition_fn()


def _build_document(db_conn):
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("selos.pdf", "/tmp/selos.pdf", "Livro dos Selos", "hash_hist_int", "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        cur.execute(
            "INSERT INTO pages (document_id, pdf_page_index, printed_page_label, confidence) VALUES (?, ?, ?, ?)",
            (doc_id, 0, "250", 0.95),
        )
        page_id = cur.lastrowid
        cur.execute(
            "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text) VALUES (?, ?, ?, ?)",
            (page_id, "1", "Texto do paragrafo 1.", "texto do paragrafo 1."),
        )
        para_id = cur.lastrowid
        cur.execute(
            "INSERT INTO paragraph_chunks (paragraph_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
            (para_id, page_id, "Texto do paragrafo 1.", "[]"),
        )
        cur.execute(
            "INSERT INTO fts_paragraphs VALUES (?, ?, ?, ?, ?)",
            (para_id, doc_id, "250", "1", "texto do paragrafo 1."),
        )
        conn.commit()
    return doc_id


def test_successful_search_is_logged_and_failed_search_is_not():
    _get_app()
    tmp_dir = tempfile.mkdtemp()
    db_conn = DatabaseConnection(os.path.join(tmp_dir, "test_hist_int.db"))
    DatabaseSchemaManager(db_conn).initialize_database()
    _build_document(db_conn)

    w = MainWindow(db_conn=db_conn)

    # Busca que ACHA resultado (página 250, real) -- deve entrar no histórico.
    w.txt_page.setText("250")
    w._perform_search()
    assert _spin_until(lambda: len(w.current_results) == 1), "busca não terminou a tempo"

    # Busca que NÃO acha nada (página inexistente) -- não deve entrar.
    w.txt_page.setText("999")
    w._perform_search()
    assert _spin_until(lambda: w.lbl_detail_header.text() == "Nenhum resultado encontrado")

    entries = w.search_history.list_history()
    assert len(entries) == 1, f"esperado 1 entrada no histórico, achou {len(entries)}"
    assert entries[0].document_title == "Livro dos Selos"
    assert "Página: 250" in entries[0].query_summary
    assert "Página 250, Parágrafo 1" in entries[0].result_summary

    # A janela de Histórico precisa mostrar essa mesma entrada.
    w._show_history_window()
    assert w.history_window.table.rowCount() == 1
    assert w.history_window.table.item(0, 1).text() == "Livro dos Selos"


if __name__ == "__main__":
    test_successful_search_is_logged_and_failed_search_is_not()
    print("OK: busca com resultado entra no historico, busca sem resultado nao entra.")
