from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

class ReviewDialog(QDialog):
    """Diálogo de Revisão Manual para validação e correção de confiança em rótulos e parágrafos."""

    def __init__(self, page_label: str, para_or_entry_num: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revisar Estrutura Detectada")
        self.resize(400, 200)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Rótulo da Página Impressa:"))
        self.page_input = QLineEdit(page_label)
        layout.addWidget(self.page_input)

        layout.addWidget(QLabel("Número do Parágrafo / Extrato:"))
        self.number_input = QLineEdit(para_or_entry_num)
        layout.addWidget(self.number_input)

        btn_box = QHBoxLayout()
        self.btn_save = QPushButton("Confirmar & Salvar")
        self.btn_cancel = QPushButton("Cancelar")
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)