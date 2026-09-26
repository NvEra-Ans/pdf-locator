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

    @staticmethod
    def _line_font_size(line: dict) -> float:
        """Tamanho de fonte "representativo" de uma linha -- média ponderada
        por quantidade de caracteres de cada span, não o tamanho MÁXIMO.

        BUG real encontrado com PDF de amostra do usuario (livro "Las
        Edades"): esses sermões usam negrito num trecho CURTO da linha pra
        marcar ênfase vocal/gagueira (ex.: "un—un Dodge", onde só o "-un "
        vem maior, ~12.7pt, dentro de uma linha cujo resto é corpo normal,
        ~10.3-10.9pt). Usando o tamanho MÁXIMO da linha pra decidir se ela é
        um bloco decorativo (título/autor/data), essa única palavra em
        negrito fazia a LINHA INTEIRA ser tratada como decorativa e
        descartada -- sumindo com uma frase real de conteúdo. A média
        ponderada por caracteres não se deixa dominar por um trecho curto
        em destaque, só por uma linha que é REALMENTE toda maior (caso
        real de título/autor/data, ou letra capitular sozinha)."""
        total_chars = 0
        weighted_sum = 0.0
        for span in line.get("spans", []):
            text = span.get("text", "")
            size = span.get("size", 0) or 0
            if not text or not size:
                continue
            total_chars += len(text)
            weighted_sum += size * len(text)
        return weighted_sum / total_chars if total_chars else 0.0

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

            # Letra capitular decorativa pendente (ver mais abaixo) -- fica
            # em espera aqui até a próxima linha real de texto, pra ser
            # colada SEM espaço nela (ex.: "M" + "uy asombrado" -> "Muy
            # asombrado", não "M uy asombrado").
            pending_dropcap_prefix = ""

            final_labels, final_confs, raw_blocks_cache, body_font_size = self._resolve_page_labels(doc)

            for page_idx in range(len(doc)):
                raw_blocks, width, height = raw_blocks_cache[page_idx]
                printed_label = final_labels[page_idx]
                page_conf = final_confs[page_idx]

                # Marca se esta página NÃO tinha número impresso detectável --
                # só páginas assim (divisórias de capítulo, capa) têm o risco
                # do vazamento de texto decorativo tratado no passo 2 abaixo.
                # Uma página de conteúdo normal (número real detectado) nunca
                # tem esse bloco decorativo, então não precisa dessa checagem.
                page_number_was_inferred = not (page_conf > 0.90)

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
                # BUG real encontrado com dado do usuario: pagina de abertura
                # de capitulo (ex.: "LA BRECHA...") traz, entre o titulo (todo
                # maiusculo, ja filtrado acima) e o primeiro paragrafo "1.",
                # um bloco decorativo -- data, local, epigrafe/hino -- que NAO
                # e todo maiusculo, entao escapava do filtro de cabecalho e
                # era colado no final do ULTIMO paragrafo do capitulo
                # ANTERIOR (que ainda estava "aberto", esperando mais texto).
                # Esse bloco e sempre CENTRALIZADO e mais ESTREITO que o
                # corpo do texto (que ocupa quase a largura toda da pagina) --
                # diferente de uma citacao biblica centralizada DENTRO de um
                # paragrafo (ex.: "Marcos 11:23-24"), que so acontece DEPOIS
                # que um paragrafo numerado ja comecou naquela pagina. Por
                # isso so filtramos bloco centralizado/estreito quando: (a) a
                # pagina nao tinha numero impresso (unico caso onde esse bloco
                # decorativo aparece) E (b) ainda nao vimos nenhum "N." comecar
                # nesta pagina.
                seen_paragraph_start_this_page = False

                # BUG real encontrado com PDF de amostra do usuario: quando
                # o capitulo novo começa com texto de introdução SEM numero
                # nenhum (nao com "1." de cara -- ex.: "Buenos días, amigos.
                # Es un privilegio..." antes do primeiro "2."), o paragrafo
                # do capitulo ANTERIOR nunca fechava (só fecha quando um
                # "N." novo aparece) -- entao esse texto de abertura ficava
                # colado no final do ULTIMO paragrafo do capitulo anterior,
                # em vez de virar sua própria entrada "Intro/Capa" do
                # capitulo novo. Corrigido: assim que o PRIMEIRO bloco
                # decorativo desta página é filtrado (título/autor/data --
                # sinal confiável de que é uma página de abertura de
                # capítulo), o parágrafo que estava aberto é fechado ali
                # mesmo, pra próxima linha de conteúdo real abrir uma
                # "Intro/Capa" nova, e não continuar o capítulo anterior.
                chapter_boundary_closed_this_page = False

                for b in blocks:
                    bbox = b.get("bbox")
                    for line in b.get("lines", []):
                        line_text = "".join([s.get("text", "") for s in line.get("spans", [])]).strip()
                        if not line_text:
                            continue

                        # BUG real encontrado com PDF de amostra do usuario:
                        # a letra capitular decorativa (inicial grande de um
                        # sermao, ex.: "M" de "Muy asombrado...") vem numa
                        # linha PROPRIA, separada do resto da palavra, e com
                        # fonte bem maior que o corpo (~34pt vs ~12pt aqui).
                        # Ela NAO pode ser tratada como bloco decorativo
                        # descartavel (o filtro logo abaixo faria isso, ja
                        # que tambem e "fonte maior que o corpo") -- ela E
                        # conteudo real, só que quebrada em dois pedacos pelo
                        # PDF. Fica em espera aqui e é colada, sem espaço, no
                        # começo da PRÓXIMA linha de texto real (ver uso de
                        # `pending_dropcap_prefix` abaixo) -- reconstituindo
                        # "M" + "uy asombrado" -> "Muy asombrado".
                        line_size_check = self._line_font_size(line)
                        if (
                            len(line_text) == 1
                            and line_text.isalpha()
                            and body_font_size
                            and line_size_check >= 1.12 * body_font_size
                        ):
                            pending_dropcap_prefix += line_text
                            continue

                        if page_number_was_inferred and not seen_paragraph_start_this_page and bbox:
                            block_width = bbox[2] - bbox[0]
                            block_center = (bbox[0] + bbox[2]) / 2.0
                            page_center = width / 2.0
                            is_narrow_centered = (
                                block_width < 0.55 * width and abs(block_center - page_center) < 0.08 * width
                            )

                            # BUG real encontrado com PDF de amostra do usuario
                            # (livro "La Palabra Hablada"/"Las Edades"): o
                            # bloco decorativo de abertura de capitulo (titulo,
                            # nome do autor, data/local) nem sempre e
                            # estreito+centralizado como no "Los Siete Sellos"
                            # -- nesse livro e um bloco LARGO (varias linhas
                            # ocupando quase a largura toda), entao escapava do
                            # filtro acima e vazava pro final do ultimo
                            # paragrafo ainda aberto (do capitulo ANTERIOR).
                            # Confirmado no PDF real: titulo/autor/data usam
                            # fonte negrito/italico e/ou tamanho MAIOR que o
                            # corpo do texto (ex.: titulo a 18pt vs corpo a
                            # ~10.5pt; autor/data a 14pt vs corpo a 12pt; a
                            # letra capitular decorativa de abertura, ainda
                            # maior, a ~34pt). Detectado comparando o tamanho
                            # da fonte desta linha com o tamanho "tipico" do
                            # corpo do texto (calculado uma vez pro documento
                            # inteiro, ver `_resolve_page_labels`) -- 12% maior
                            # ja e sinal suficiente, sem depender de largura ou
                            # centralizacao nenhuma.
                            line_size = self._line_font_size(line)
                            is_off_size = bool(body_font_size) and line_size >= 1.12 * body_font_size

                            if is_narrow_centered or is_off_size:
                                if not chapter_boundary_closed_this_page and current_para_id is not None:
                                    self._close_paragraph(cursor, current_para_id, doc_id, printed_label, current_para_text)
                                    current_para_id = None
                                    current_para_num = None
                                    current_para_text = []
                                    chapter_boundary_closed_this_page = True
                                continue

                        if pending_dropcap_prefix:
                            line_text = pending_dropcap_prefix + line_text
                            pending_dropcap_prefix = ""

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

                        if res["is_paragraph_candidate"]:
                            seen_paragraph_start_this_page = True

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

    def _resolve_page_labels(self, doc):
        """Primeira passada (só leitura, nenhuma gravação): decide o rótulo de
        página impressa final pra cada página do documento, ANTES de extrair
        parágrafo nenhum.

        BUG real encontrado com PDF de amostra do usuário (livro "La Palabra
        Hablada" -- cada capítulo é um sermão separado, com parágrafos
        renumerados a partir de "1." em cada um, mas a numeração de PÁGINA é
        contínua pelo livro todo): a lógica antiga só conseguia inferir o
        rótulo de uma página sem número impresso comparando com o "último
        número confirmado" (`last_confirmed_page_num`) -- e nas primeiras
        páginas do livro (capa, ficha técnica, página de abertura do 1º
        sermão, ANTES de qualquer número real já ter sido visto), esse valor
        ainda é `None`. Isso fazia essas páginas caírem no fallback bruto
        `page_idx + 1` como se fosse um número confiável (mesma confiança
        0.90 de uma página sem detecção nenhuma) -- ex. real confirmado
        nesta amostra: a 3ª página física do PDF (índice 2, sem número
        impresso) já tem texto de dois parágrafos numerados ("2.", "3.") do
        1º sermão, mas era gravada com o rótulo "3" (índice cru do PDF) em
        vez do número real da página impressa (que só aparece 1 página
        depois, como "56" -- ou seja, essa página 3ª/índice 2 deveria ser
        rotulada "55"). Isso faz esse conteúdo real ficar indexado sob um
        número de página que não existe no livro de verdade -- busca pelo
        número real não encontra nada, e busca pelo número errado (aqui,
        "3") devolve um resultado que não bate com a página física
        correspondente.

        Corrigido com uma segunda passada, que só é possível porque agora o
        documento inteiro é lido ANTES de resolver qualquer rótulo (a versão
        antiga resolvia em streaming, uma página de cada vez, sem enxergar
        adiante): as páginas sem número são resolvidas em blocos, entre duas
        âncoras confirmadas (ou antes da 1ª / depois da última). Quando um
        bloco fica entre duas âncoras e a quantidade de páginas bate
        exatamente com a quantidade de números faltando, a resposta é
        calculada por contagem direta (sem depender de heurística nenhuma).
        Só quando a contagem não bate (ou o bloco está no início/fim do
        documento, sem âncora dos dois lados) entra a heurística antiga
        (página sem parágrafo numerado não consome número / página com
        parágrafo numerado consome 1, com a correção de página de abertura
        cair em ímpar) -- ver `fill_run` abaixo pra detalhes de cada caso.

        [inferência] Essa extrapolação pra trás usa a mesma regra já
        confirmada pro MEIO do livro, mas não foi confirmada contra um
        número de página real impresso ANTES do início desta amostra (o
        arquivo de amostra começa exatamente nessas páginas) -- ou seja, o
        valor calculado pras páginas iniciais do livro é a melhor estimativa
        possível com o padrão já visto, não uma confirmação direta. Vale
        conferir no app, após reimportar, se o número calculado pra essas
        primeiras páginas bate com o livro impresso de verdade.
        """
        num_pages = len(doc)
        raw_blocks_cache = [None] * num_pages
        detected_label = [None] * num_pages
        detected_conf = [0.0] * num_pages
        has_content = [False] * num_pages

        # Tamanho de fonte "tipico" do corpo do texto no documento inteiro --
        # usado (ver corpo do metodo index_document) pra reconhecer bloco
        # decorativo de abertura de capitulo (titulo/autor/data, ou letra
        # capitular) por ter fonte visivelmente MAIOR que o corpo, mesmo
        # quando o bloco nao e estreito/centralizado. Calculado como a
        # mediana ponderada por quantidade de caracteres (nao a media nem a
        # moda simples) pra nao ser distorcida por poucas linhas de titulo em
        # fonte grande nem por pequena variacao de tamanho entre linhas do
        # proprio corpo (comum em texto justificado, ex.: 10.3 vs 10.9) --
        # como o corpo do texto sempre domina a contagem de caracteres do
        # livro, a mediana pondera cai dentro da faixa do corpo mesmo com
        # esse jitter.
        size_weight_pairs = []

        for page_idx in range(num_pages):
            page = doc[page_idx]
            width, height = page.rect.width, page.rect.height
            raw_blocks = page.get_text("dict").get("blocks", [])
            raw_blocks_cache[page_idx] = (raw_blocks, width, height)

            best_label = None
            best_conf = 0.90
            for b in raw_blocks:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    line_text = "".join([s.get("text", "") for s in line.get("spans", [])]).strip()
                    if not line_text:
                        continue
                    res = PatternDetector.analyze_text_span(line_text, b.get("bbox", [0, 0, 0, 0]), width, height)
                    if res["is_page_number_candidate"] and res["confidence_page_label"] > best_conf:
                        best_label = res["detected_label"]
                        best_conf = res["confidence_page_label"]
                    if PatternDetector.PARAGRAPH_PATTERN_TYPE_A.match(line_text):
                        has_content[page_idx] = True
                    line_size = ParagraphIndexer._line_font_size(line)
                    if line_size:
                        size_weight_pairs.append((line_size, len(line_text)))
            if best_label is not None:
                detected_label[page_idx] = best_label
                detected_conf[page_idx] = best_conf

        final_labels = [None] * num_pages
        final_confs = [0.0] * num_pages

        # Índices de TODAS as páginas com número confirmado no documento
        # inteiro -- ter essa lista completa ANTES de resolver qualquer
        # página sem número (só é possível porque agora é uma segunda
        # passada, com o documento inteiro já lido) é o que permite a
        # melhoria abaixo em relação à versão antiga (que só enxergava pra
        # trás, uma página de cada vez, em streaming).
        anchor_indices = [i for i in range(num_pages) if detected_label[i] is not None and detected_label[i].isdigit()]
        for i in anchor_indices:
            final_labels[i] = detected_label[i]
            final_confs[i] = detected_conf[i]

        def fill_forward_heuristic(run, start_num):
            """Avança 1 número por página com parágrafo detectado (com
            correção de abertura de capítulo cair em ímpar), repete o último
            número em página sem conteúdo -- a regra original, confirmada no
            livro "La Revelación de Los Siete Sellos" (páginas "Notas" extras
            desta edição, que não fazem parte da paginação original, não
            consomem número). Usada só quando NÃO dá pra reconciliar a
            contagem exata (ver fill_reconciled abaixo), que é mais confiável
            quando disponível."""
            cur = start_num
            for j in run:
                if has_content[j]:
                    cur += 1
                    if cur % 2 == 0:
                        cur += 1
                final_labels[j] = str(cur)
                final_confs[j] = 0.85

        def fill_backward_heuristic(run, end_num):
            """Espelho de fill_forward_heuristic, de trás pra frente -- único
            recurso possível pra páginas ANTES da 1ª âncora do livro inteiro
            (capa/ficha técnica/abertura do 1º capítulo), onde não existe
            nenhum número confirmado anterior pra reconciliar contagem."""
            cur = end_num
            for j in reversed(run):
                if has_content[j]:
                    cur -= 1
                    if cur % 2 == 0:
                        cur -= 1
                final_labels[j] = str(cur)
                final_confs[j] = 0.85

        def fill_run(run, left_num, right_num):
            if not run:
                return
            if left_num is not None and right_num is not None:
                gap = right_num - left_num - 1
                if gap == len(run):
                    # BUG real encontrado com 2ª amostra do usuário (livro
                    # "Las Edades"/"La Palabra Hablada", capítulos sobre as
                    # igrejas de Éfeso/Esmirna): entre as páginas confirmadas
                    # "109" e "112" havia 2 páginas sem número -- uma em
                    # branco (sem parágrafo nenhum) e uma de abertura de
                    # capítulo (com parágrafo). A regra antiga (só avançar em
                    # página COM conteúdo) fazia a página em branco "repetir"
                    # 109 em vez de virar 110, e a de abertura virar 111 --
                    # sobrando o número 110 sem nenhuma página, silenciosamente.
                    # Quando dá pra CONTAR exatamente quantos números faltam
                    # (112-109-1 = 2) e esse total bate com o número de
                    # páginas sem rótulo nesse intervalo (2), a contagem exata
                    # é usada diretamente -- sem depender de heurística de
                    # conteúdo nenhuma, porque nesse caso a resposta certa é
                    # matematicamente garantida (cada página física recebe,
                    # em ordem, um dos números que faltam).
                    for offset, j in enumerate(run):
                        final_labels[j] = str(left_num + 1 + offset)
                        final_confs[j] = 0.88
                    return
                # Contagem não bate (mais ou menos páginas físicas do que
                # números faltando) -- reconciliação exata não é possível
                # com certeza; cai pra heurística de conteúdo, ancorada pela
                # esquerda (mesmo comportamento de antes).
                fill_forward_heuristic(run, left_num)
                return
            if left_num is not None:
                # Trecho no FINAL do documento, sem nenhuma âncora depois --
                # só dá pra seguir em frente com a heurística de conteúdo.
                fill_forward_heuristic(run, left_num)
                return
            if right_num is not None:
                # Trecho no INÍCIO do documento (antes da 1ª âncora do livro
                # inteiro) -- não há como reconciliar contagem (não sabemos
                # quantas páginas vieram antes desta amostra/deste livro), só
                # dá pra extrapolar pra trás com a heurística de conteúdo.
                # [inferência] ver nota detalhada na docstring do método.
                fill_backward_heuristic(run, right_num)
                return
            # Caso extremo (não esperado num livro real): documento inteiro
            # sem NENHUM número de página confirmado -- usa o índice cru
            # como último recurso, com confiança BAIXA (0.5, abaixo do
            # limiar de 0.90 usado em todo o resto do código) pra não ser
            # confundido com um número real ou inferido de verdade.
            for j in run:
                final_labels[j] = str(j + 1)
                final_confs[j] = 0.5

        # Preenche o trecho ANTES da 1ª âncora, cada trecho ENTRE duas
        # âncoras consecutivas, e o trecho DEPOIS da última âncora.
        cursor_idx = 0
        prev_num = None
        for anchor_idx in anchor_indices:
            run = list(range(cursor_idx, anchor_idx))
            fill_run(run, prev_num, int(detected_label[anchor_idx]))
            prev_num = int(detected_label[anchor_idx])
            cursor_idx = anchor_idx + 1
        if cursor_idx < num_pages:
            fill_run(list(range(cursor_idx, num_pages)), prev_num, None)

        body_font_size = None
        if size_weight_pairs:
            size_weight_pairs.sort(key=lambda pair: pair[0])
            total_weight = sum(weight for _, weight in size_weight_pairs)
            half_weight = total_weight / 2.0
            cumulative = 0
            for size, weight in size_weight_pairs:
                cumulative += weight
                if cumulative >= half_weight:
                    body_font_size = size
                    break

        return final_labels, final_confs, raw_blocks_cache, body_font_size

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
        full_text = self.join_text_parts(text_parts)
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
