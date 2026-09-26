"""
Testes de regressao para dois bugs reais reportados pelo usuario, ambos
encontrados analisando amostras REAIS de dois PDFs diferentes do mesmo
livro ("La Palabra Hablada" / "Las Edades", cada capitulo um sermao
separado, paragrafos renumerados a partir de "1" em cada um, mas a
pagina impressa e continua pelo livro todo).

1. "essa pagina 2 nao esta aparecendo na busca" -- causa raiz A: as
   PRIMEIRAS paginas do livro (capa, ficha tecnica, pagina de abertura
   do 1o sermao), ANTES de QUALQUER numero de pagina real ja detectado
   no documento inteiro, caiam no fallback bruto (indice cru do PDF,
   ex. "1", "2", "3") como se fosse confiavel -- o numero de pagina
   REAL dessas paginas (confirmado so pela primeira ancora, algumas
   paginas depois) nunca era calculado. Conteudo real ficava indexado
   sob um numero de pagina que nao existe no livro.

2. Causa raiz B, mais grave: numa segunda amostra do MESMO livro (livro
   "Las Edades"), os paragrafos nao usam "N.\t" (ponto+tab, formato do
   livro "Los Siete Sellos", ja suportado) -- usam so "N " (numero +
   um espaco, sem ponto nenhum: "2 Pues es muy bueno...", "16 Ahora,
   estaban..."). O padrao antigo (PARAGRAPH_PATTERN_TYPE_A) exigia o
   ponto -- nesse formato NENHUM paragrafo seria reconhecido como
   inicio de paragrafo nenhum, o livro inteiro cairia numa unica
   entrada "Intro/Capa" corrida, e busca por paragrafo (ou por pagina,
   ja que a deteccao de "pagina tem conteudo" tambem depende do mesmo
   padrao) ficaria quebrada pro livro inteiro, nao so numa pagina.

Terceiro caso testado aqui (melhoria que apareceu ao investigar o bug
1): quando um trecho de paginas sem numero fica ENTRE DUAS paginas com
numero confirmado (nao so antes da 1a ou depois da ultima), e a
quantidade de paginas bate exatamente com a quantidade de numeros que
faltam, a resposta agora e calculada por contagem direta (garantida),
em vez da heuristica antiga de "pagina com paragrafo avanca, sem
paragrafo repete" -- que, verificado com dado real, podia deixar um
numero real "sobrando" sem nenhuma pagina (ver
test_interior_gap_with_exact_page_count_is_reconciled_directly).
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


def _new_db():
    tmp_dir = tempfile.mkdtemp()
    db_conn = DatabaseConnection(os.path.join(tmp_dir, "t.db"))
    DatabaseSchemaManager(db_conn).initialize_database()
    return db_conn, tmp_dir


def _register_document(db_conn, filename, title):
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            (filename, filename, title, "hash_" + filename, "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        conn.commit()
    return doc_id


# --------------------------------------------------------------- Caso 1


def _build_leading_pages_doc():
    doc = fitz.open()

    # Pagina 1: capa do livro/sermao -- so titulo, sem numero, sem
    # paragrafo nenhum.
    p0 = doc.new_page(width=432, height=612)
    p0.insert_text((150, 300), "EL SEXTUPLE PROPOSITO", fontsize=12)

    # Pagina 2: ficha tecnica/data -- sem numero, sem paragrafo.
    p1 = doc.new_page(width=432, height=612)
    p1.insert_text((150, 300), "30 de julio de 1961", fontsize=9)

    # Pagina 3: abertura do sermao -- sem numero, MAS com paragrafos
    # numerados reais (2. e 3.; o "1" fica implicito antes, sem numero
    # proprio, como no PDF real).
    p2 = doc.new_page(width=432, height=612)
    p2.insert_text((54, 80), "2.\t Texto do paragrafo dois, sem pagina impressa ainda.", fontsize=10)
    p2.insert_text((54, 120), "3.\t Texto do paragrafo tres, mesma pagina.", fontsize=10)

    # Pagina 4: primeira pagina com numero REAL detectado no documento
    # inteiro.
    p3 = doc.new_page(width=432, height=612)
    p3.insert_text((150, 40), "LA PALABRA HABLADA", fontsize=10)
    p3.insert_text((150, 45), "56", fontsize=10)
    p3.insert_text((54, 80), "4.\t Texto do paragrafo quatro, ja na pagina com numero real.", fontsize=10)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "abertura_livro.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_pages_before_first_anchor_get_inferred_label_not_raw_index():
    """BUG real: pagina 3 (indice 2) tinha conteudo de paragrafo real
    (2. e 3.) mas era gravada com o rotulo "3" (indice cru do PDF) em
    vez do numero real da pagina (55, calculado a partir da 1a ancora
    do livro, "56", na pagina seguinte)."""
    db_conn, _ = _new_db()
    pdf_path = _build_leading_pages_doc()
    doc_id = _register_document(db_conn, pdf_path, "Sermao Teste")

    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT pdf_page_index, printed_page_label, confidence FROM pages "
            "WHERE document_id=? ORDER BY pdf_page_index",
            (doc_id,),
        )
        rows = cur.fetchall()

    labels = [r["printed_page_label"] for r in rows]
    # Pagina 4 (indice 3) e a ancora real "56". Paginas antes (indices
    # 0,1,2) sao calculadas de tras pra frente: so a pagina 2 (indice 2,
    # que TEM paragrafo numerado) consome um numero -> "55". As duas
    # anteriores (sem paragrafo nenhum) repetem esse mesmo valor.
    assert labels == ["55", "55", "55", "56"], f"Sequencia errada: {labels}"

    # Confiança da pagina inferida (0.85) deve ficar abaixo do limiar de
    # deteccao real (>0.90) -- pra nao ser confundida com uma pagina
    # confirmada de verdade.
    assert rows[0]["confidence"] <= 0.90

    engine = SearchEngine(db_conn)
    results = engine.search(document_id=doc_id, page_label="55")
    assert len(results) >= 1, "Busca pela pagina 55 (inferida antes da 1a ancora) nao retornou nada"
    joined = " ".join(r.full_text for r in results)
    assert "paragrafo dois" in joined and "paragrafo tres" in joined


# --------------------------------------------------------------- Caso 2


def test_interior_gap_with_exact_page_count_is_reconciled_directly():
    """BUG real (2a amostra, livro 'Las Edades'): entre as paginas
    confirmadas '109' e '112' havia 2 paginas sem numero -- uma em
    branco e uma de abertura de capitulo (com paragrafo). A heuristica
    antiga (so avanca em pagina com paragrafo) fazia a pagina em branco
    'repetir' 109 e a de abertura virar 111, deixando '110' sem
    nenhuma pagina. Quando a contagem bate exatamente (112-109-1 = 2
    paginas faltando = 2 paginas sem rotulo), a nova logica calcula por
    contagem direta: 110 e 111, em ordem -- sem depender de qual pagina
    tem paragrafo ou nao."""
    doc = fitz.open()

    p0 = doc.new_page(width=432, height=612)
    p0.insert_text((150, 40), "LA VISION DE PATMOS", fontsize=10)
    p0.insert_text((150, 45), "109", fontsize=10)
    p0.insert_text((54, 80), "290.\t Texto do paragrafo duzentos e noventa.", fontsize=10)

    # Pagina em branco, sem numero, sem paragrafo nenhum.
    p1 = doc.new_page(width=432, height=612)

    # Abertura de capitulo -- sem numero, com paragrafo real.
    p2 = doc.new_page(width=432, height=612)
    p2.insert_text((150, 300), "LA EDAD DE LA IGLESIA DE EFESO", fontsize=12)
    p2.insert_text((54, 400), "2.\t Texto do paragrafo dois do capitulo novo.", fontsize=10)

    p3 = doc.new_page(width=432, height=612)
    p3.insert_text((150, 40), "LA PALABRA HABLADA", fontsize=10)
    p3.insert_text((150, 45), "112", fontsize=10)
    p3.insert_text((54, 80), "6.\t Texto do paragrafo seis, ja na pagina 112.", fontsize=10)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "lacuna_interna.pdf")
    doc.save(pdf_path)
    doc.close()

    db_conn, _ = _new_db()
    doc_id = _register_document(db_conn, pdf_path, "Teste Lacuna")
    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT printed_page_label FROM pages WHERE document_id=? ORDER BY pdf_page_index",
            (doc_id,),
        )
        labels = [r["printed_page_label"] for r in cur.fetchall()]

    assert labels == ["109", "110", "111", "112"], f"Sequencia errada: {labels}"

    engine = SearchEngine(db_conn)
    results_110 = engine.search(document_id=doc_id, page_label="110")
    assert len(results_110) == 0, "Pagina 110 (em branco, sem conteudo) nao deveria ter resultado de busca"

    results_111 = engine.search(document_id=doc_id, page_label="111")
    assert len(results_111) == 1, "Busca pela pagina 111 (abertura de capitulo, reconciliada) nao encontrou nada"
    assert "capitulo novo" in results_111[0].full_text


# --------------------------------------------------------------- Caso 3


def test_paragraph_pattern_type_a_accepts_number_space_format_without_period():
    """Formato real confirmado numa 2a amostra do usuario ('Las
    Edades'): paragrafo comeca so com 'N ' (numero + espaco), sem ponto
    e sem tab -- diferente do formato ja suportado ('N.\t')."""
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("2 Pues es muy bueno, estar juntos de nuevo")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("16 Ahora, estaban pasando por ahi")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("279 ¿Que fue lo que dijo la Receta?")
    # Formato antigo continua funcionando.
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("13.\t Ahora, yo no se")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("4.\t")


def test_paragraph_pattern_type_a_rejects_number_space_lowercase_continuation():
    """Frase comum comecando com numero + palavra MINUSCULA (ex.: data
    '6 de agosto de 1961') nao pode ser confundida com inicio de
    paragrafo -- so maiuscula ou abertura de interrogacao/exclamacao em
    espanhol (¿/¡) depois do espaco conta."""
    assert not PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("6 de agosto de 1961")
    assert not PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("30 de julio de 1961, P.M.")


def test_no_period_paragraph_format_is_indexed_and_searchable():
    doc = fitz.open()

    p0 = doc.new_page(width=432, height=612)
    p0.insert_text((150, 40), "LA EDAD DE LA IGLESIA DE EFESO", fontsize=10)
    p0.insert_text((150, 45), "111", fontsize=10)
    p0.insert_text((54, 80), "2 Pues es muy bueno, estar juntos de nuevo en el servicio.", fontsize=10)
    p0.insert_text((54, 120), "3 Ahora, mi hermano fue y trajo un pizarron.", fontsize=10)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "sem_ponto.pdf")
    doc.save(pdf_path)
    doc.close()

    db_conn, _ = _new_db()
    doc_id = _register_document(db_conn, pdf_path, "Teste Sem Ponto")
    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)

    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT paragraph_number, text FROM paragraphs p JOIN pages pg ON p.page_id=pg.id "
            "WHERE pg.document_id=? ORDER BY p.id",
            (doc_id,),
        )
        rows = cur.fetchall()

    numbers = [r["paragraph_number"] for r in rows]
    # Sem a correcao, "2" e "3" nunca seriam reconhecidos como inicio de
    # paragrafo -- tudo cairia numa unica entrada "Intro/Capa".
    assert "2" in numbers, f"Paragrafo '2' (formato sem ponto) nao foi reconhecido: {numbers}"
    assert "3" in numbers, f"Paragrafo '3' (formato sem ponto) nao foi reconhecido: {numbers}"

    engine = SearchEngine(db_conn)
    results = engine.search(document_id=doc_id, paragraph_num="2")
    assert len(results) == 1, "Busca pelo paragrafo 2 (formato sem ponto) nao encontrou nada"
    assert "estar juntos de nuevo" in results[0].full_text


if __name__ == "__main__":
    test_pages_before_first_anchor_get_inferred_label_not_raw_index()
    test_interior_gap_with_exact_page_count_is_reconciled_directly()
    test_paragraph_pattern_type_a_accepts_number_space_format_without_period()
    test_paragraph_pattern_type_a_rejects_number_space_lowercase_continuation()
    test_no_period_paragraph_format_is_indexed_and_searchable()
    print("OK: paginas de abertura do livro, lacuna interna reconciliada, e formato de paragrafo sem ponto.")
