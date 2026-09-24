"""Janela de "Histórico de Pesquisas".

PEDIDO REAL do usuário: um registro cronológico das buscas feitas (e do
que foi encontrado), com um jeito de exportar pra um arquivo de texto
(Bloco de Notas) organizado da mais antiga pra mais nova, e um jeito de
limpar o histórico inteiro quando quiser começar do zero.
"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt

from app.search.history import SearchHistoryManager


class HistoryWindow(QWidget):
    """Janela independente (não-modal) que lista o histórico de
    pesquisas. Cada abertura recarrega do banco, pra sempre refletir o
    estado atual (inclusive buscas feitas depois que essa janela já
    tinha sido aberta antes)."""

    def __init__(self, history_manager: SearchHistoryManager, parent=None):
        super().__init__(parent, Qt.Window)
        self.history_manager = history_manager
        self.setWindowTitle("Localizador — Histórico de Pesquisas")
        self.resize(800, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top_bar = QHBoxLayout()
        self.lbl_count = QLabel("")
        top_bar.addWidget(self.lbl_count)
        top_bar.addStretch(1)

        self.btn_export = QPushButton("💾 Exportar para Bloco de Notas (.txt)")
        self.btn_export.clicked.connect(self._export)
        top_bar.addWidget(self.btn_export)

        self.btn_clear = QPushButton("🗑️ Limpar Histórico")
        self.btn_clear.clicked.connect(self._clear)
        top_bar.addWidget(self.btn_clear)

        layout.addLayout(top_bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Data/Hora", "Livro", "Busca", "Encontrado"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table, stretch=1)

        self.reload()

    def reload(self):
        """Recarrega a tabela a partir do banco -- da mais ANTIGA pra
        mais NOVA (pedido do usuário: cronológico a partir da primeira),
        então a busca mais recente fica no fim da lista, igual um log."""
        entries = self.history_manager.list_history()
        self.table.setRowCount(0)
        for entry in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(self.history_manager.format_timestamp(entry.searched_at)))
            self.table.setItem(row, 1, QTableWidgetItem(entry.document_title))
            self.table.setItem(row, 2, QTableWidgetItem(entry.query_summary))
            self.table.setItem(row, 3, QTableWidgetItem(entry.result_summary))

        self.lbl_count.setText(f"{len(entries)} pesquisa(s) registrada(s)")
        if entries:
            self.table.scrollToBottom()

    def _export(self):
        default_name = "historico_pesquisas.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Histórico de Pesquisas", default_name, "Arquivos de Texto (*.txt)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".txt"):
            file_path += ".txt"

        try:
            count = self.history_manager.export_to_txt(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao exportar", f"Falha ao exportar o histórico:\n{exc}")
            return

        QMessageBox.information(
            self, "Exportado",
            f"{count} pesquisa(s) exportada(s) com sucesso para:\n{file_path}"
        )

    def _clear(self):
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "Histórico vazio", "Não há nenhuma pesquisa registrada ainda.")
            return

        resp = QMessageBox.question(
            self, "Limpar Histórico",
            "Isso vai apagar TODO o histórico de pesquisas, sem volta.\n\n"
            "Deseja continuar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        self.history_manager.clear_history()
        self.reload()
