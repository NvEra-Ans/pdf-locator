from typing import List, Optional
from rapidfuzz import fuzz
from app.database.connection import DatabaseConnection
from app.models.document import SearchResult, DocumentIndexProfile, ProfileType
from app.indexing.base import BaseIndexer

class SearchEngine:
    """Motor de Busca Inteligente com suporte a FTS5, Busca por Página, Parágrafo, Extrato e Fuzzy Search."""

    def __init__(self, db_conn: DatabaseConnection):
        self.db_conn = db_conn

    def get_next_page_with_content(self, document_id: int, current_page_label: str) -> Optional[str]:
        """Acha o próximo número de página (maior que o atual) que tem
        conteúdo indexado de verdade, pulando páginas "buraco" sem texto
        (ex.: números que não existem porque a página é abertura de
        capítulo/Notas sem conteúdo próprio -- ver paragraph_indexer.py).

        PEDIDO REAL do usuário: botão de "Próxima Página" pra continuar a
        leitura sem precisar digitar o número manualmente. Decisão
        confirmada com o usuário: pular buracos sem conteúdo, não parar
        neles -- leitura contínua é a prioridade.

        Só funciona quando o rótulo de página atual é puramente numérico
        (ex.: "53"). Rótulos alfanuméricos (ex.: "14A", usados no livro de
        citações) não têm uma noção clara de "próximo" e retornam None --
        o chamador deve desabilitar o botão nesse caso.
        """
        return self._get_adjacent_page_with_content(document_id, current_page_label, direction="next")

    def get_previous_page_with_content(self, document_id: int, current_page_label: str) -> Optional[str]:
        """Espelho de get_next_page_with_content, pra trás -- mesmo pedido
        real do usuário ("completar a ideia" do botão de página com um
        botão de voltar também). Mesma regra: pula buracos sem conteúdo
        (indo pra página anterior com texto de verdade), e só funciona com
        rótulo de página puramente numérico."""
        return self._get_adjacent_page_with_content(document_id, current_page_label, direction="previous")

    def _get_adjacent_page_with_content(
        self, document_id: int, current_page_label: str, direction: str
    ) -> Optional[str]:
        if not current_page_label or not current_page_label.isdigit():
            return None
        current_num = int(current_page_label)

        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT profile_type FROM documents WHERE id = ?", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                return None
            profile = DocumentIndexProfile.get_profile(ProfileType(doc_row["profile_type"]))

            if profile.profile_type == ProfileType.PARAGRAPH_BOOK:
                chunk_table = "paragraph_chunks"
            else:
                chunk_table = "entry_chunks"

            comparator = ">" if direction == "next" else "<"
            order = "ASC" if direction == "next" else "DESC"

            # GLOB '[0-9]*' + NOT GLOB '*[^0-9]*' = string inteira só com
            # dígitos (equivalente a um .isdigit() em SQL puro), pra não
            # quebrar o CAST em páginas com rótulo alfanumérico.
            cursor.execute(
                f"""
                SELECT pg.printed_page_label
                FROM pages pg
                WHERE pg.document_id = ?
                  AND pg.printed_page_label GLOB '[0-9]*'
                  AND pg.printed_page_label NOT GLOB '*[^0-9]*'
                  AND CAST(pg.printed_page_label AS INTEGER) {comparator} ?
                  AND EXISTS (SELECT 1 FROM {chunk_table} c WHERE c.page_id = pg.id)
                ORDER BY CAST(pg.printed_page_label AS INTEGER) {order}
                LIMIT 1
                """,
                (document_id, current_num)
            )
            row = cursor.fetchone()
            return row["printed_page_label"] if row else None

    def search(
        self,
        document_id: int,
        page_label: Optional[str] = None,
        paragraph_num: Optional[str] = None,
        entry_num: Optional[str] = None,
        text_query: Optional[str] = None,
        use_fuzzy: bool = False,
        fuzzy_threshold: float = 75.0
    ) -> List[SearchResult]:

        results: List[SearchResult] = []
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()

            # Obtém metadados do documento
            cursor.execute("SELECT title, profile_type FROM documents WHERE id = ?", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                return results

            doc_title, prof_type_str = doc_row["title"], doc_row["profile_type"]
            profile = DocumentIndexProfile.get_profile(ProfileType(prof_type_str))

            norm_text = BaseIndexer.normalize_text(text_query) if text_query else None

            # 1. Pesquisa no Perfil PARAGRAPH_BOOK (Tipo A)
            if profile.profile_type == ProfileType.PARAGRAPH_BOOK:
                # PEDIDO REAL do usuario: nesse perfil (livro tipo "Los Siete
                # Sellos", sermao dividido em paragrafos numerados dentro da
                # pagina) a consulta normal e por PAGINA, nao por paragrafo
                # isolado -- diferente do livro de citacoes, onde cada
                # extrato e uma unidade fechada por si so. Buscar so pela
                # pagina devolvia um resultado SEPARADO por paragrafo (ex.:
                # pagina 10 com paragrafos 32 e 33 apareciam como 2 linhas),
                # obrigando a pessoa a clicar em cada um pra reconstruir o
                # texto da pagina inteira -- o que o livro real (uma pagina
                # continua, com varios paragrafos numerados em sequencia)
                # nao pede.
                #
                # Corrigido: quando a pesquisa informa uma PAGINA, o
                # resultado passa a ser UM registro por pagina, com o texto
                # de TODOS os paragrafos daquela pagina concatenados na
                # ordem em que aparecem (mesma ordem de insercao/leitura),
                # igual a pagina fisica do livro. Buscar so por parágrafo
                # (sem pagina) continua devolvendo um resultado por
                # parágrafo, ja que nesse caso o objetivo e achar aquele
                # número específico em qualquer capítulo do livro (a
                # numeração reinicia por capítulo, ver PatternDetector).
                if page_label:
                    # Reconstroi o texto a partir de paragraph_chunks (nao
                    # de paragraphs.text) -- e o unico jeito de recuperar
                    # corretamente o pedaco de um paragrafo que COMECOU na
                    # pagina anterior e so termina nesta (ex.: pagina 10
                    # comecando com o final do paragrafo 31, antes do "32."
                    # aparecer). paragraphs.text tem o texto INTEIRO do
                    # paragrafo (util pra busca por numero de paragrafo
                    # isolado, no bloco `else` abaixo), mas nao diz o que
                    # ficou fisicamente em CADA pagina quando ele atravessa
                    # mais de uma.
                    query = """
                    SELECT d.id as doc_id, d.title, pg.id as page_db_id,
                           pg.pdf_page_index, pg.printed_page_label
                    FROM pages pg
                    JOIN documents d ON pg.document_id = d.id
                    WHERE d.id = ? AND pg.printed_page_label = ?
                      AND EXISTS (SELECT 1 FROM paragraph_chunks pc WHERE pc.page_id = pg.id)
                    """
                    params = [document_id, page_label]
                    if paragraph_num and profile.supports_paragraph_search:
                        query += """ AND EXISTS (
                            SELECT 1 FROM paragraph_chunks pc2
                            JOIN paragraphs p2 ON pc2.paragraph_id = p2.id
                            WHERE pc2.page_id = pg.id AND p2.paragraph_number = ?
                        )"""
                        params.append(paragraph_num)

                    cursor.execute(query, params)
                    page_rows = cursor.fetchall()

                    for pr in page_rows:
                        cursor.execute(
                            "SELECT pc.paragraph_id, pc.chunk_text, p.paragraph_number FROM paragraph_chunks pc "
                            "JOIN paragraphs p ON pc.paragraph_id = p.id "
                            "WHERE pc.page_id = ? ORDER BY pc.id",
                            (pr["page_db_id"],)
                        )
                        chunk_rows = cursor.fetchall()
                        if not chunk_rows:
                            continue

                        # Agrupa os chunks (linhas) por parágrafo consecutivo,
                        # juntando as linhas de um mesmo parágrafo com espaço
                        # (reconstrói a frase) e separando parágrafos
                        # diferentes com quebra dupla (parágrafo novo).
                        para_groups = []
                        for c in chunk_rows:
                            if para_groups and para_groups[-1]["paragraph_id"] == c["paragraph_id"]:
                                para_groups[-1]["lines"].append(c["chunk_text"])
                            else:
                                para_groups.append({
                                    "paragraph_id": c["paragraph_id"],
                                    "paragraph_number": c["paragraph_number"],
                                    "lines": [c["chunk_text"]],
                                })

                        # BUG real reportado pelo usuário (print de tela): esta
                        # reconstrução por página tinha seu PRÓPRIO join ingênuo
                        # (" ".join), separado do usado em paragraph_indexer.py
                        # -- então mesmo depois de corrigir a hifenização de
                        # quebra de linha na indexação, a busca por PÁGINA
                        # continuava mostrando "es- trechó" em vez de
                        # "estrechó", porque reconstrói o texto direto dos
                        # chunks salvos por linha. Precisa do mesmo tratamento.
                        content = "\n\n".join(BaseIndexer.join_text_parts(g["lines"]) for g in para_groups)
                        content_norm = BaseIndexer.normalize_text(content)
                        score = 100.0

                        if norm_text:
                            if use_fuzzy:
                                score = fuzz.partial_ratio(norm_text, content_norm)
                                if score < fuzzy_threshold:
                                    continue
                            else:
                                if norm_text not in content_norm:
                                    continue

                        first_num = para_groups[0]["paragraph_number"]
                        last_num = para_groups[-1]["paragraph_number"]
                        range_label = first_num if first_num == last_num else f"{first_num}-{last_num}"

                        results.append(SearchResult(
                            document_id=pr["doc_id"],
                            document_title=pr["title"],
                            pdf_page_index=pr["pdf_page_index"],
                            printed_page_label=pr["printed_page_label"],
                            paragraph_number=range_label,
                            text_snippet=content[:150] + "...",
                            full_text=content,
                            match_score=score
                        ))

                else:
                    # Sem pagina informada: busca por paragrafo (ou texto)
                    # em qualquer lugar do documento -- mantem 1 resultado
                    # por paragrafo, como antes.
                    query = """
                    SELECT d.id as doc_id, d.title, pg.pdf_page_index, pg.printed_page_label,
                           p.paragraph_number, p.text, p.normalized_text
                    FROM paragraphs p
                    JOIN pages pg ON p.page_id = pg.id
                    JOIN documents d ON pg.document_id = d.id
                    WHERE d.id = ?
                    """
                    params = [document_id]

                    if paragraph_num and profile.supports_paragraph_search:
                        query += " AND p.paragraph_number = ?"
                        params.append(paragraph_num)

                    cursor.execute(query, params)
                    rows = cursor.fetchall()

                    for r in rows:
                        content = r["text"]
                        content_norm = r["normalized_text"]
                        score = 100.0

                        if norm_text:
                            if use_fuzzy:
                                score = fuzz.partial_ratio(norm_text, content_norm)
                                if score < fuzzy_threshold:
                                    continue
                            else:
                                if norm_text not in content_norm:
                                    continue

                        results.append(SearchResult(
                            document_id=r["doc_id"],
                            document_title=r["title"],
                            pdf_page_index=r["pdf_page_index"],
                            printed_page_label=r["printed_page_label"],
                            paragraph_number=r["paragraph_number"],
                            text_snippet=content[:150] + "...",
                            full_text=content,
                            match_score=score
                        ))

            # 2. Pesquisa no Perfil CITATIONS_BOOK (Tipo B)
            elif profile.profile_type == ProfileType.CITATIONS_BOOK:
                # Observação: usar LEFT JOIN direto com entry_chunks/pages multiplica as
                # linhas (uma por chunk) quando uma entrada tem mais de um chunk associado.
                # Por isso a página é obtida via subquery (primeiro chunk da entrada), e o
                # filtro por page_label usa EXISTS, mantendo uma linha por entrada.
                query = """
                SELECT d.id as doc_id, d.title,
                       (SELECT pg2.pdf_page_index
                          FROM entry_chunks ec2 JOIN pages pg2 ON ec2.page_id = pg2.id
                         WHERE ec2.entry_id = e.id ORDER BY ec2.id LIMIT 1) as pdf_page_index,
                       (SELECT pg2.printed_page_label
                          FROM entry_chunks ec2 JOIN pages pg2 ON ec2.page_id = pg2.id
                         WHERE ec2.entry_id = e.id ORDER BY ec2.id LIMIT 1) as printed_page_label,
                       e.entry_number, e.full_text, e.normalized_text, e.source_title, e.location, e.date_str
                FROM text_entries e
                JOIN documents d ON e.document_id = d.id
                WHERE d.id = ? AND e.needs_review = 0
                """
                params = [document_id]

                if page_label:
                    query += """ AND EXISTS (
                        SELECT 1 FROM entry_chunks ec JOIN pages pg ON ec.page_id = pg.id
                        WHERE ec.entry_id = e.id AND pg.printed_page_label = ?
                    )"""
                    params.append(page_label)
                if entry_num and profile.supports_entry_search:
                    # A busca por extrato precisa achar o numero "puro" (ex.:
                    # "7") E as variantes de Parte A/B (ex.: "7-A", "7-B") --
                    # o indexador grava entry_number com o sufixo "-A"/"-B"
                    # quando o extrato pertence a uma dessas secoes (ver
                    # citations_indexer.py). Antes da correcao do bug de
                    # rastreamento de Parte A/B, esses extratos as vezes
                    # ficavam gravados sem sufixo por engano, e por isso a
                    # busca "= entry_num" parecia funcionar (coincidencia).
                    # Com o rastreamento corrigido, o sufixo passou a ser
                    # aplicado corretamente, e a busca por igualdade exata
                    # parou de encontrar "7-A"/"7-B" ao buscar "7" -- por
                    # pedido explicito do usuario, resultados do mesmo numero
                    # de extrato em secoes diferentes devem aparecer juntos,
                    # distinguidos pela coluna Pagina. LIKE 'entry_num-%'
                    # cobre exatamente os sufixos "-A"/"-B" sem casar outros
                    # numeros que só começam com os mesmos dígitos (ex.:
                    # buscar "7" não deve casar "70-A", porque "70-A" não
                    # começa com "7-").
                    query += " AND (e.entry_number = ? OR e.entry_number LIKE ? ESCAPE '\\')"
                    escaped_entry_num = entry_num.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                    params.append(entry_num)
                    params.append(f"{escaped_entry_num}-%")

                cursor.execute(query, params)
                rows = cursor.fetchall()

                for r in rows:
                    content = r["full_text"]
                    content_norm = r["normalized_text"]
                    score = 100.0

                    if norm_text:
                        if use_fuzzy:
                            score = fuzz.partial_ratio(norm_text, content_norm)
                            if score < fuzzy_threshold:
                                continue
                        else:
                            if norm_text not in content_norm:
                                continue

                    results.append(SearchResult(
                        document_id=r["doc_id"],
                        document_title=r["title"],
                        pdf_page_index=r["pdf_page_index"] if r["pdf_page_index"] is not None else 0,
                        printed_page_label=r["printed_page_label"] if r["printed_page_label"] else "N/A",
                        entry_number=r["entry_number"],
                        text_snippet=content[:150] + "...",
                        full_text=content,
                        match_score=score,
                        source_title=r["source_title"],
                        location=r["location"],
                        date_str=r["date_str"]
                    ))

        return results