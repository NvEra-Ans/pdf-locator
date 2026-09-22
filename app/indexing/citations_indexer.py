import fitz
import json
from app.indexing.base import BaseIndexer
from app.database.connection import DatabaseConnection
from analyzer.pattern_detector import PatternDetector
from analyzer.layout import order_blocks_reading_order

class CitationsIndexer(BaseIndexer):
    """Indexador específico para livros de citações/extratos numerados (Perfil Tipo B)."""

    def __init__(self, db_conn: DatabaseConnection):
        self.db_conn = db_conn

    def index_document(self, doc_id: int, pdf_path: str) -> bool:
        doc = fitz.open(pdf_path)
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()

            active_entry_id = None
            active_entry_text = []
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
                # inteira, depois coluna direita inteira) — é isso que evita cortar
                # um extrato que começa na coluna esquerda e continua na direita.
                blocks = order_blocks_reading_order(raw_blocks, width, height)

                for b in blocks:
                    block_text = ""
                    for line in b.get("lines", []):
                        block_text += "".join([s.get("text", "") for s in line.get("spans", [])]) + " "
                    block_text = block_text.strip()
                    if not block_text:
                        continue

                    res = PatternDetector.analyze_text_span(block_text, b.get("bbox"), width, height)

                    # Ainda não há entrada ativa: abre uma entrada de introdução/capa
                    if active_entry_id is None:
                        active_entry_id = self._start_entry(cursor, doc_id, "Intro/Capa")
                        active_entry_text = []

                    # Bloco inicia uma nova entrada numerada -> fecha a anterior e abre esta
                    if res["is_paragraph_candidate"]:
                        self._close_entry(cursor, active_entry_id, doc_id, printed_label, active_entry_text)
                        active_entry_id = self._start_entry(cursor, doc_id, res["detected_paragraph_num"])
                        active_entry_text = []

                    active_entry_text.append(block_text)

                    cursor.execute(
                        "INSERT INTO entry_chunks (entry_id, page_id, chunk_text, bbox) VALUES (?, ?, ?, ?)",
                        (active_entry_id, page_db_id, block_text, json.dumps(b.get("bbox")))
                    )

            # Fecha a última entrada pendente ao final do documento
            if active_entry_id is not None:
                self._close_entry(cursor, active_entry_id, doc_id, printed_label, active_entry_text)

            conn.commit()
        return True

    def _start_entry(self, cursor, doc_id: int, entry_number: str) -> int:
        """Cria a linha em text_entries e retorna o id (o texto é preenchido depois, em _close_entry)."""
        cursor.execute(
            "INSERT INTO text_entries (document_id, entry_number, full_text, normalized_text) VALUES (?, ?, ?, ?)",
            (doc_id, entry_number, "", "")
        )
        return cursor.lastrowid

    def _close_entry(self, cursor, entry_id: int, doc_id: int, printed_label: str, text_parts) -> None:
        """Consolida o texto acumulado da entrada (todos os blocos/chunks) e grava em text_entries + fts_entries."""
        full_text = " ".join(text_parts).strip()
        norm_text = self.normalize_text(full_text)

        cursor.execute(
            "UPDATE text_entries SET full_text = ?, normalized_text = ? WHERE id = ?",
            (full_text, norm_text, entry_id)
        )

        cursor.execute("SELECT entry_number FROM text_entries WHERE id = ?", (entry_id,))
        entry_number = cursor.fetchone()[0]

        cursor.execute(
            "INSERT INTO fts_entries (entry_id, document_id, printed_page_label, entry_number, content, source_title, location) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry_id, doc_id, printed_label, entry_number, norm_text, None, None)
        )
