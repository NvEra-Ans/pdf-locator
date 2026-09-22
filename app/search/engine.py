from typing import List, Optional
from rapidfuzz import fuzz
from app.database.connection import DatabaseConnection
from app.models.document import SearchResult, DocumentIndexProfile, ProfileType
from app.indexing.base import BaseIndexer

class SearchEngine:
    """Motor de Busca Inteligente com suporte a FTS5, Busca por Página, Parágrafo, Extrato e Fuzzy Search."""

    def __init__(self, db_conn: DatabaseConnection):
        self.db_conn = db_conn

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
                query = """
                SELECT d.id as doc_id, d.title, pg.pdf_page_index, pg.printed_page_label,
                       p.paragraph_number, p.text, p.normalized_text
                FROM paragraphs p
                JOIN pages pg ON p.page_id = pg.id
                JOIN documents d ON pg.document_id = d.id
                WHERE d.id = ?
                """
                params = [document_id]

                if page_label:
                    query += " AND pg.printed_page_label = ?"
                    params.append(page_label)
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
                WHERE d.id = ?
                """
                params = [document_id]

                if page_label:
                    query += """ AND EXISTS (
                        SELECT 1 FROM entry_chunks ec JOIN pages pg ON ec.page_id = pg.id
                        WHERE ec.entry_id = e.id AND pg.printed_page_label = ?
                    )"""
                    params.append(page_label)
                if entry_num and profile.supports_entry_search:
                    query += " AND e.entry_number = ?"
                    params.append(entry_num)

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