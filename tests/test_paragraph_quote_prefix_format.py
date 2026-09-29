"""
Teste de regressao para bug real encontrado com tools/verificar_estrutura_pdf.py
(ANTES do usuario relatar como bug de verdade -- achado rodando o script
novo contra o PDF real e completo do livro "Demonologia", perfil Tipo A).

O 2o formato de paragrafo ("N " sem ponto, exige maiuscula/¿/¡ logo apos o
espaco) nao reconhecia paragrafos cujo texto abre com uma citacao entre
aspas curvas, ex.: '31 "Pero dejeme Ud. ir alla al Africa...'. Confirmado
caractere por caractere no texto real extraido do PDF: e U+201C (aspa dupla
curva de abertura), nao aspa reta ("). Confirmado tambem que os 9 numeros
afetados no livro real (31, 64, 70, 91, 94, 100, 117, 176, 206) encaixam
exatamente na sequencia -- o numero anterior E o seguinte de cada um ja
eram reconhecidos normalmente -- confirmando que sao paragrafos de verdade,
nao coincidencia. Sem esse ajuste, cada um ficava colado no final do texto
do paragrafo anterior.
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


def test_paragraph_pattern_type_a_accepts_curly_quote_prefix():
    # U+201C -- aspa dupla curva de abertura, a mesma achada no PDF real.
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("31 “Pero déjeme Ud. ir allá al África")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("100 “¿Le aman? Lamento haberlos tenido")
    # Os formatos ja suportados continuam funcionando.
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("13.\t Ahora, yo no se")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("16 Ahora, estaban pasando")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("1. - Señor Amado, te damos gracias")
    assert PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("164 . - Le dije: algo")
    # Uma referencia de versiculo no meio de frase continua NAO batendo.
    assert not PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match("100:872 alguma coisa")


def _build_doc():
    doc = fitz.open()
    p0 = doc.new_page(width=396, height=612)
    p0.insert_text((150, 40), "DEMONOLOGIA", fontsize=10)
    p0.insert_text((150, 45), "8", fontsize=10)
    p0.insert_text((36, 80), "30.\t Texto do paragrafo trinta que fica aberto.", fontsize=12)
    # Paragrafo 31 abre com aspa -- usa aspa reta (") aqui, nao a curva
    # (U+201C) confirmada no PDF real, porque a fonte base14 do PyMuPDF
    # (usada por insert_text sem fonte customizada) nao tem esse glifo
    # unicode e o substitui por um caractere errado, quebrando o teste.
    # A cobertura do caractere curvo de verdade fica no teste de regex
    # puro acima (test_paragraph_pattern_type_a_accepts_curly_quote_prefix)
    # -- a aspa reta exercita o MESMO ramo do padrao (o grupo de aspas
    # aceitas inclui as duas).
    p0.insert_text((36, 120), "31 \"Pero déjeme Ud. ir allá al África, a la tribu.", fontsize=12)
    p0.insert_text((36, 160), "32.\t Texto do paragrafo trinta e dois, normal.", fontsize=12)

    tmp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp_dir, "demonologia.pdf")
    doc.save(pdf_path)
    doc.close()

    db_conn = DatabaseConnection(os.path.join(tmp_dir, "demonologia.db"))
    DatabaseSchemaManager(db_conn).initialize_database()
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
            ("demonologia.pdf", pdf_path, "Demonologia", "hash_demonologia", "PARAGRAPH_BOOK"),
        )
        doc_id = cur.lastrowid
        conn.commit()

    ParagraphIndexer(db_conn).index_document(doc_id, pdf_path)
    return db_conn, doc_id


def test_paragraph_starting_with_quote_becomes_its_own_entry():
    db_conn, doc_id = _build_doc()
    with db_conn.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT paragraph_number, text FROM paragraphs p JOIN pages pg ON p.page_id=pg.id "
            "WHERE pg.document_id=? ORDER BY p.id",
            (doc_id,),
        )
        rows = cur.fetchall()

    text_30 = next((r["text"] for r in rows if r["paragraph_number"] == "30"), "")
    text_31 = next((r["text"] for r in rows if r["paragraph_number"] == "31"), "")

    assert "Pero déjeme" not in text_30, (
        f"BUG: paragrafo 31 (abre com aspa) vazou pro final do paragrafo 30: {text_30!r}"
    )
    assert "Pero déjeme" in text_31, f"Paragrafo 31 nao abriu entrada propria: {rows!r}"


def test_search_by_paragraph_31_finds_the_quoted_text():
    db_conn, doc_id = _build_doc()
    engine = SearchEngine(db_conn)
    results = engine.search(document_id=doc_id, paragraph_num="31")
    assert len(results) == 1, "Busca pelo paragrafo 31 (abre com aspa curva) nao encontrou nada"
    assert "Pero déjeme" in results[0].full_text


if __name__ == "__main__":
    test_paragraph_pattern_type_a_accepts_curly_quote_prefix()
    test_paragraph_starting_with_quote_becomes_its_own_entry()
    test_search_by_paragraph_31_finds_the_quoted_text()
    print("OK: paragrafo iniciando com aspa curva reconhecido corretamente.")
