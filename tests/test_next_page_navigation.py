"""
Teste do botao "Proxima Pagina" (SearchEngine.get_next_page_with_content):
pedido real do usuario para avancar a leitura sem digitar o numero
manualmente, pulando paginas "buraco" sem conteudo (ex.: abertura de
capitulo sem numero impresso, paginas "Notas" em branco).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import tempfile

from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.indexing.paragraph_indexer import ParagraphIndexer
from app.search.engine import SearchEngine


def _build_and_index():
    """3 paginas de conteudo real (147, 149, 150 -- reproduzindo o caso
    real onde '148' nao existe, e uma pagina 'Notas' isolada, sem
    conteudo, no meio)."""
    doc = fitz.open()

    p1 = doc.new_page(width=432, height=612)
    p1.insert_text((150, 40), "EL PRIMER SELLO", fontsize=10)
    p1.insert_text((150, 45), "147", fontsize=10)
    p1.insert_text((54, 80), "194.\t Texto da pagina cento e quarenta e sete.", fontsize=10)

    # Pagina em branco no meio -- nao deve nunca ser destino do "proxima".
    p_blank = doc.new_page(width=432, height=612)
    p_blank.insert_text((190, 40), "Notas", fontsize=12)

    p2 = doc.new_page(width=432, height=612)
    p2.insert_text((180, 30), "EL SEGUNDO SELLO", fontsize=10)
    p2.insert_text((140, 100), "19 de marzo de 1963 Tabernaculo Branham", fontsize=9)
    p2.insert_text((54, 200), "1.\t Texto da pagina cento e quarenta e nove.", fontsize=10)

    p3 = doc.new_page(width=432, height=612)
    p3.insert_text((150, 40), "LOS SIETE SELLOS", fontsize=10)
    p3.insert_text((150, 45), "150", fontsize=10)
    p3.insert_text((54, 80), "4.\t Texto da pagina cento e cinquenta.", fontsize=10)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "test_next_page.pdf")
    doc.save(pdf_path)
    doc.close()

    db_path = os.path.join(tmp_dir, "test_next_page.db")
    db_conn = DatabaseConnection(db_path)
    DatabaseSchemaManager(db_conn).initialize_database()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("t.pdf", pdf_path, "Teste", "hash_next_page", "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        conn.commit()

    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)
    return db_conn, doc_id


def test_next_page_skips_gap_without_content():
    db_conn, doc_id = _build_and_index()
    engine = SearchEngine(db_conn)

    # 147 -> deveria ir direto pra 149 (pulando o buraco "148" que nunca
    # existe -- ver v2.4.4).
    assert engine.get_next_page_with_content(doc_id, "147") == "149"
    # 149 -> 150 normalmente.
    assert engine.get_next_page_with_content(doc_id, "149") == "150"
    # 150 -> fim do documento, nao tem proxima.
    assert engine.get_next_page_with_content(doc_id, "150") is None


def test_next_page_returns_none_for_non_numeric_label():
    db_conn, doc_id = _build_and_index()
    engine = SearchEngine(db_conn)
    assert engine.get_next_page_with_content(doc_id, "14A") is None
    assert engine.get_next_page_with_content(doc_id, "") is None


if __name__ == "__main__":
    test_next_page_skips_gap_without_content()
    test_next_page_returns_none_for_non_numeric_label()
    print("OK: botao de proxima pagina pula buracos sem conteudo corretamente.")
