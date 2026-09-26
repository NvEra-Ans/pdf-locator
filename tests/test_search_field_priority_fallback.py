"""
Teste de regressao para bug real reportado pelo usuario: "se eu digitar um
numero de pagina na busca do libro de citas e depois digitar um paragrafo o
aplicativo nao retorna nada faça que a prioridade seja onde eu digitei por
ultimo".

Reproduz exatamente o fluxo: o usuario digita uma pagina, pesquisa (ou nao),
e DEPOIS digita um parágrafo/extrato sem apagar o campo Página antigo. Como
a busca combina os dois filtros (Página E Parágrafo/Extrato, de proposito --
usado pra desambiguar um parágrafo repetido em mais de uma página, ver
tests/test_paragraph_page_aggregation.py), se o parágrafo digitado por
último não pertence à página que sobrou no campo Página, a busca combinada
não acha nada.

Correção (app/ui/main_window.py): quando a busca combinada não encontra
nada, o app tenta de novo automaticamente usando só o campo que foi editado
por ÚLTIMO (rastreado via textEdited em txt_page/txt_para/txt_entry),
limpando o outro campo. A combinação Página+Parágrafo continua funcionando
normalmente quando ela De fato encontra algo -- só entra o fallback quando
o resultado combinado é vazio.
"""
import sys
import os
import time

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


def _wait_for_search_to_settle(w, timeout=5.0):
    """Processa o loop de eventos Qt até o botão de busca voltar ao estado
    normal (reabilitado, texto 'Pesquisar') -- só acontece depois que a
    busca (e o eventual retry de fallback) terminam de verdade."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        _get_app().processEvents()
        if w.btn_search.isEnabled() and w.btn_search.text() == "Pesquisar":
            return
        time.sleep(0.01)
    raise AssertionError("Busca não terminou dentro do timeout")


def _build_document():
    """Um livro Tipo A (parágrafos) onde a página '10' tem o parágrafo '1',
    e a página '20' (bem diferente) tem o parágrafo '999' -- de propósito,
    pra reproduzir o caso real: página e parágrafo digitados em momentos
    diferentes, sem nenhuma relação um com o outro."""
    tmp_dir = tempfile.mkdtemp()
    db_conn = DatabaseConnection(os.path.join(tmp_dir, "test_priority.db"))
    DatabaseSchemaManager(db_conn).initialize_database()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("citas.pdf", "/tmp/citas.pdf", "Livro de Citações", "hash_citas", "CITATIONS_BOOK"),
        )
        doc_id = cur.lastrowid

        cur.execute(
            "INSERT INTO pages (document_id, pdf_page_index, printed_page_label, confidence) VALUES (?, ?, ?, ?)",
            (doc_id, 0, "10", 0.95),
        )
        page10_id = cur.lastrowid
        cur.execute(
            "INSERT INTO text_entries (document_id, entry_number, full_text, normalized_text) VALUES (?, ?, ?, ?)",
            (doc_id, "1", "Texto do extrato 1, pagina 10.", "texto do extrato 1, pagina 10."),
        )
        entry1_id = cur.lastrowid
        cur.execute(
            "INSERT INTO entry_chunks (entry_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
            (entry1_id, page10_id, "Texto do extrato 1, pagina 10.", "[]"),
        )
        cur.execute(
            "INSERT INTO fts_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry1_id, doc_id, "10", "1", "texto do extrato 1, pagina 10.", "", ""),
        )

        cur.execute(
            "INSERT INTO pages (document_id, pdf_page_index, printed_page_label, confidence) VALUES (?, ?, ?, ?)",
            (doc_id, 1, "20", 0.95),
        )
        page20_id = cur.lastrowid
        cur.execute(
            "INSERT INTO text_entries (document_id, entry_number, full_text, normalized_text) VALUES (?, ?, ?, ?)",
            (doc_id, "999", "Texto do extrato 999, pagina 20.", "texto do extrato 999, pagina 20."),
        )
        entry999_id = cur.lastrowid
        cur.execute(
            "INSERT INTO entry_chunks (entry_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
            (entry999_id, page20_id, "Texto do extrato 999, pagina 20.", "[]"),
        )
        cur.execute(
            "INSERT INTO fts_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry999_id, doc_id, "20", "999", "texto do extrato 999, pagina 20.", "", ""),
        )
        conn.commit()

    return db_conn, doc_id


def test_typing_entry_after_stale_page_falls_back_to_last_edited_field():
    _get_app()
    db_conn, doc_id = _build_document()
    w = MainWindow(db_conn=db_conn)

    idx = next(i for i in range(w.combo_docs.count()) if w.combo_docs.itemData(i)["id"] == doc_id)
    w.combo_docs.setCurrentIndex(idx)

    # Usuário digita a página 10 (via teclado -- setText sozinho não
    # dispara textEdited, então simulamos digitação de verdade).
    w.txt_page.setText("10")
    w.txt_page.textEdited.emit("10")

    # Depois, SEM apagar a página, digita o extrato 999 -- que na
    # verdade fica na página 20, não na 10.
    w.txt_entry.setText("999")
    w.txt_entry.textEdited.emit("999")

    assert w._last_edited_field == "entry"

    w._perform_search()
    _wait_for_search_to_settle(w)

    assert len(w.current_results) == 1, (
        f"Busca não caiu de volta pro campo editado por último (extrato): {w.current_results!r}"
    )
    assert w.current_results[0].entry_number == "999"
    assert "extrato 999" in w.current_results[0].full_text

    # O campo Página (que estava "errado"/desatualizado) foi limpo pelo
    # fallback, e o Extrato -- o campo que o usuário editou por último --
    # continua com o valor que ele digitou.
    assert w.txt_page.text() == ""
    assert w.txt_entry.text() == "999"


def test_combined_page_and_entry_still_works_when_they_actually_match():
    """A combinação Página+Extrato não pode quebrar quando os dois campos
    realmente correspondem ao mesmo resultado -- não é pra sempre ignorar
    o campo mais antigo, só quando a combinação falha."""
    _get_app()
    db_conn, doc_id = _build_document()
    w = MainWindow(db_conn=db_conn)

    idx = next(i for i in range(w.combo_docs.count()) if w.combo_docs.itemData(i)["id"] == doc_id)
    w.combo_docs.setCurrentIndex(idx)

    w.txt_page.setText("10")
    w.txt_page.textEdited.emit("10")
    w.txt_entry.setText("1")
    w.txt_entry.textEdited.emit("1")

    w._perform_search()
    _wait_for_search_to_settle(w)

    assert len(w.current_results) == 1
    assert w.current_results[0].entry_number == "1"
    # Como a combinação já achou resultado, nenhum fallback deveria ter
    # disparado -- os dois campos continuam preenchidos como o usuário
    # deixou.
    assert w.txt_page.text() == "10"
    assert w.txt_entry.text() == "1"


if __name__ == "__main__":
    test_typing_entry_after_stale_page_falls_back_to_last_edited_field()
    test_combined_page_and_entry_still_works_when_they_actually_match()
    print("OK: fallback pro campo editado por último funciona, combinação válida continua intacta.")
