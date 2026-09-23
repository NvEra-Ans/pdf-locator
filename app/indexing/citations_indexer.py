import fitz
import json
from app.indexing.base import BaseIndexer
from app.database.connection import DatabaseConnection
from analyzer.pattern_detector import PatternDetector
from analyzer.layout import order_blocks_reading_order

class CitationsIndexer(BaseIndexer):
    """Indexador específico para livros de citações/extratos numerados (Perfil Tipo B)."""

    # A partir desta página (índice 0 do PyMuPDF, ou seja, "página impressa
    # 203" do visualizador = pdf_page_index 202) começa a seção de ÍNDICE
    # TEMÁTICO do livro (não confundir com o número de página impresso do
    # PDF, que pode divergir se o arquivo tiver capa/folha de rosto extra).
    # Confirmado pelo usuário olhando o PDF real: página 202/256 (visualizador)
    # ainda é conteúdo normal (extrato 87); página 203/256 já é o índice.
    # [não verificado por mim de forma independente — baseado só na confirmação
    # do usuário sobre ESTE arquivo específico.]
    #
    # LIMITAÇÃO CONHECIDA: esse corte é por número de página fixo, não por
    # detecção estrutural do cabeçalho "ÍNDICE". Se o PDF for reexportado com
    # uma página a mais ou a menos antes dessa seção, esse número desloca e o
    # corte passa a errar silenciosamente (sem lançar erro nenhum — só volta a
    # indexar lixo, ou começa a cortar conteúdo válido antes da hora). Se isso
    # acontecer, o valor abaixo precisa ser reconferido contra o PDF atual.
    INDEX_SECTION_START_PDF_PAGE_IDX = 202

    def __init__(self, db_conn: DatabaseConnection):
        self.db_conn = db_conn

    def index_document(self, doc_id: int, pdf_path: str) -> bool:
        doc = fitz.open(pdf_path)
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()

            active_entry_id = None
            active_entry_text = []
            active_entry_title = None
            active_entry_location = None
            active_entry_date = None
            printed_label = "1"

            # Alguns livros de citações têm, além do corpo principal (numerado
            # 1..N), seções extras ("Parte A", "Parte B") que REAPROVEITAM os
            # mesmos números de extrato de novo. O livro sinaliza a virada de
            # seção com um marcador de página tipo "7-A"/"1-B" no cabeçalho/
            # rodapé. Rastreamos isso para poder distinguir "extrato 7 da
            # Parte A" de "extrato 7" do corpo principal — sem isso, os dois
            # caem no mesmo número e a busca fica imprecisa.
            current_part = None

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                width, height = page.rect.width, page.rect.height
                page_dict = page.get_text("dict")
                raw_blocks = page_dict.get("blocks", [])

                printed_label = str(page_idx + 1)
                page_conf = 0.90

                # 1. Tenta identificar o rótulo de página impresso no cabeçalho/rodapé
                # (número de página simples, ou marcador de Parte A/B).
                for b in raw_blocks:
                    if b.get("type") == 0:
                        for line in b.get("lines", []):
                            line_text = "".join([s.get("text", "") for s in line.get("spans", [])]).strip()
                            res = PatternDetector.analyze_text_span(line_text, b.get("bbox", [0, 0, 0, 0]), width, height)
                            if res["confidence_page_label"] > page_conf:
                                if res["is_part_label_candidate"]:
                                    printed_label = f"{res['detected_label']}-{res['detected_part']}"
                                    page_conf = res["confidence_page_label"]
                                    # BUG real encontrado com dado do usuario: o marcador
                                    # "1-B" fica no rodape da pagina, entao so seria visto
                                    # pelo SEGUNDO laco (o que processa o corpo, em ordem de
                                    # leitura) DEPOIS de ja ter processado o corpo inteiro
                                    # dessa mesma pagina (rodape sempre vem por ultimo na
                                    # ordem de leitura). Isso fazia a pagina inteira do
                                    # marcador (ex.: extratos 1-11 da pagina "1-B") ser
                                    # indexada ainda com o current_part da secao anterior.
                                    # Atualizando aqui, neste primeiro laco que varre a
                                    # pagina INTEIRA antes de processar o corpo, o
                                    # current_part ja fica correto pra pagina inteira.
                                    current_part = res["detected_part"]
                                elif res["is_page_number_candidate"]:
                                    printed_label = res["detected_label"]
                                    page_conf = res["confidence_page_label"]

                cursor.execute(
                    "INSERT INTO pages (document_id, pdf_page_index, printed_page_label, confidence) VALUES (?, ?, ?, ?)",
                    (doc_id, page_idx, printed_label, page_conf)
                )
                page_db_id = cursor.lastrowid

                # A partir da seção de ÍNDICE TEMÁTICO, os números baixos
                # (1, 2, 3...) voltam a aparecer, agora como identificadores de
                # tópico, não de extrato — sem esse corte, cada linha numerada
                # do índice vira um "extrato fantasma" novo. Página inteira é
                # pulada (não vira entry_chunks nem abre/fecha extrato), mas o
                # registro em `pages` acima já foi feito, pra manter a
                # numeração de página consistente pro resto do app.
                if page_idx >= self.INDEX_SECTION_START_PDF_PAGE_IDX:
                    continue

                # 2. Reordena os blocos em ordem de leitura real (coluna esquerda
                # inteira, depois coluna direita inteira) — é isso que evita cortar
                # um extrato que começa na coluna esquerda e continua na direita.
                blocks = order_blocks_reading_order(raw_blocks, width, height)

                # IMPORTANTE: o teste de "isso começa um novo extrato numerado?"
                # precisa ser feito LINHA por LINHA, não por bloco inteiro. O
                # PyMuPDF às vezes agrupa, no mesmo bloco, a linha de atribuição
                # do extrato anterior ("Mire hacia Jesús, Pág. X...") seguida,
                # na linha de baixo, já pelo início do próximo extrato ("1058 -
                # ..."). Testar o bloco inteiro concatenado faz o "1058" cair no
                # meio da string e nunca bater no padrão (que é ancorado no
                # início), fundindo os dois extratos em um só.
                for b in blocks:
                    bbox = b.get("bbox")
                    for line in b.get("lines", []):
                        line_text = "".join([s.get("text", "") for s in line.get("spans", [])]).strip()
                        if not line_text:
                            continue

                        res = PatternDetector.analyze_text_span(line_text, bbox, width, height)

                        # Marcador "Parte A"/"Parte B" (ex.: "7-A" sozinho no
                        # cabeçalho/rodapé): só atualiza em qual seção estamos
                        # agora — não é conteúdo de citação nenhuma, não abre
                        # nem fecha extrato, não vira chunk.
                        if res["is_part_label_candidate"]:
                            current_part = res["detected_part"]
                            continue

                        # Número de página solto no cabeçalho/rodapé (ex.: só
                        # "100"): idem, é só paginação, não é conteúdo.
                        if res["is_page_number_candidate"]:
                            continue

                        # Ainda não há entrada ativa: abre uma entrada de introdução/capa
                        if active_entry_id is None:
                            active_entry_id = self._start_entry(cursor, doc_id, "Intro/Capa")
                            active_entry_text = []
                            active_entry_title = None
                            active_entry_location = None
                            active_entry_date = None

                        # Linha inicia uma nova entrada numerada -> fecha a anterior e abre esta
                        if res["is_paragraph_candidate"]:
                            self._close_entry(
                                cursor, active_entry_id, doc_id, printed_label,
                                active_entry_text, active_entry_title, active_entry_location, active_entry_date
                            )
                            entry_num = res["detected_paragraph_num"]
                            if current_part:
                                # Mesmo número reaproveitado na Parte A/B do livro
                                # (ex.: extrato "7" do corpo principal vs. "7-A" da
                                # Parte A) — sem isso os dois colidem na busca.
                                entry_num = f"{entry_num}-{current_part}"
                            active_entry_id = self._start_entry(cursor, doc_id, entry_num)
                            active_entry_text = [line_text]
                            active_entry_title = None
                            active_entry_location = None
                            active_entry_date = None

                        # Linha "Cidade, Estado., DD-MM-AA" -> fecha a citação/atribuição
                        # do extrato atual. A linha anterior (já no corpo do texto) é o
                        # título em negrito da referência ("Mire hacia Jesús, Pág. X...");
                        # as duas saem do corpo e viram source_title/location/date_str.
                        elif res["is_location_date_candidate"] and active_entry_text:
                            active_entry_title = active_entry_text.pop()
                            active_entry_location = res["detected_location"]
                            active_entry_date = res["detected_date"]

                        # Cabeçalho/rodapé repetido do livro (ex.: o título "CITAS
                        # DEL MENSAJE DEL PROFETA" que aparece em toda página) não
                        # é conteúdo de citação — não acumula no corpo do extrato.
                        #
                        # BUG real encontrado com dado do usuario: esse "pass" nao
                        # impedia o INSERT INTO entry_chunks logo abaixo (ele ficava
                        # FORA do if/elif, rodando sempre). Isso gravava a linha de
                        # cabecalho como se fosse um chunk do extrato ainda ATIVO
                        # (ex.: "CITAS DEL MENSAJE DEL PROFETA" ficava associado ao
                        # extrato 1539, na pagina "1-A", so porque era a pagina onde
                        # o cabecalho apareceu) -- isso fazia esse extrato aparecer
                        # errado em buscas por pagina ("1-A"), mesmo o texto dele
                        # sendo, de verdade, da pagina 171. Corrigido com "continue",
                        # igual ja acontece com marcador de pagina/Parte-A-B logo
                        # acima -- cabecalho/rodape nao deve virar chunk nenhum.
                        elif res["is_header_or_footer"]:
                            continue

                        else:
                            active_entry_text.append(line_text)

                        cursor.execute(
                            "INSERT INTO entry_chunks (entry_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
                            (active_entry_id, page_db_id, line_text, json.dumps(bbox))
                        )

            # Fecha a última entrada pendente ao final do documento
            if active_entry_id is not None:
                self._close_entry(
                    cursor, active_entry_id, doc_id, printed_label,
                    active_entry_text, active_entry_title, active_entry_location, active_entry_date
                )

            conn.commit()
        return True

    def _start_entry(self, cursor, doc_id: int, entry_number: str) -> int:
        """Cria a linha em text_entries e retorna o id (o texto é preenchido depois, em _close_entry)."""
        cursor.execute(
            "INSERT INTO text_entries (document_id, entry_number, full_text, normalized_text) VALUES (?, ?, ?, ?)",
            (doc_id, entry_number, "", "")
        )
        return cursor.lastrowid

    def _close_entry(
        self, cursor, entry_id: int, doc_id: int, printed_label: str, text_parts,
        source_title=None, location=None, date_str=None
    ) -> None:
        """Consolida o texto acumulado da entrada (todos os blocos/chunks) e grava em
        text_entries + fts_entries. full_text/normalized_text contêm só o corpo da
        citação (sem a linha de atribuição) — título/local/data ficam em colunas
        separadas, para a UI poder mostrar formatado como no livro."""
        full_text = " ".join(text_parts).strip()
        norm_text = self.normalize_text(full_text)

        cursor.execute("SELECT entry_number FROM text_entries WHERE id = ?", (entry_id,))
        entry_number = cursor.fetchone()[0]

        # "Extrato fantasma": a única linha que abriu essa entrada era só o
        # próprio número (ex.: "1057", ou "1057 -"), sem nenhum texto de
        # citação depois. Isso acontece tipicamente em páginas de índice/
        # sumário do livro, onde o número aparece sozinho como referência
        # cruzada — não é uma citação de verdade. Só filtra o caso 100% vazio
        # (zero risco de esconder uma citação real que só coincide em ser
        # curta); entradas com QUALQUER texto além do número continuam
        # indexadas normalmente, mesmo que pareçam curtas.
        body_after_number = PatternDetector.PARAGRAPH_PATTERN.sub("", full_text, count=1).strip()
        is_empty_shell = (body_after_number == "")

        cursor.execute(
            "UPDATE text_entries SET full_text = ?, normalized_text = ?, "
            "source_title = ?, location = ?, date_str = ?, needs_review = ? WHERE id = ?",
            (full_text, norm_text, source_title, location, date_str, 1 if is_empty_shell else 0, entry_id)
        )

        if is_empty_shell:
            # Mantém a linha em text_entries (dado bruto, útil pra depurar),
            # mas não entra no índice de busca — não deve aparecer como
            # resultado de pesquisa.
            return

        cursor.execute(
            "INSERT INTO fts_entries (entry_id, document_id, printed_page_label, entry_number, content, source_title, location) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry_id, doc_id, printed_label, entry_number, norm_text, source_title, location)
        )
