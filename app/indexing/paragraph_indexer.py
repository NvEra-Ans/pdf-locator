import fitz
import json
from app.indexing.base import BaseIndexer
from app.database.connection import DatabaseConnection
from analyzer.pattern_detector import PatternDetector
from analyzer.layout import order_blocks_reading_order

class ParagraphIndexer(BaseIndexer):
    """Indexador específico para documentos baseados em Páginas e Parágrafos (Tipo A)."""

    def __init__(self, db_conn: DatabaseConnection):
        self.db_conn = db_conn

    def index_document(self, doc_id: int, pdf_path: str) -> bool:
        doc = fitz.open(pdf_path)
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()

            # BUG real encontrado com dado do usuario (livro "La Revelacion
            # de Los Siete Sellos"): current_para_num/current_para_text
            # antes eram declarados DENTRO do loop de paginas (resetados a
            # cada pagina nova). Isso fazia o texto de um paragrafo que
            # comeca numa pagina e continua na seguinte (comum em sermao
            # corrido) ser CORTADO -- a parte que sobrava no comeco da
            # proxima pagina, antes do proximo numero de paragrafo aparecer,
            # nao tinha onde ser salva (current_para_num virava None de
            # novo) e era perdida por completo, sem erro nenhum. Corrigido
            # movendo esse estado pra FORA do loop de paginas, igual ja
            # funciona no citations_indexer.py (active_entry_id/text).
            current_para_id = None
            current_para_num = None
            current_para_text = []
            current_bbox = None
            printed_label = "1"

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                width, height = page.rect.width, page.rect.height
                page_dict = page.get_text("dict")
                raw_blocks = page_dict.get("blocks", [])

                printed_label = str(page_idx + 1)
                page_conf = 0.90

                # 1. Tenta identificar o rótulo de página impresso no cabeçalho/rodapé
                for b in raw_blocks:
                    if b.get("type") == 0:
                        for line in b.get("lines", []):
                            line_text = "".join([s.get("text", "") for s in line.get("spans", [])]).strip()
                            res = PatternDetector.analyze_text_span(line_text, b.get("bbox", [0, 0, 0, 0]), width, height)
                            if res["is_page_number_candidate"] and res["confidence_page_label"] > page_conf:
                                printed_label = res["detected_label"]
                                page_conf = res["confidence_page_label"]

                cursor.execute(
                    "INSERT INTO pages (document_id, pdf_page_index, printed_page_label, confidence) VALUES (?, ?, ?, ?)",
                    (doc_id, page_idx, printed_label, page_conf)
                )
                page_db_id = cursor.lastrowid

                # 2. Reordena os blocos em ordem de leitura real (coluna esquerda
                # inteira, depois coluna direita inteira) antes de processar
                # parágrafos, para não cortar parágrafos que atravessam colunas.
                blocks = order_blocks_reading_order(raw_blocks, width, height)

                # IMPORTANTE: o teste de "isso começa um novo parágrafo?" precisa
                # ser feito LINHA por LINHA, não por bloco inteiro — o PyMuPDF às
                # vezes agrupa no mesmo bloco o fim de um parágrafo e o início do
                # próximo (ex.: uma linha de atribuição/rodapé seguida, na linha
                # de baixo, já pelo número do parágrafo seguinte). Testar o bloco
                # inteiro concatenado faz esse número cair no meio da string e
                # nunca bater no padrão (ancorado no início), fundindo os dois
                # parágrafos em um só.
                for b in blocks:
                    bbox = b.get("bbox")
                    for line in b.get("lines", []):
                        line_text = "".join([s.get("text", "") for s in line.get("spans", [])]).strip()
                        if not line_text:
                            continue

                        res = PatternDetector.analyze_text_span(
                            line_text, bbox, width, height,
                            paragraph_pattern=PatternDetector.PARAGRAPH_PATTERN_TYPE_A,
                        )

                        # Número de página solto, marcador de Parte A/B (nao
                        # deveria aparecer nesse perfil, mas por seguranca) ou
                        # cabecalho/rodape repetido do livro (titulo da obra,
                        # titulo do capitulo, ou paginas quase em branco tipo
                        # "Notas" entre capitulos): nao e conteudo de
                        # paragrafo nenhum, nao deve acumular no corpo.
                        if res["is_page_number_candidate"] or res["is_part_label_candidate"] or res["is_header_or_footer"]:
                            continue

                        # Ainda não há parágrafo ativo (ex.: texto de capa/
                        # introdução antes do primeiro "N." do livro): abre
                        # uma entrada de introdução, igual ja acontece no
                        # citations_indexer.py, pra nao perder esse texto.
                        if current_para_id is None:
                            current_para_id = self._start_paragraph(cursor, page_db_id, "Intro/Capa")
                            current_para_num = "Intro/Capa"
                            current_para_text = []
                            current_bbox = bbox

                        # Linha inicia um novo parágrafo numerado -> fecha o
                        # anterior (que pode ter chunks em varias paginas
                        # diferentes) e abre este.
                        if res["is_paragraph_candidate"]:
                            self._close_paragraph(cursor, current_para_id, doc_id, printed_label, current_para_text)
                            current_para_num = res["detected_paragraph_num"]
                            current_para_id = self._start_paragraph(cursor, page_db_id, current_para_num)
                            current_para_text = [line_text]
                            current_bbox = bbox
                        else:
                            current_para_text.append(line_text)

                        # Chunk por pagina, igual ao entry_chunks do Tipo B --
                        # e o que permite reconstruir o texto exato de UMA
                        # pagina fisica (busca por pagina), mesmo quando um
                        # paragrafo comeca numa pagina e continua na
                        # seguinte.
                        cursor.execute(
                            "INSERT INTO paragraph_chunks (paragraph_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
                            (current_para_id, page_db_id, line_text, json.dumps(bbox))
                        )

            # Fecha o último parágrafo pendente ao final do documento
            if current_para_id is not None:
                self._close_paragraph(cursor, current_para_id, doc_id, printed_label, current_para_text)

            conn.commit()
        return True

    def _start_paragraph(self, cursor, page_id: int, paragraph_number: str) -> int:
        """Cria a linha em paragraphs e retorna o id (o texto é preenchido depois, em _close_paragraph).
        `page_id` aqui é só a página onde o parágrafo ABRIU -- para saber
        exatamente o que aparece em cada página física (parágrafo que
        atravessa página), use paragraph_chunks, não este campo."""
        cursor.execute(
            "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text) VALUES (?, ?, ?, ?)",
            (page_id, paragraph_number, "", "")
        )
        return cursor.lastrowid

    def _close_paragraph(self, cursor, paragraph_id: int, doc_id: int, printed_label: str, text_parts) -> None:
        """Consolida o texto acumulado do parágrafo (todos os chunks, de
        todas as páginas por onde ele passou) e grava em paragraphs +
        fts_paragraphs."""
        full_text = " ".join(text_parts).strip()
        norm_text = self.normalize_text(full_text)

        cursor.execute("SELECT paragraph_number FROM paragraphs WHERE id = ?", (paragraph_id,))
        row = cursor.fetchone()
        paragraph_number = row[0] if row else ""

        cursor.execute(
            "UPDATE paragraphs SET text = ?, normalized_text = ? WHERE id = ?",
            (full_text, norm_text, paragraph_id)
        )

        if not full_text:
            # Parágrafo "casca vazia" (abriu mas não acumulou nenhum texto
            # real) -- mantém a linha em paragraphs (dado bruto, útil pra
            # depurar), mas não entra no índice de busca.
            return

        cursor.execute(
            "INSERT INTO fts_paragraphs VALUES (?, ?, ?, ?, ?)",
            (paragraph_id, doc_id, printed_label, paragraph_number, norm_text)
        )
