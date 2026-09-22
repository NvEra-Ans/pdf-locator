import unittest
import os
from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.indexing.paragraph_indexer import ParagraphIndexer
from app.indexing.citations_indexer import CitationsIndexer
from app.search.engine import SearchEngine
from app.models.document import ProfileType

class TestSearchEngine(unittest.TestCase):
    """Suíte de Testes Automatizados para Indexação e Busca."""

    def setUp(self):
        self.db_path = "data/test_locator.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        self.db_conn = DatabaseConnection(self.db_path)
        self.schema_mgr = DatabaseSchemaManager(self.db_conn)
        self.schema_mgr.initialize_database()
        self.search_engine = SearchEngine(self.db_conn)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_paragraph_indexing_and_search(self):
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
                ("doc_a.pdf", "/tmp/doc_a.pdf", "Livro A", "hash123", ProfileType.PARAGRAPH_BOOK.value)
            )
            doc_id = cursor.lastrowid
            cursor.execute("INSERT INTO pages (document_id, pdf_page_index, printed_page_label) VALUES (?, ?, ?)", (doc_id, 16, "14A"))
            page_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO paragraphs (page_id, paragraph_number, text, normalized_text) VALUES (?, ?, ?, ?)",
                (page_id, "140", "Este e o texto do paragrafo 140.", "este e o texto do paragrafo 140.")
            )
            conn.commit()

        results = self.search_engine.search(document_id=doc_id, page_label="14A", paragraph_num="140")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].printed_page_label, "14A")
        self.assertEqual(results[0].paragraph_number, "140")

if __name__ == "__main__":
    unittest.main()