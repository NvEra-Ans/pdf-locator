"""
Testes de regressao para o perfil Tipo A (Livro Estruturado por
Paragrafos), cobrindo os dois bugs reais encontrados com o PDF real do
livro "La Revelacion de Los Siete Sellos":

  1. PARAGRAPH_PATTERN_TYPE_A precisa reconhecer "N." + TAB como inicio
     de paragrafo (formato real do livro), sem reconhecer por engano um
     numero comum seguido de ponto e espaco normal no meio de uma frase
     (ex.: "...en el ano 1963. Despues...").
  2. paragraph_indexer.py precisa tratar cabecalho/rodape (titulo do
     livro/capitulo, numero de pagina, paginas "Notas" quase em branco)
     como nao-conteudo -- sem isso, esse texto vazava pro paragrafo
     aberto anteriormente.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.pattern_detector import PatternDetector


def test_paragraph_pattern_type_a_matches_tab_separator():
    res = PatternDetector.analyze_text_span(
        "13.\t Ahora, yo no sé lo que significan estos sellos.",
        [0, 0, 0, 0], 432, 612,
        paragraph_pattern=PatternDetector.PARAGRAPH_PATTERN_TYPE_A,
    )
    assert res["is_paragraph_candidate"] is True
    assert res["detected_paragraph_num"] == "13"


def test_paragraph_pattern_type_a_matches_number_alone_on_own_line():
    # Caso real confirmado: as vezes o numero fica sozinho na linha, com
    # o texto continuando na linha seguinte (bloco separado).
    res = PatternDetector.analyze_text_span(
        "4.\t",
        [0, 0, 0, 0], 432, 612,
        paragraph_pattern=PatternDetector.PARAGRAPH_PATTERN_TYPE_A,
    )
    assert res["is_paragraph_candidate"] is True
    assert res["detected_paragraph_num"] == "4"


def test_paragraph_pattern_type_a_does_not_match_plain_space_separator():
    # "1963. Despues..." tem ponto + ESPACO comum (nao tab) -- nao pode
    # virar um "paragrafo 1963" fantasma.
    res = PatternDetector.analyze_text_span(
        "1963. Después de esto sucedió algo interesante.",
        [0, 0, 0, 0], 432, 612,
        paragraph_pattern=PatternDetector.PARAGRAPH_PATTERN_TYPE_A,
    )
    assert res["is_paragraph_candidate"] is False


def test_citations_book_paragraph_pattern_unaffected_by_default():
    # Sem passar paragraph_pattern, o comportamento do Tipo B (livro de
    # citacoes) tem que continuar EXATAMENTE como antes -- separador e
    # traco, nao ponto+tab.
    res = PatternDetector.analyze_text_span(
        "87 - [Estas líneas de texto son directas...]",
        [0, 0, 0, 0], 612, 792,
    )
    assert res["is_paragraph_candidate"] is True
    assert res["detected_paragraph_num"] == "87"

    # E o formato do Tipo A ("N." + tab) NAO deve ser reconhecido como
    # paragrafo pelo padrao do Tipo B (nao teriam abertura de extrato
    # nenhuma nesse livro nesse formato).
    res2 = PatternDetector.analyze_text_span(
        "13.\t Ahora, yo no sé lo que significan estos sellos.",
        [0, 0, 0, 0], 612, 792,
    )
    assert res2["is_paragraph_candidate"] is False


def test_notas_page_recognized_as_header_or_footer():
    res = PatternDetector.analyze_text_span("Notas", [0, 0, 0, 0], 432, 612)
    assert res["is_header_or_footer"] is True


def _block(x0, y0, x1, y1, lines_text):
    return {
        "type": 0,
        "bbox": [x0, y0, x1, y1],
        "lines": [{"spans": [{"text": t}]} for t in lines_text],
    }


def test_indexer_does_not_leak_header_or_notas_page_into_paragraph():
    """Reproducao fim-a-fim (com banco real em memoria) do bug real:
    cabecalho do livro/capitulo e a pagina 'Notas' vazando pro corpo do
    ultimo paragrafo aberto."""
    import fitz
    import tempfile
    from app.database.connection import DatabaseConnection
    from app.database.schema import DatabaseSchemaManager
    from app.indexing.paragraph_indexer import ParagraphIndexer

    doc = fitz.open()

    # Pagina 1: cabecalho + paragrafo 1 (numero sozinho na linha, como no
    # caso real) + paragrafo 2.
    p1 = doc.new_page(width=432, height=612)
    p1.insert_text((150, 40), "LOS SIETE SELLOS", fontsize=10)
    p1.insert_text((54, 80), "1.\t", fontsize=10)
    p1.insert_text((54, 100), "Texto do primeiro paragrafo aqui.", fontsize=10)
    p1.insert_text((54, 130), "2.\t Texto do segundo paragrafo, numero e texto juntos.", fontsize=10)
    p1.insert_text((280, 580), "2", fontsize=9)

    # Pagina 2: pagina "Notas" quase em branco -- nao deve grudar no
    # paragrafo 2 que ainda estava aberto.
    p2 = doc.new_page(width=432, height=612)
    p2.insert_text((190, 40), "Notas", fontsize=12)

    # Pagina 3: paragrafo 3, com cabecalho de capitulo diferente.
    p3 = doc.new_page(width=432, height=612)
    p3.insert_text((150, 40), "LA BRECHA", fontsize=10)
    p3.insert_text((54, 80), "3.\t Texto do terceiro paragrafo, em outro capitulo.", fontsize=10)
    p3.insert_text((280, 580), "4", fontsize=9)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "test_sellos.pdf")
    doc.save(pdf_path)
    doc.close()

    db_path = os.path.join(tmp_dir, "test_sellos.db")
    db_conn = DatabaseConnection(db_path)
    DatabaseSchemaManager(db_conn).initialize_database()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("t.pdf", pdf_path, "Teste", "hashabc", "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        conn.commit()

    indexer = ParagraphIndexer(db_conn)
    indexer.index_document(doc_id, pdf_path)

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT paragraph_number, text FROM paragraphs WHERE page_id IN "
            "(SELECT id FROM pages WHERE document_id=?) ORDER BY id",
            (doc_id,),
        )
        rows = cur.fetchall()

    texts_by_num = {r["paragraph_number"]: r["text"] for r in rows}

    assert "LOS SIETE SELLOS" not in texts_by_num.get("1", ""), (
        f"BUG: cabecalho do livro vazou pro paragrafo 1: {texts_by_num.get('1')!r}"
    )
    assert "Notas" not in texts_by_num.get("2", ""), (
        f"BUG: pagina 'Notas' vazou pro paragrafo 2: {texts_by_num.get('2')!r}"
    )
    assert "LA BRECHA" not in texts_by_num.get("3", ""), (
        f"BUG: cabecalho do capitulo vazou pro paragrafo 3: {texts_by_num.get('3')!r}"
    )
    assert "Texto do primeiro paragrafo aqui." in texts_by_num.get("1", "")
    assert "Texto do segundo paragrafo, numero e texto juntos." in texts_by_num.get("2", "")
    assert "Texto do terceiro paragrafo, em outro capitulo." in texts_by_num.get("3", "")


if __name__ == "__main__":
    test_paragraph_pattern_type_a_matches_tab_separator()
    test_paragraph_pattern_type_a_matches_number_alone_on_own_line()
    test_paragraph_pattern_type_a_does_not_match_plain_space_separator()
    test_citations_book_paragraph_pattern_unaffected_by_default()
    test_notas_page_recognized_as_header_or_footer()
    test_indexer_does_not_leak_header_or_notas_page_into_paragraph()
    print("OK: todos os testes do perfil Tipo A passaram.")
