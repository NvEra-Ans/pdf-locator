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

                current_para_num = None
                current_para_text = []
                current_bbox = None

                for b in blocks:
                    block_text = ""
                    for line in b.get("lines", []):
                        block_text += "".join([s.get("text", "") for s in line.get("spans", [])]) + " "

                    block_text = block_text.strip()
                    if not block_text:
                        continue

                    res = PatternDetector.analyze_text_span(block_text, b.get("bbox"), width, height)
                    if res["is_paragraph_candidate"]:
                        # Salva parágrafo anterior
                        if current_para_num and current_para_text:
                            full_text = " ".join(current_para_text)
                            norm_text = self.normalize_text(full_text)
                            cursor.execute(
                                "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text, bbox) VALUES (?, ?, ?, ?, ?)",
                                (page_db_id, current_para_num, full_text, norm_text, json.dumps(current_bbox))
                            )
                            para_db_id = cursor.lastrowid
                            cursor.execute(
                                "INSERT INTO fts_paragraphs VALUES (?, ?, ?, ?, ?)",
                                (para_db_id, doc_id, printed_label, current_para_num, norm_text)
                            )

                        current_para_num = res["detected_paragraph_num"]
                        current_para_text = [block_text]
                        current_bbox = b.get("bbox")
                    else:
                        if current_para_num:
                            current_para_text.append(block_text)

                # Salva o último parágrafo da página se houver
                if current_para_num and current_para_text:
                    full_text = " ".join(current_para_text)
                    norm_text = self.normalize_text(full_text)
                    cursor.execute(
                        "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text, bbox) VALUES (?, ?, ?, ?, ?)",
                        (page_db_id, current_para_num, full_text, norm_text, json.dumps(current_bbox))
                    )
                    para_db_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO fts_paragraphs VALUES (?, ?, ?, ?, ?)",
                        (para_db_id, doc_id, printed_label, current_para_num, norm_text)
                    )

            conn.commit()
        return True
