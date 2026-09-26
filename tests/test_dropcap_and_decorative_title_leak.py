"""
Testes de regressao para tres bugs reais, todos encontrados no MESMO
PDF de amostra real ("Setenta Semanas de Daniel"/"Las Edades" -- livro
"La Palabra Hablada"), depois que o usuario reimportou com a v2.6.2 e
mandou prints do resultado da busca de verdade no app:

1. A letra capitular decorativa de abertura de sermao (ex.: "M" grande
   de "Muy asombrado...") vem como linha PROPRIA no PDF, separada do
   resto da palavra. O filtro de "linha toda maiuscula = cabecalho"
   (pensado pra titulos tipo "LA PALABRA HABLADA") classificava essa
   letra sozinha como cabecalho e DESCARTAVA ela -- a busca mostrava
   "uy asombrado..." sem o M.

2. O bloco decorativo de abertura de capitulo (titulo do sermao, nome
   do autor, data/local) nesse livro e LARGO (varias linhas, quase a
   largura toda da pagina) -- o filtro antigo so reconhecia bloco
   ESTREITO e centralizado (valido pro livro "Los Siete Sellos", onde
   esse bloco e só uma linha de data/hino). Sem reconhecer esse
   formato, o bloco inteiro (titulo+autor+data) virava "texto normal"
   e colava no final do ULTIMO paragrafo do capitulo ANTERIOR, que
   ainda estava aberto -- e o paragrafo do capitulo anterior nunca
   fechava sozinho (só fecha quando aparece um "N." novo), entao até o
   texto de introducao do sermao novo (sem numero) ficava grudado
   nele.

3. Bug introduzido E CORRIGIDO na mesma investigacao: o filtro novo de
   "linha com fonte maior que o corpo = decorativa" (pra resolver o
   bug 2) usava o tamanho MAXIMO da linha -- esses sermoes usam
   negrito num trecho CURTO pra marcar enfase/gagueira (ex.: "un-un
   Dodge", só o "-un" maior). Isso fazia uma frase real de conteudo
   (nao decorativa nenhuma) ser descartada por inteiro so por causa de
   uma palavra em destaque. Corrigido usando a media ponderada por
   caractere da linha, nao o maximo.
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


def _new_db():
    tmp_dir = tempfile.mkdtemp()
    db_conn = DatabaseConnection(os.path.join(tmp_dir, "t.db"))
    DatabaseSchemaManager(db_conn).initialize_database()
    return db_conn


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


def _build_chapter_boundary_doc():
    """Reproduz, em miniatura, o layout real: capítulo em andamento
    (paragrafo "185" aberto) -> pagina de abertura do capitulo novo,
    SEM numero impresso, com titulo+autor+data (bloco LARGO, fonte
    maior) + letra capitular ("M") + uma frase com uma palavra em
    negrito/maior no meio (enfase) + inicio do texto de introducao
    (sem numero) -> paragrafo numerado "2." do capitulo novo."""
    doc = fitz.open()

    # Página 1 ("110" impresso): parágrafo 185 do capítulo anterior,
    # fica aberto (não fecha nesta página). insert_text (não
    # TextWriter) preserva o "\t" literal na string, igual já
    # confirmado nos outros testes deste projeto -- é o que faz o "\t"
    # bater no padrão PARAGRAPH_PATTERN_TYPE_A.
    p0 = doc.new_page(width=396, height=612)
    p0.insert_text((150, 40), "CAPITULO ANTERIOR", fontsize=10)
    p0.insert_text((150, 45), "110", fontsize=10)
    p0.insert_text((36, 80), "185.\t Texto do paragrafo cento e oitenta e cinco que fica aberto.", fontsize=12)

    # Página 2: abertura do capítulo novo -- SEM número impresso.
    p1 = doc.new_page(width=396, height=612)
    # Título (bold, grande) -- bloco LARGO, não estreito/centralizado.
    p1.insert_text((36, 150), "LA EDAD DE LA IGLESIA DE EFESO ESTE TITULO E BEM LARGO", fontsize=18)
    # Autor + data (um pouco maior que o corpo) -- também largo.
    p1.insert_text((36, 200), "Rev. William Marrion Branham", fontsize=14)
    p1.insert_text((36, 220), "30 de julio de 1961, P.M. Tabernaculo Branham", fontsize=14)
    # Letra capitular "M" sozinha, bem maior que o corpo (~12pt aqui).
    p1.insert_text((36, 260), "M", fontsize=34)
    # Continuação do texto (corpo, 12pt) -- "uy asombrado..." precisa
    # virar "Muy asombrado..." depois de colar com o M.
    p1.insert_text((36, 300), "uy asombrado con las cosas, dijo el.", fontsize=12)
    # Frase com uma palavra em destaque (maior) no MEIO da mesma linha
    # de base -- NAO pode sumir a linha inteira por causa disso.
    p1.insert_text((36, 340), "Alguien aqui maneja un", fontsize=12)
    p1.insert_text((190, 340), "-un", fontsize=17)
    p1.insert_text((215, 340), " Dodge nuevo, de verdad.", fontsize=12)
    # Início do parágrafo numerado do capítulo novo.
    p1.insert_text((36, 380), "2.\t Texto do segundo paragrafo do capitulo novo.", fontsize=12)

    # Página 3 ("112" impresso): capítulo novo continua normalmente.
    p2 = doc.new_page(width=396, height=612)
    p2.insert_text((150, 40), "CAPITULO NOVO", fontsize=10)
    p2.insert_text((150, 45), "112", fontsize=10)
    p2.insert_text((36, 80), "3.\t Texto do terceiro paragrafo, capitulo novo continuando.", fontsize=12)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "abertura_com_dropcap.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def _index(pdf_path):
    db_conn = _new_db()
    doc_id = _register_document(db_conn, pdf_path, "Teste Dropcap")
    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)
    return db_conn, doc_id


def test_dropcap_letter_is_glued_to_next_word_not_dropped():
    db_conn, doc_id = _index(_build_chapter_boundary_doc())
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT text FROM paragraphs p JOIN pages pg ON p.page_id=pg.id "
            "WHERE pg.document_id=? AND p.paragraph_number='Intro/Capa' ORDER BY p.id",
            (doc_id,),
        )
        rows = cur.fetchall()

    intro_texts = [r["text"] for r in rows]
    assert any("Muy asombrado" in t for t in intro_texts), (
        f"Letra capitular 'M' nao foi colada corretamente (esperado 'Muy asombrado'): {intro_texts!r}"
    )
    assert not any("uy asombrado" in t and "Muy asombrado" not in t for t in intro_texts), (
        "BUG: letra capitular foi descartada (sobrou 'uy asombrado' sem o M)"
    )


def test_wide_title_author_date_block_does_not_leak_into_previous_paragraph():
    db_conn, doc_id = _index(_build_chapter_boundary_doc())
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT paragraph_number, text FROM paragraphs p JOIN pages pg ON p.page_id=pg.id "
            "WHERE pg.document_id=? ORDER BY p.id",
            (doc_id,),
        )
        rows = cur.fetchall()

    text_185 = next((r["text"] for r in rows if r["paragraph_number"] == "185"), "")
    assert "EDAD DE LA IGLESIA" not in text_185.upper(), (
        f"BUG: titulo do capitulo novo vazou pro final do paragrafo 185 (anterior): {text_185!r}"
    )
    assert "William Marrion Branham" not in text_185, (
        f"BUG: bloco autor/data vazou pro final do paragrafo 185 (anterior): {text_185!r}"
    )
    assert text_185.strip().endswith("aberto."), f"Paragrafo 185 nao fechou limpo: {text_185!r}"


def test_intro_text_of_new_chapter_becomes_its_own_entry_not_glued_to_previous_paragraph():
    db_conn, doc_id = _index(_build_chapter_boundary_doc())
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT paragraph_number, text FROM paragraphs p JOIN pages pg ON p.page_id=pg.id "
            "WHERE pg.document_id=? ORDER BY p.id",
            (doc_id,),
        )
        rows = cur.fetchall()

    # A primeira entrada "Intro/Capa" (vazia) é um artefato conhecido e
    # esperado: o indexador sempre abre uma entrada de introdução antes
    # do 1º parágrafo numerado do documento, mesmo quando esse 1º
    # parágrafo já aparece de cara (caso do "185." na página 1 deste
    # teste) -- fica vazia e não entra na busca (ver _close_paragraph).
    # O que importa aqui é que exista uma SEGUNDA entrada "Intro/Capa",
    # não-vazia, pro texto de introdução do capítulo NOVO -- e que ele
    # não tenha ficado colado no final do parágrafo "185" (isso já é
    # coberto pelo teste anterior).
    intro_rows = [r for r in rows if r["paragraph_number"] == "Intro/Capa"]
    non_empty_intros = [r for r in intro_rows if r["text"].strip()]
    assert len(non_empty_intros) == 1, (
        f"Esperava exatamente 1 entrada 'Intro/Capa' NÃO VAZIA (a do capítulo novo), achou: {intro_rows}"
    )


def test_emphasized_word_inside_a_line_does_not_drop_the_whole_sentence():
    """BUG introduzido e corrigido na mesma investigação: usar o
    tamanho MÁXIMO da linha (em vez de média ponderada) fazia uma
    frase real sumir só porque uma palavra dentro dela estava em
    destaque (maior/negrito)."""
    db_conn, doc_id = _index(_build_chapter_boundary_doc())
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT text FROM paragraphs p JOIN pages pg ON p.page_id=pg.id "
            "WHERE pg.document_id=? AND p.paragraph_number='Intro/Capa' AND p.text != ''",
            (doc_id,),
        )
        text = cur.fetchone()["text"]

    assert "Alguien aqui maneja un" in text, f"BUG: frase com palavra em destaque sumiu: {text!r}"
    assert "Dodge nuevo, de verdad." in text, f"BUG: frase com palavra em destaque sumiu: {text!r}"


def test_search_finds_new_chapter_paragraph_2_after_boundary():
    db_conn, doc_id = _index(_build_chapter_boundary_doc())
    engine = SearchEngine(db_conn)
    results = engine.search(document_id=doc_id, paragraph_num="2")
    assert len(results) == 1, "Busca pelo paragrafo 2 do capitulo novo nao encontrou nada"
    assert "segundo paragrafo do capitulo novo" in results[0].full_text


if __name__ == "__main__":
    test_dropcap_letter_is_glued_to_next_word_not_dropped()
    test_wide_title_author_date_block_does_not_leak_into_previous_paragraph()
    test_intro_text_of_new_chapter_becomes_its_own_entry_not_glued_to_previous_paragraph()
    test_emphasized_word_inside_a_line_does_not_drop_the_whole_sentence()
    test_search_finds_new_chapter_paragraph_2_after_boundary()
    print("OK: letra capitular reconstituida, bloco decorativo largo filtrado, fronteira de capitulo fecha limpo.")
