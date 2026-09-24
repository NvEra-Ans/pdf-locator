"""
Teste de regressao para bug real reportado pelo usuario (print de tela):
quando o PDF quebra uma palavra no fim da linha por causa da margem
(hifenizacao de justificacao -- comum em texto corrido em espanhol/
portugues), o texto extraido mostrava a palavra partida com hifen E
espaco sobrando (ex.: "es- trechó" em vez de "estrechó").

Causa raiz encontrada em DOIS lugares independentes, que precisaram da
mesma correcao:
1. app/indexing/base.py (BaseIndexer.join_text_parts, usado por
   paragraph_indexer.py e citations_indexer.py ao fechar um paragrafo/
   extrato).
2. app/search/engine.py (reconstrucao de texto por PAGINA a partir de
   paragraph_chunks) -- tinha seu PROPRIO join ingenuo, separado do
   primeiro, entao corrigir só o indexador nao bastava pra busca por
   pagina continuar mostrando o bug.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import tempfile

from app.indexing.base import BaseIndexer
from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.indexing.paragraph_indexer import ParagraphIndexer
from app.search.engine import SearchEngine


def test_join_text_parts_rejoins_line_wrap_hyphenation():
    # Caso real do print de tela: "es-" no fim de uma linha, "trechó" no
    # comeco da proxima -- deve virar "estrechó", sem hifen nem espaco.
    assert BaseIndexer.join_text_parts(["Y lo es-", "trechó a lo largo"]) == \
        "Y lo estrechó a lo largo"


def test_join_text_parts_keeps_space_for_non_hyphenated_lines():
    assert BaseIndexer.join_text_parts(["Primeira linha", "segunda linha"]) == \
        "Primeira linha segunda linha"


def test_join_text_parts_does_not_merge_number_ranges_or_real_dashes():
    # Intervalo de datas quebrado no fim da linha (raro, mas nao deve
    # virar "19751976") -- digito antes do hifen, nao letra minuscula.
    assert BaseIndexer.join_text_parts(["de 1975-", "1976"]) == "de 1975- 1976"
    # Hifen seguido de maiuscula (inicio de frase/nome proprio) tambem
    # nao deve ser tratado como quebra de palavra.
    assert BaseIndexer.join_text_parts(["Isso é claro-", "Realmente é."]) == \
        "Isso é claro- Realmente é."
    # Travessao duplo/travessão real não é hífen de quebra de linha.
    assert BaseIndexer.join_text_parts(["Uma pausa--", "continuação"]) == \
        "Uma pausa-- continuação"


def test_paragraph_indexer_and_page_search_rejoin_hyphenated_word():
    """Reproduz o caso real de ponta a ponta: PDF com uma palavra quebrada
    no fim da linha dentro de um parágrafo, e confirma que tanto o texto
    salvo no parágrafo quanto a reconstrução por PÁGINA (usada na Tela de
    Leitura/painel principal) mostram a palavra unida."""
    doc = fitz.open()
    page = doc.new_page(width=432, height=612)
    page.insert_text((150, 40), "EL PRIMER SELLO", fontsize=10)
    page.insert_text((150, 45), "77", fontsize=10)
    page.insert_text((54, 80), "1.\tHabía una vez un camino a lo largo del río. Y lo es-", fontsize=10)
    page.insert_text((54, 95), "trechó a lo largo del correcto.", fontsize=10)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "test_hyphen.pdf")
    doc.save(pdf_path)
    doc.close()

    db_path = os.path.join(tmp_dir, "test_hyphen.db")
    db_conn = DatabaseConnection(db_path)
    DatabaseSchemaManager(db_conn).initialize_database()

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("t.pdf", pdf_path, "Teste", "hash_hyphen", "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        conn.commit()

    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT text FROM paragraphs WHERE paragraph_number = '1'")
        row = cur.fetchone()

    assert row is not None
    assert "estrechó" in row[0], f"palavra nao foi reunida corretamente: {row[0]!r}"
    assert "es- trechó" not in row[0] and "es-trechó" not in row[0]

    engine = SearchEngine(db_conn)
    results = engine.search(document_id=doc_id, page_label="77")
    assert len(results) == 1
    assert "estrechó" in results[0].full_text, \
        f"reconstrucao por pagina nao reuniu a palavra: {results[0].full_text!r}"


if __name__ == "__main__":
    test_join_text_parts_rejoins_line_wrap_hyphenation()
    test_join_text_parts_keeps_space_for_non_hyphenated_lines()
    test_join_text_parts_does_not_merge_number_ranges_or_real_dashes()
    test_paragraph_indexer_and_page_search_rejoin_hyphenated_word()
    print("OK: palavras partidas no fim da linha voltam a ser uma só.")
