"""
Teste de regressao para bug real reportado pelo usuario (print de tela):
ele buscou a pagina "250" no Livro dos Selos (Tipo A), depois trocou pro
Livro de Citacoes (Tipo B) e digitou o extrato "251" no campo Extrato --
a busca nao retornava nada, porque o campo Pagina continuava com "250"
(deixado da busca anterior, so escondido/trocado de contexto, nunca
limpo) e a busca combinava OS DOIS filtros (pagina 250 E extrato 251),
que quase nunca coincidem entre livros diferentes. Só voltava a
funcionar depois de apagar manualmente o campo Pagina.

Corrigido em app/ui/main_window.py (_on_document_changed): trocar de
documento agora limpa todos os campos de busca (Pagina, Paragrafo,
Extrato, Texto) e os resultados da busca anterior, ja que nenhum deles
faz sentido carregado de um documento pro outro.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pyside6 = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
from PySide6.QtWidgets import QApplication

from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.ui.main_window import MainWindow


def _get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _build_two_documents():
    """Doc 1 (Tipo A): pagina 250 tem o paragrafo 1.
    Doc 2 (Tipo B): extrato 251 fica na pagina 300 -- NUNCA na 250, de
    proposito, pra reproduzir o caso real (numeros de pagina de livros
    diferentes quase nunca coincidem)."""
    tmp_dir = tempfile.mkdtemp()
    db_conn = DatabaseConnection(os.path.join(tmp_dir, "test_switch.db"))
    DatabaseSchemaManager(db_conn).initialize_database()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("selos.pdf", "/tmp/selos.pdf", "Livro dos Selos", "hash_selos", "PARAGRAPH_BOOK"),
        )
        doc1_id = cur.lastrowid
        cur.execute(
            "INSERT INTO pages (document_id, pdf_page_index, printed_page_label, confidence) VALUES (?, ?, ?, ?)",
            (doc1_id, 0, "250", 0.95),
        )
        page1_id = cur.lastrowid
        cur.execute(
            "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text) VALUES (?, ?, ?, ?)",
            (page1_id, "1", "Texto do paragrafo 1.", "texto do paragrafo 1."),
        )
        para1_id = cur.lastrowid
        cur.execute(
            "INSERT INTO paragraph_chunks (paragraph_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
            (para1_id, page1_id, "Texto do paragrafo 1.", "[]"),
        )
        cur.execute(
            "INSERT INTO fts_paragraphs VALUES (?, ?, ?, ?, ?)",
            (para1_id, doc1_id, "250", "1", "texto do paragrafo 1."),
        )

        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("citas.pdf", "/tmp/citas.pdf", "Libro de Citas", "hash_citas", "CITATIONS_BOOK"),
        )
        doc2_id = cur.lastrowid
        cur.execute(
            "INSERT INTO pages (document_id, pdf_page_index, printed_page_label, confidence) VALUES (?, ?, ?, ?)",
            (doc2_id, 0, "300", 0.95),
        )
        page2_id = cur.lastrowid
        cur.execute(
            "INSERT INTO text_entries (document_id, entry_number, full_text, normalized_text) VALUES (?, ?, ?, ?)",
            (doc2_id, "251", "Texto do extrato 251.", "texto do extrato 251."),
        )
        entry_id = cur.lastrowid
        cur.execute(
            "INSERT INTO entry_chunks (entry_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
            (entry_id, page2_id, "Texto do extrato 251.", "[]"),
        )
        cur.execute(
            "INSERT INTO fts_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry_id, doc2_id, "300", "251", "texto do extrato 251.", "", ""),
        )
        conn.commit()

    return db_conn, doc1_id, doc2_id


def test_switching_document_clears_stale_search_fields():
    _get_app()
    db_conn, doc1_id, doc2_id = _build_two_documents()
    w = MainWindow(db_conn=db_conn)

    # Seleciona o Livro dos Selos (doc1) e digita a pagina 250, como o
    # usuario fez de verdade.
    idx1 = w.combo_docs.findData({"id": doc1_id, "profile": "PARAGRAPH_BOOK"})
    # findData com dict não casa por igualdade de objeto -- procura manualmente.
    idx1 = next(i for i in range(w.combo_docs.count()) if w.combo_docs.itemData(i)["id"] == doc1_id)
    w.combo_docs.setCurrentIndex(idx1)
    w.txt_page.setText("250")

    # Troca pro Livro de Citações (doc2) -- ANTES da correção, "250"
    # continuava no campo Página.
    idx2 = next(i for i in range(w.combo_docs.count()) if w.combo_docs.itemData(i)["id"] == doc2_id)
    w.combo_docs.setCurrentIndex(idx2)

    assert w.txt_page.text() == "", (
        f"campo Página não foi limpo ao trocar de documento (ainda tem {w.txt_page.text()!r}) "
        "-- reproduz o bug real reportado"
    )

    # Digita o extrato 251, do jeito que o usuário fez, e confirma que a
    # busca agora encontra o extrato (antes, o filtro fantasma de página
    # "250" bloqueava esse resultado).
    w.txt_entry.setText("251")
    results = w.search_engine.search(document_id=doc2_id, entry_num="251")
    assert len(results) == 1
    assert "extrato 251" in results[0].full_text


if __name__ == "__main__":
    test_switching_document_clears_stale_search_fields()
    print("OK: trocar de documento limpa os campos de busca do documento anterior.")
