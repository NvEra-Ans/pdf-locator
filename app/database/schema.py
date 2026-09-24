from app.database.connection import DatabaseConnection

class DatabaseSchemaManager:
    """Cria e gerencia as tabelas e índices FTS5 do banco de dados local."""

    def __init__(self, db_conn: DatabaseConnection):
        self.db_conn = db_conn

    def initialize_database(self) -> None:
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()

            # Tabela de Perfis
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_profiles (
                profile_type TEXT PRIMARY KEY,
                supports_page_search INTEGER NOT NULL,
                supports_paragraph_search INTEGER NOT NULL,
                supports_entry_search INTEGER NOT NULL,
                supports_text_search INTEGER NOT NULL,
                supports_metadata_search INTEGER NOT NULL
            );
            """)

            # Tabela de Documentos
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                title TEXT NOT NULL,
                hash TEXT UNIQUE NOT NULL,
                profile_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_type) REFERENCES document_profiles (profile_type)
            );
            """)

            # Tabela de Páginas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                pdf_page_index INTEGER NOT NULL,
                printed_page_label TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                needs_review INTEGER DEFAULT 0,
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
            );
            """)

            # Tabela de Parágrafos (Perfil Tipo A)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS paragraphs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER NOT NULL,
                paragraph_number TEXT NOT NULL,
                text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                bbox TEXT,
                confidence REAL DEFAULT 1.0,
                needs_review INTEGER DEFAULT 0,
                FOREIGN KEY (page_id) REFERENCES pages (id) ON DELETE CASCADE
            );
            """)

            # Tabela de Entradas / Extratos (Perfil Tipo B)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS text_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                entry_number TEXT NOT NULL,
                full_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                source_title TEXT,
                location TEXT,
                date_str TEXT,
                source_page_ref TEXT,
                confidence REAL DEFAULT 1.0,
                needs_review INTEGER DEFAULT 0,
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
            );
            """)

            # Tabela de Chunks para vincular Entradas às Páginas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS entry_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                page_id INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                bbox TEXT,
                FOREIGN KEY (entry_id) REFERENCES text_entries (id) ON DELETE CASCADE,
                FOREIGN KEY (page_id) REFERENCES pages (id) ON DELETE CASCADE
            );
            """)

            # Tabela de Chunks para vincular Parágrafos às Páginas (Perfil
            # Tipo A) -- mesmo papel do entry_chunks acima, mas pra
            # parágrafos. BUG real encontrado com dado do usuário: um
            # parágrafo que começa numa página e continua na seguinte
            # (comum em livro de sermão corrido) perdia o texto que sobrava
            # na página seguinte por completo, porque o indexador antigo não
            # rastreava o parágrafo aberto entre páginas -- sem essa tabela,
            # não tem como reconstruir corretamente o texto de UMA página
            # física quando um parágrafo é cortado no meio dela.
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS paragraph_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paragraph_id INTEGER NOT NULL,
                page_id INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                bbox TEXT,
                FOREIGN KEY (paragraph_id) REFERENCES paragraphs (id) ON DELETE CASCADE,
                FOREIGN KEY (page_id) REFERENCES pages (id) ON DELETE CASCADE
            );
            """)

            # Índices nas colunas de chave estrangeira / busca frequente. SEM
            # eles, toda exclusão ou reimportação de documento (que dispara
            # DELETE em cascata, ex.: documento -> páginas -> entry_chunks)
            # obriga o SQLite a varrer a tabela inteira pra achar as linhas
            # relacionadas — numa tabela com dezenas de milhares de linhas
            # (entry_chunks tem uma linha por linha de texto do PDF), isso é
            # visivelmente lento. Com índice, vira uma busca quase instantânea.
            # IF NOT EXISTS torna seguro rodar em bancos já existentes também.
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pages_document_id ON pages (document_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pages_printed_label ON pages (printed_page_label);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_paragraphs_page_id ON paragraphs (page_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_text_entries_document_id ON text_entries (document_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_text_entries_entry_number ON text_entries (entry_number);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entry_chunks_entry_id ON entry_chunks (entry_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entry_chunks_page_id ON entry_chunks (page_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_paragraph_chunks_paragraph_id ON paragraph_chunks (paragraph_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_paragraph_chunks_page_id ON paragraph_chunks (page_id);")

            # Tabelas Virtuais SQLite FTS5 para busca textual ultra-rápida
            cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_paragraphs USING fts5(
                paragraph_id UNINDEXED,
                document_id UNINDEXED,
                page_label,
                paragraph_number,
                content
            );
            """)

            cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_entries USING fts5(
                entry_id UNINDEXED,
                document_id UNINDEXED,
                printed_page_label,
                entry_number,
                content,
                source_title,
                location
            );
            """)

            # Carga dos Perfis Padrão
            cursor.execute("""
            INSERT OR IGNORE INTO document_profiles VALUES 
            ('PARAGRAPH_BOOK', 1, 1, 0, 1, 0),
            ('CITATIONS_BOOK', 1, 0, 1, 1, 1);
            """)

            conn.commit()