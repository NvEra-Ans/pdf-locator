"""
Teste de regressao para o pedido real do usuario: no perfil Tipo A
(livro estruturado por paragrafos, ex.: "Los Siete Sellos"), buscar por
PAGINA precisa devolver a pagina inteira (todos os paragrafos daquela
pagina, na ordem em que aparecem), nao um resultado separado por
paragrafo -- diferente do livro de citacoes, onde cada extrato e uma
unidade fechada por si so.

Buscar so por paragrafo (sem pagina) continua devolvendo 1 resultado
por paragrafo, ja que a numeracao reinicia por capitulo e o objetivo
nesse caso e achar aquele numero especifico em qualquer capitulo.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.search.engine import SearchEngine
from app.models.document import ProfileType


def _setup_db(tmp_path):
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    db_conn = DatabaseConnection(tmp_path)
    DatabaseSchemaManager(db_conn).initialize_database()

    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("sellos.pdf", "/tmp/sellos.pdf", "Los Siete Sellos", "hashxyz", ProfileType.PARAGRAPH_BOOK.value)
        )
        doc_id = cursor.lastrowid

        # Pagina 10: paragrafos 32 e 33, igual ao caso real reportado.
        cursor.execute("INSERT INTO pages (document_id, pdf_page_index, printed_page_label) VALUES (?, ?, ?)", (doc_id, 15, "10"))
        page_id_10 = cursor.lastrowid
        cursor.execute(
            "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text) VALUES (?, ?, ?, ?)",
            (page_id_10, "32", "32. Ahora deseo leer en el primer libro de Crónicas.", "32 ahora deseo leer en el primer libro de cronicas.")
        )
        para_id_32 = cursor.lastrowid
        cursor.execute(
            "INSERT INTO paragraph_chunks (paragraph_id, page_id, chunk_text) VALUES (?, ?, ?)",
            (para_id_32, page_id_10, "32. Ahora deseo leer en el primer libro de Crónicas.")
        )
        cursor.execute(
            "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text) VALUES (?, ?, ?, ?)",
            (page_id_10, "33", "33. Quisiera decir aquí que David vio la misma cosa.", "33 quisiera decir aqui que david vio la misma cosa.")
        )
        para_id_33 = cursor.lastrowid
        cursor.execute(
            "INSERT INTO paragraph_chunks (paragraph_id, page_id, chunk_text) VALUES (?, ?, ?)",
            (para_id_33, page_id_10, "33. Quisiera decir aquí que David vio la misma cosa.")
        )
        conn.commit()

    return db_conn, doc_id


def test_search_by_page_returns_whole_page_aggregated():
    db_conn, doc_id = _setup_db("/tmp/test_page_agg.db")
    engine = SearchEngine(db_conn)

    results = engine.search(document_id=doc_id, page_label="10")

    assert len(results) == 1, f"Esperava 1 resultado agregado da pagina, veio {len(results)}"
    r = results[0]
    assert "32. Ahora deseo leer" in r.full_text
    assert "33. Quisiera decir" in r.full_text
    assert r.paragraph_number == "32-33"
    assert r.printed_page_label == "10"


def test_search_by_page_and_paragraph_still_returns_whole_page():
    db_conn, doc_id = _setup_db("/tmp/test_page_agg2.db")
    engine = SearchEngine(db_conn)

    # Busca pagina 10 + paragrafo 32 -- a pagina qualifica (tem o
    # paragrafo 32), e o resultado continua sendo a pagina inteira.
    results = engine.search(document_id=doc_id, page_label="10", paragraph_num="32")

    assert len(results) == 1
    assert "32. Ahora deseo leer" in results[0].full_text
    assert "33. Quisiera decir" in results[0].full_text


def test_search_by_paragraph_alone_still_returns_one_row_per_paragraph():
    db_conn, doc_id = _setup_db("/tmp/test_page_agg3.db")
    engine = SearchEngine(db_conn)

    # Sem pagina: busca so pelo paragrafo 32 em qualquer capitulo --
    # continua devolvendo so o paragrafo 32 (nao a pagina inteira).
    results = engine.search(document_id=doc_id, paragraph_num="32")

    assert len(results) == 1
    assert "32. Ahora deseo leer" in results[0].full_text
    assert "33. Quisiera decir" not in results[0].full_text
    assert results[0].paragraph_number == "32"


if __name__ == "__main__":
    test_search_by_page_returns_whole_page_aggregated()
    test_search_by_page_and_paragraph_still_returns_whole_page()
    test_search_by_paragraph_alone_still_returns_one_row_per_paragraph()
    print("OK: busca por pagina agrega todos os paragrafos; busca por paragrafo isolado continua granular.")
