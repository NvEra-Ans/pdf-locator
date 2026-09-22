import sys
import os
import html
import hashlib
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QTextEdit,
    QCheckBox, QFileDialog, QMessageBox, QHeaderView, QSplitter, QInputDialog,
    QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QFont

from app.database.connection import DatabaseConnection
from app.search.engine import SearchEngine
from app.models.document import ProfileType, DocumentIndexProfile
from app.indexing.paragraph_indexer import ParagraphIndexer
from app.indexing.citations_indexer import CitationsIndexer
from app.version import APP_NAME, APP_NAME_SHORT, APP_VERSION
from app.ui.theme import ThemeManager
from app.paths import get_db_path

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")


class MainWindow(QMainWindow):
    """Janela Principal do Aplicativo Desktop Localizador Inteligente."""

    def __init__(self, db_conn: DatabaseConnection = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME_SHORT} — v{APP_VERSION}")
        self.resize(1200, 800)

        icon_path = os.path.join(ASSETS_DIR, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.theme = ThemeManager()

        # Se nenhuma conexão for passada (ex.: uso direto fora de app/main.py),
        # cria uma usando o mesmo caminho "seguro para escrita" (get_db_path).
        self.db_conn = db_conn if db_conn is not None else DatabaseConnection(get_db_path())
        self.search_engine = SearchEngine(self.db_conn)

        self._init_ui()
        self._apply_theme()
        self._load_documents()

    # ------------------------------------------------------------------ UI

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(12)

        body_layout.addLayout(self._build_document_row())
        body_layout.addLayout(self._build_search_row())
        body_layout.addLayout(self._build_text_row())
        body_layout.addWidget(self._build_results_splitter(), stretch=1)

        main_layout.addWidget(body, stretch=1)

        self.current_results = []

    def _build_header(self):
        header = QWidget()
        header.setObjectName("HeaderBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)

        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        logo_label = QLabel()
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaledToHeight(40, Qt.SmoothTransformation)
            logo_label.setPixmap(pix)
        layout.addWidget(logo_label)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel(APP_NAME_SHORT)
        title.setObjectName("AppTitleLabel")
        version = QLabel(f"Associação Missionária A Voz do Último Dia · v{APP_VERSION}")
        version.setObjectName("AppVersionLabel")
        title_box.addWidget(title)
        title_box.addWidget(version)
        layout.addLayout(title_box)

        layout.addStretch(1)

        self.btn_theme = QPushButton("🌙 Modo Escuro")
        self.btn_theme.setObjectName("ThemeToggle")
        self.btn_theme.clicked.connect(self._toggle_theme)
        layout.addWidget(self.btn_theme)

        self.btn_about = QPushButton("Sobre")
        self.btn_about.clicked.connect(self._show_about)
        layout.addWidget(self.btn_about)

        return header

    def _build_document_row(self):
        doc_box = QHBoxLayout()
        doc_box.addWidget(QLabel("Documento:"))
        self.combo_docs = QComboBox()
        self.combo_docs.currentIndexChanged.connect(self._on_document_changed)
        doc_box.addWidget(self.combo_docs, stretch=2)

        self.btn_import = QPushButton("Importar PDF...")
        self.btn_import.clicked.connect(self._import_pdf)
        doc_box.addWidget(self.btn_import)

        self.btn_delete_doc = QPushButton("Excluir Documento")
        self.btn_delete_doc.clicked.connect(self._delete_document)
        doc_box.addWidget(self.btn_delete_doc)
        return doc_box

    def _build_search_row(self):
        search_box = QHBoxLayout()

        self.lbl_page = QLabel("Página:")
        self.txt_page = QLineEdit()
        self.txt_page.setPlaceholderText("ex: 14A")
        self.txt_page.returnPressed.connect(self._perform_search)
        search_box.addWidget(self.lbl_page)
        search_box.addWidget(self.txt_page)

        self.lbl_para = QLabel("Parágrafo:")
        self.txt_para = QLineEdit()
        self.txt_para.setPlaceholderText("ex: 140")
        self.txt_para.returnPressed.connect(self._perform_search)
        search_box.addWidget(self.lbl_para)
        search_box.addWidget(self.txt_para)

        self.lbl_entry = QLabel("Extrato:")
        self.txt_entry = QLineEdit()
        self.txt_entry.setPlaceholderText("ex: 1057")
        self.txt_entry.returnPressed.connect(self._perform_search)
        search_box.addWidget(self.lbl_entry)
        search_box.addWidget(self.txt_entry)

        self.chk_fuzzy = QCheckBox("Busca Aproximada (Fuzzy)")
        search_box.addWidget(self.chk_fuzzy)
        return search_box

    def _build_text_row(self):
        text_box = QHBoxLayout()
        text_box.addWidget(QLabel("Texto:"))
        self.txt_text = QLineEdit()
        self.txt_text.setPlaceholderText("Digite o trecho a pesquisar...")
        self.txt_text.returnPressed.connect(self._perform_search)
        text_box.addWidget(self.txt_text)

        self.btn_search = QPushButton("Pesquisar")
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_search.clicked.connect(self._perform_search)
        text_box.addWidget(self.btn_search)
        return text_box

    def _build_results_splitter(self):
        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Página", "Parágrafo / Extrato", "Match", "Trecho Encontrado"])
        header = self.table.horizontalHeader()
        # Colunas 0-2 (Página, Parágrafo/Extrato, Match) se ajustam ao próprio
        # conteúdo/cabeçalho, em vez de ficar com a largura padrão fixa do Qt
        # (que cortava o texto do cabeçalho com a fonte maior). A última
        # coluna (Trecho Encontrado) ocupa o espaço restante.
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setMinimumSectionSize(90)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.itemSelectionChanged.connect(self._on_result_selected)
        splitter.addWidget(self.table)

        detail_widget = QWidget()
        detail_widget.setObjectName("DetailPanel")
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(16, 16, 16, 16)

        self.lbl_detail_header = QLabel("Detalhes do Texto Selecionado")
        self.lbl_detail_header.setStyleSheet("font-weight: 600; font-size: 13px;")
        detail_layout.addWidget(self.lbl_detail_header)

        self.txt_detail = QTextEdit()
        self.txt_detail.setObjectName("DetailText")
        self.txt_detail.setReadOnly(True)
        detail_font = QFont()
        detail_font.setPointSize(13)
        self.txt_detail.setFont(detail_font)
        detail_layout.addWidget(self.txt_detail)

        btn_action_box = QHBoxLayout()
        self.btn_copy_text = QPushButton("📋 Copiar Texto")
        self.btn_copy_ref = QPushButton("🔖 Copiar Referência")
        self.btn_open_pdf = QPushButton("📄 Abrir PDF nesta Página")

        self.btn_copy_text.clicked.connect(self._copy_text)
        self.btn_copy_ref.clicked.connect(self._copy_ref)
        self.btn_open_pdf.clicked.connect(self._open_pdf)

        btn_action_box.addWidget(self.btn_copy_text)
        btn_action_box.addWidget(self.btn_copy_ref)
        btn_action_box.addWidget(self.btn_open_pdf)
        btn_action_box.addStretch(1)
        detail_layout.addLayout(btn_action_box)

        splitter.addWidget(detail_widget)
        splitter.setSizes([400, 350])
        return splitter

    # --------------------------------------------------------------- Tema

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(self.theme.stylesheet())
        self.btn_theme.setText("☀️ Modo Claro" if self.theme.is_dark() else "🌙 Modo Escuro")

    def _toggle_theme(self):
        self.theme.set_dark(not self.theme.is_dark())
        self._apply_theme()

    def _show_about(self):
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        msg = QMessageBox(self)
        msg.setWindowTitle("Sobre")
        msg.setText(
            f"<b>{APP_NAME}</b><br>"
            f"Versão {APP_VERSION}<br><br>"
            "Associação Missionária A Voz do Último Dia<br>"
            "Aplicativo desktop para indexação e pesquisa estruturada em PDFs."
        )
        if os.path.exists(logo_path):
            msg.setIconPixmap(QPixmap(logo_path).scaledToWidth(96, Qt.SmoothTransformation))
        msg.exec()

    # ------------------------------------------------------------ Documentos

    def _load_documents(self):
        self.combo_docs.clear()
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, profile_type FROM documents")
            rows = cursor.fetchall()
            for r in rows:
                self.combo_docs.addItem(r["title"], userData={"id": r["id"], "profile": r["profile_type"]})

    def _on_document_changed(self):
        idx = self.combo_docs.currentIndex()
        if idx < 0:
            return
        data = self.combo_docs.itemData(idx)
        profile_type = ProfileType(data["profile"])

        if profile_type == ProfileType.PARAGRAPH_BOOK:
            self.lbl_para.setVisible(True)
            self.txt_para.setVisible(True)
            self.lbl_entry.setVisible(False)
            self.txt_entry.setVisible(False)
        elif profile_type == ProfileType.CITATIONS_BOOK:
            self.lbl_para.setVisible(False)
            self.txt_para.setVisible(False)
            self.lbl_entry.setVisible(True)
            self.txt_entry.setVisible(True)

    def _import_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecionar PDF", "", "Arquivos PDF (*.pdf)")
        if not file_path:
            return

        filename = os.path.basename(file_path)
        items = ["Livro Estruturado por Parágrafos (Tipo A)", "Livro de Citações / Extratos (Tipo B)"]
        item, ok = QInputDialog.getItem(self, "Selecionar Perfil", "Selecione o perfil do documento:", items, 0, False)
        if not ok:
            return

        prof_type = ProfileType.PARAGRAPH_BOOK if item == items[0] else ProfileType.CITATIONS_BOOK

        try:
            # Hash do CONTEÚDO do arquivo (não do caminho) — assim o mesmo PDF
            # sempre gera o mesmo hash entre execuções diferentes do app, e dá
            # pra detectar de verdade "esse arquivo já foi importado antes".
            file_hash = hashlib.sha256()
            with open(file_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    file_hash.update(chunk)
            file_hash = file_hash.hexdigest()

            with self.db_conn.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM documents WHERE hash = ?", (file_hash,))
                existing = cursor.fetchone()

                if existing:
                    resp = QMessageBox.question(
                        self, "Documento já importado",
                        "Esse arquivo já tinha sido importado antes.\n\n"
                        "Deseja reindexar (apagar a indexação antiga e refazer do zero, "
                        "sem duplicar na lista)?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if resp != QMessageBox.Yes:
                        return
                    doc_id = existing["id"]
                    # Apaga tudo que dependia desse documento. As tabelas normais têm
                    # ON DELETE CASCADE, mas as tabelas virtuais FTS5 não suportam
                    # chave estrangeira, então precisam ser limpas manualmente.
                    cursor.execute("DELETE FROM fts_entries WHERE document_id = ?", (doc_id,))
                    cursor.execute("DELETE FROM fts_paragraphs WHERE document_id = ?", (doc_id,))
                    cursor.execute("DELETE FROM pages WHERE document_id = ?", (doc_id,))
                    cursor.execute("DELETE FROM text_entries WHERE document_id = ?", (doc_id,))
                    cursor.execute(
                        "UPDATE documents SET filename = ?, filepath = ?, title = ?, profile_type = ? WHERE id = ?",
                        (filename, file_path, filename, prof_type.value, doc_id)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO documents (filename, filepath, title, hash, profile_type) VALUES (?, ?, ?, ?, ?)",
                        (filename, file_path, filename, file_hash, prof_type.value)
                    )
                    doc_id = cursor.lastrowid

                conn.commit()

            if prof_type == ProfileType.PARAGRAPH_BOOK:
                indexer = ParagraphIndexer(self.db_conn)
            else:
                indexer = CitationsIndexer(self.db_conn)

            indexer.index_document(doc_id, file_path)

        except Exception as exc:
            QMessageBox.critical(self, "Erro ao indexar", f"Falha ao indexar o documento:\n{exc}")
            return

        QMessageBox.information(self, "Sucesso", "Documento indexado com sucesso!")
        self._load_documents()

    def _delete_document(self):
        idx = self.combo_docs.currentIndex()
        if idx < 0:
            QMessageBox.information(self, "Excluir Documento", "Nenhum documento selecionado.")
            return

        doc_title = self.combo_docs.currentText()
        doc_id = self.combo_docs.itemData(idx)["id"]

        resp = QMessageBox.question(
            self, "Excluir Documento",
            f"Tem certeza que deseja excluir a indexação de:\n\n\"{doc_title}\"\n\n"
            "Isso remove todas as páginas, parágrafos/extratos e o índice de busca "
            "desse documento (o arquivo PDF original no seu computador não é afetado). "
            "Essa ação não pode ser desfeita.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        try:
            with self.db_conn.get_connection() as conn:
                cursor = conn.cursor()
                # As tabelas normais têm ON DELETE CASCADE (pages, text_entries,
                # paragraphs, entry_chunks), mas as tabelas virtuais FTS5 não
                # suportam chave estrangeira e precisam ser limpas manualmente.
                cursor.execute("DELETE FROM fts_entries WHERE document_id = ?", (doc_id,))
                cursor.execute("DELETE FROM fts_paragraphs WHERE document_id = ?", (doc_id,))
                cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                conn.commit()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao excluir", f"Falha ao excluir o documento:\n{exc}")
            return

        self.table.setRowCount(0)
        self.current_results = []
        self.txt_detail.clear()
        self._load_documents()
        QMessageBox.information(self, "Excluído", "Documento removido com sucesso.")

    # ---------------------------------------------------------------- Busca

    def _perform_search(self):
        idx = self.combo_docs.currentIndex()
        if idx < 0:
            return
        doc_id = self.combo_docs.itemData(idx)["id"]

        page = self.txt_page.text().strip() or None
        para = self.txt_para.text().strip() or None
        entry = self.txt_entry.text().strip() or None
        text = self.txt_text.text().strip() or None
        fuzzy = self.chk_fuzzy.isChecked()

        self.current_results = self.search_engine.search(
            document_id=doc_id,
            page_label=page,
            paragraph_num=para,
            entry_num=entry,
            text_query=text,
            use_fuzzy=fuzzy
        )

        self.table.setRowCount(0)
        for r in self.current_results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r.printed_page_label))
            num_label = r.paragraph_number if r.paragraph_number else (r.entry_number or "N/A")
            self.table.setItem(row, 1, QTableWidgetItem(num_label))
            self.table.setItem(row, 2, QTableWidgetItem(f"{r.match_score:.0f}%"))
            self.table.setItem(row, 3, QTableWidgetItem(r.text_snippet))

        self.txt_detail.clear()
        if not self.current_results:
            self.lbl_detail_header.setText("Nenhum resultado encontrado")
        else:
            self.lbl_detail_header.setText(f"{len(self.current_results)} resultado(s) encontrado(s)")

    def _on_result_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.current_results):
            return
        res = self.current_results[row]
        num_label = res.paragraph_number if res.paragraph_number else res.entry_number
        num_kind = "Parágrafo" if res.paragraph_number else "Extrato"

        safe_text = html.escape(res.full_text).replace("\n", "<br>")
        html_parts = [
            f'<span style="background-color:#F3E7C3; color:#6B5514; border-radius:10px; '
            f'padding:2px 8px; font-weight:600; font-size:12px;">'
            f'{num_kind} {html.escape(str(num_label))} · Página {html.escape(res.printed_page_label)}</span>',
            f'<p style="font-size:16px; line-height:160%; margin-top:12px;">{safe_text}</p>',
        ]

        # Referência da citação (título em negrito + local/data), do mesmo jeito
        # que aparece no livro ao final de cada extrato — só existe para o
        # perfil Tipo B (Livro de Citações), quando o indexador conseguiu
        # reconhecer essas duas linhas separadas do corpo do texto.
        if res.source_title or res.location or res.date_str:
            title_color, meta_color, border_color = (
                ("#F2E7C6", "#B9BEC7", "rgba(255,255,255,0.15)") if self.theme.is_dark()
                else ("#6B5514", "#5B6270", "rgba(0,0,0,0.12)")
            )
            loc_date = ", ".join(x for x in [res.location, res.date_str] if x)
            html_parts.append(
                f'<div style="margin-top:14px; padding-top:10px; border-top:1px solid {border_color}; '
                f'text-align:center;">'
                + (f'<div style="font-weight:700; font-size:14px; color:{title_color};">'
                   f'{html.escape(res.source_title or "")}</div>' if res.source_title else "")
                + (f'<div style="font-size:13px; color:{meta_color};">{html.escape(loc_date)}</div>' if loc_date else "")
                + '</div>'
            )

        self.txt_detail.setHtml("".join(html_parts))

    # --------------------------------------------------------------- Ações

    def _copy_text(self):
        row = self.table.currentRow()
        if row >= 0:
            res = self.current_results[row]
            QApplication.clipboard().setText(res.full_text)

    def _copy_ref(self):
        row = self.table.currentRow()
        if row >= 0:
            res = self.current_results[row]
            num_str = f", parágrafo {res.paragraph_number}" if res.paragraph_number else f", extrato {res.entry_number}"
            ref = f"Página {res.printed_page_label}{num_str} ({res.document_title})"
            QApplication.clipboard().setText(ref)

    def _open_pdf(self):
        row = self.table.currentRow()
        if row >= 0:
            res = self.current_results[row]
            QMessageBox.information(self, "Abrir PDF", f"Navegando para o índice de página física: {res.pdf_page_index}")
