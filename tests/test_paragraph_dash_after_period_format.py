"""
Teste de regressao pro BUG real reportado pelo usuario ("página 1 não
aparece na busca"), confirmado com o PDF COMPLETO (32 páginas) do
livro "Sobre las Alas de una Blanca Paloma" (perfil Tipo A).

Terceiro formato de numeração de parágrafo encontrado neste projeto:
"N. - " -- número, PONTO, espaço, TRAÇO, espaço (ex.: "1. - Señor
Amado, te damos gracias..."). Diferente tanto do formato "N.\t" (Los
Siete Sellos) quanto do formato "N " sem ponto (Las Edades), ambos já
suportados.

Confirmado direto no texto extraído do PDF real: a 1ª página de
conteúdo do livro (a abertura, sem número impresso -- a próxima página
já mostra "2") tem justamente esse formato ("1. - Señor Amado...",
"2. - Bendice...", etc.). Sem reconhecer esse formato, essa página não
era vista como "página com parágrafo", herdava por engano o número da
página seguinte ("2"), e a busca pela página 1 (real) não encontrava
nada -- exatamente a mesma classe de bug já corrigida antes (páginas
sem número impresso), com uma 3ª variação de formato de parágrafo.
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
from analyzer.pattern_detector import PatternDetector


def test_paragraph_pattern_type_a_accepts_period_dash_format():
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("1. - Señor Amado, te damos gracias")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("54. - Si yo me fumara un cigarrillo")
    # Os dois formatos ja suportados continuam funcionando.
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("13.\t Ahora, yo no se")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("16 Ahora, estaban pasando")


def test_paragraph_pattern_type_a_accepts_space_before_period_dash_variant():
    """Achado com tools/verificar_estrutura_pdf.py, rodado sobre o PDF
    completo (real) de "Sobre las Alas de una Blanca Paloma" ANTES do
    usuário relatar isso como bug: o parágrafo 164 vem como
    "164 . - Le dije..." -- com um espaço entre o número e o ponto --
    enquanto os vizinhos 163 e 165 vêm sem esse espaço ("163. - ",
    "165. - "). Confirmado direto no texto extraído real (índice de página
    21). Provável inconsistência de diagramação do PDF de origem, não do
    indexador -- mas sem tolerar esse espaço opcional, o parágrafo 164
    ficava colado no final do texto do parágrafo 163."""
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("164 . - Le dije: “Pero, señor”")
    # Garante que isso não abriu brecha pra outros formatos incomuns.
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("1. - Señor Amado, te damos gracias")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("13.\t Ahora, yo no se")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("16 Ahora, estaban pasando")


def _build_doc():
    doc = fitz.open()

    # Página 1 (índice 0): abertura do livro -- SEM número impresso,
    # parágrafos no formato "N. - ".
    p0 = doc.new_page(width=396, height=612)
    p0.insert_text((54, 40), "EN LAS ALAS DE UNA PALOMA BLANCA COMO LA NIEVE", fontsize=11)
    p0.insert_text((54, 60), "Inclinemos nuestras cabezas:", fontsize=11)
    p0.insert_text((54, 80), "1. - Señor Amado, te damos gracias por la promesa.", fontsize=11)
    p0.insert_text((54, 100), "2. - Bendice a aquellos que han viajado largas distancias.", fontsize=11)

    # Página 2 (índice 1): número impresso real "2".
    p1 = doc.new_page(width=396, height=612)
    p1.insert_text((150, 40), "LA PALABRA HABLADA", fontsize=10)
    p1.insert_text((150, 45), "2", fontsize=10)
    p1.insert_text((54, 80), "3. - Dios bendiga a cada uno de ustedes.", fontsize=11)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "paloma.pdf")
    doc.save(pdf_path)
    doc.close()

    db_conn = DatabaseConnection(os.path.join(tmp_dir, "paloma.db"))
    DatabaseSchemaManager(db_conn).initialize_database()
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("paloma.pdf", pdf_path, "Sobre las Alas", "hash_paloma", "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        conn.commit()

    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)
    return db_conn, doc_id


def test_first_unnumbered_page_is_inferred_as_page_1_not_page_2():
    db_conn, doc_id = _build_doc()
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT printed_page_label FROM pages WHERE document_id=? ORDER BY pdf_page_index",
            (doc_id,),
        )
        labels = [r["printed_page_label"] for r in cur.fetchall()]

    assert labels == ["1", "2"], f"Sequência de páginas errada: {labels}"


def test_search_by_page_1_finds_the_opening_prayer_content():
    db_conn, doc_id = _build_doc()
    engine = SearchEngine(db_conn)
    results = engine.search(document_id=doc_id, page_label="1")
    assert len(results) == 1, "Busca pela página 1 (formato 'N. - ') não encontrou nada"
    assert "Señor Amado" in results[0].full_text
    assert "Bendice a aquellos" in results[0].full_text


def test_search_by_paragraph_1_finds_correct_text():
    db_conn, doc_id = _build_doc()
    engine = SearchEngine(db_conn)
    results = engine.search(document_id=doc_id, paragraph_num="1")
    assert len(results) == 1, "Busca pelo parágrafo 1 (formato 'N. - ') não encontrou nada"
    assert "Señor Amado" in results[0].full_text


if __name__ == "__main__":
    test_paragraph_pattern_type_a_accepts_period_dash_format()
    test_first_unnumbered_page_is_inferred_as_page_1_not_page_2()
    test_search_by_page_1_finds_the_opening_prayer_content()
    test_search_by_paragraph_1_finds_correct_text()
    print("OK: formato de paragrafo 'N. - ' reconhecido, pagina 1 inferida corretamente.")
