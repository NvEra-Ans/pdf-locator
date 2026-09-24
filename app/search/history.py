"""Histórico de pesquisas -- pedido real do usuário: um registro
cronológico do que foi buscado (e encontrado) no app, pra poder consultar
ou exportar depois -- por exemplo, quais páginas/parágrafos/extratos
foram usados durante a tradução simultânea de um culto.

Decisões confirmadas com o usuário:
  - Cada linha registra a busca E a referência encontrada (não só os
    termos digitados) -- serve como registro de citações usadas.
  - Só buscas com pelo menos 1 resultado entram no histórico (buscas sem
    resultado, tipicamente erro de digitação, não são registradas).
  - Histórico único, geral, com todos os documentos juntos, na ordem
    cronológica real de uso.
  - Existe um jeito de limpar o histórico inteiro dentro do app.
"""
from datetime import datetime
from typing import List, Optional

from app.database.connection import DatabaseConnection


class SearchHistoryEntry:
    def __init__(self, id: int, searched_at: str, document_title: str,
                 query_summary: str, result_summary: str):
        self.id = id
        self.searched_at = searched_at
        self.document_title = document_title
        self.query_summary = query_summary
        self.result_summary = result_summary


class SearchHistoryManager:
    """Grava, lista, exporta e limpa o histórico de pesquisas."""

    def __init__(self, db_conn: DatabaseConnection):
        self.db_conn = db_conn

    @staticmethod
    def build_query_summary(page_label=None, paragraph_num=None, entry_num=None,
                             text_query=None, use_fuzzy=False) -> str:
        """Monta uma descrição legível do que foi digitado nos campos de
        busca (só os campos preenchidos), na mesma ordem em que aparecem
        na tela."""
        parts = []
        if page_label:
            parts.append(f"Página: {page_label}")
        if paragraph_num:
            parts.append(f"Parágrafo: {paragraph_num}")
        if entry_num:
            parts.append(f"Extrato: {entry_num}")
        if text_query:
            parts.append(f'Texto: "{text_query}"')
        if use_fuzzy:
            parts.append("Busca Aproximada")
        return " · ".join(parts) if parts else "(sem filtros)"

    @staticmethod
    def build_result_summary(results, max_refs: int = 5) -> str:
        """Monta uma descrição compacta do que foi encontrado -- até
        `max_refs` referências (Página/Parágrafo ou Página/Extrato),
        com "e mais N" quando a busca trouxe mais resultados do que isso
        (ex.: busca por texto que aparece em vários lugares)."""
        refs = []
        for r in results:
            ref = f"Página {r.printed_page_label}"
            if r.paragraph_number:
                ref += f", Parágrafo {r.paragraph_number}"
            elif r.entry_number:
                ref += f", Extrato {r.entry_number}"
            refs.append(ref)

        shown = refs[:max_refs]
        text = "; ".join(shown)
        remaining = len(refs) - len(shown)
        if remaining > 0:
            text += f" (e mais {remaining})"
        return text

    def log_search(self, document_title: str, query_summary: str, result_summary: str) -> None:
        with self.db_conn.get_connection() as conn:
            conn.execute(
                "INSERT INTO search_history (searched_at, document_title, query_summary, result_summary) "
                "VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), document_title, query_summary, result_summary)
            )
            conn.commit()

    def list_history(self) -> List[SearchHistoryEntry]:
        """Devolve todo o histórico, cronológico a partir da PRIMEIRA
        pesquisa (mais antiga primeiro)."""
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, searched_at, document_title, query_summary, result_summary "
                "FROM search_history ORDER BY id ASC"
            )
            rows = cursor.fetchall()
        return [SearchHistoryEntry(**dict(row)) for row in rows]

    def clear_history(self) -> None:
        with self.db_conn.get_connection() as conn:
            conn.execute("DELETE FROM search_history")
            conn.commit()

    @staticmethod
    def format_timestamp(iso_str: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            return iso_str

    def export_to_txt(self, file_path: str) -> int:
        """Exporta o histórico inteiro para um arquivo .txt (formato
        simples, legível em qualquer editor -- Bloco de Notas incluso),
        organizado cronologicamente a partir da primeira pesquisa.
        Devolve a quantidade de linhas exportadas."""
        entries = self.list_history()

        lines = [
            "Histórico de Pesquisas - Localizador de Citações",
            f"Exportado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"Total de pesquisas: {len(entries)}",
            "=" * 60,
            "",
        ]
        for entry in entries:
            lines.append(f"[{self.format_timestamp(entry.searched_at)}] {entry.document_title}")
            lines.append(f"  Busca: {entry.query_summary}")
            lines.append(f"  Encontrado: {entry.result_summary}")
            lines.append("")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return len(entries)
