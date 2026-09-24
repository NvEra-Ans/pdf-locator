"""
Teste de regressao para o bug real reportado pelo usuario: busca pela
pagina "53" (numero impresso que existe no livro real, mas some entre
paginas de abertura de capitulo) nao retornava nada.

Causa raiz confirmada nos dados reais do livro "La Revelacion de Los
Siete Sellos": paginas "Notas" (em branco, inseridas nesta edicao) e a
pagina de abertura de cada capitulo novo NAO tem numero de pagina
impresso no PDF. O indexador antigo usava o indice bruto do PDF como
fallback (pdf_page_index + 1), o que diverge completamente da
numeracao real assim que aparece uma sequencia dessas paginas sem
numero -- o numero real ("53") nunca chegava a existir no banco.

Bug relacionado, tambem corrigido junto: a pagina de abertura de
capitulo tem um bloco decorativo (data, local, epigrafe) ANTES do
primeiro paragrafo "1." que nao e todo maiusculo (entao escapava do
filtro de cabecalho) e vazava pro final do ULTIMO paragrafo do
capitulo ANTERIOR, que ainda estava aberto.
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
    doc = fitz.open()

    # Pagina fisica 1 ("52" impresso): capitulo em andamento, paragrafo
    # 204 fica aberto (nao fecha nesta pagina).
    p1 = doc.new_page(width=432, height=612)
    p1.insert_text((150, 40), "DIOS EN SIMPLICIDAD", fontsize=10)
    p1.insert_text((150, 45), "52", fontsize=10)
    p1.insert_text((54, 80), "204.\t Texto do paragrafo duzentos e quatro que continua aberto.", fontsize=10)

    # Paginas fisicas 2 e 3: "Notas" em branco, sem numero impresso.
    p2 = doc.new_page(width=432, height=612)
    p2.insert_text((190, 40), "Notas", fontsize=12)
    p3 = doc.new_page(width=432, height=612)
    p3.insert_text((190, 40), "Notas", fontsize=12)

    # Pagina fisica 4: abertura do capitulo novo -- SEM numero impresso.
    # Titulo (maiusculo, filtrado) + bloco decorativo centralizado
    # (data/local, NAO maiusculo -- risco real) + paragrafo "1.".
    p4 = doc.new_page(width=432, height=612)
    p4.insert_text((180, 30), "LA BRECHA", fontsize=10)
    p4.insert_text((140, 100), "17 de marzo de 1963 Tabernaculo Branham", fontsize=9)
    p4.insert_text((54, 200), "1.\t Texto do primeiro paragrafo do capitulo novo.", fontsize=10)

    # Pagina fisica 5 ("54" impresso): capitulo novo continua normalmente.
    p5 = doc.new_page(width=432, height=612)
    p5.insert_text((150, 40), "LOS SIETE SELLOS", fontsize=10)
    p5.insert_text((150, 45), "54", fontsize=10)
    p5.insert_text((54, 80), "4.\t Texto do quarto paragrafo, capitulo novo continuando.", fontsize=10)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "test_transicao.pdf")
    doc.save(pdf_path)
    doc.close()

    db_path = os.path.join(tmp_dir, "test_transicao.db")
    db_conn = DatabaseConnection(db_path)
    DatabaseSchemaManager(db_conn).initialize_database()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("t.pdf", pdf_path, "Teste", "hash_transicao", "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        conn.commit()

    indexer = ParagraphIndexer(db_conn)
    indexer.index_document(doc_id, pdf_path)

    return db_conn, doc_id


def test_page_number_is_inferred_across_unnumbered_chapter_opening():
    db_conn, doc_id = _build_and_index()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT pdf_page_index, printed_page_label FROM pages WHERE document_id=? ORDER BY pdf_page_index",
            (doc_id,),
        )
        rows = cur.fetchall()

    labels = [r["printed_page_label"] for r in rows]
    # Pagina 1: "52" (detectado). Paginas 2/3 "Notas": repetem "52" (nao
    # consomem numero). Pagina 4 (abertura de capitulo): infere "53"
    # (continua a sequencia). Pagina 5: "54" (detectado).
    assert labels == ["52", "52", "52", "53", "54"], f"Sequencia de paginas errada: {labels}"


def test_search_by_page_53_returns_chapter_opening_content():
    db_conn, doc_id = _build_and_index()
    engine = SearchEngine(db_conn)

    results = engine.search(document_id=doc_id, page_label="53")
    assert len(results) == 1, "Busca pela pagina 53 (inferida) nao retornou resultado"
    assert "Texto do primeiro paragrafo do capitulo novo." in results[0].full_text


def test_decorative_block_does_not_leak_into_previous_or_next_paragraph():
    db_conn, doc_id = _build_and_index()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT p.paragraph_number, p.text FROM paragraphs p "
            "JOIN pages pg ON p.page_id = pg.id WHERE pg.document_id=? ORDER BY p.id",
            (doc_id,),
        )
        rows = cur.fetchall()

    texts_by_num = {r["paragraph_number"]: r["text"] for r in rows}

    assert "17 de marzo" not in texts_by_num.get("204", ""), (
        f"BUG: bloco decorativo vazou pro paragrafo 204 (capitulo anterior): {texts_by_num.get('204')!r}"
    )
    assert "17 de marzo" not in texts_by_num.get("1", ""), (
        f"BUG: bloco decorativo vazou pro paragrafo 1 (capitulo novo): {texts_by_num.get('1')!r}"
    )
    assert "LA BRECHA" not in texts_by_num.get("204", "")
    assert "LA BRECHA" not in texts_by_num.get("1", "")


if __name__ == "__main__":
    test_page_number_is_inferred_across_unnumbered_chapter_opening()
    test_search_by_page_53_returns_chapter_opening_content()
    test_decorative_block_does_not_leak_into_previous_or_next_paragraph()
    print("OK: numeracao de pagina inferida corretamente na transicao de capitulo, sem vazamento decorativo.")
