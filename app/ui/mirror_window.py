"""Janela de "Tela de Leitura" (espelhamento pro segundo monitor).

PEDIDO REAL do usuário: o app é usado durante tradução simultânea --
o tradutor precisa ter o texto encontrado na sua frente, num segundo
monitor, sem precisar fazer a busca ele mesmo. Decisões confirmadas
com o usuário:
  - Texto aparece automaticamente sempre que uma busca é feita no app
    principal (sem precisar clicar em nada nesta janela).
  - Texto puro, sem os controles de busca -- só o texto e a referência
    de página/parágrafo em algum canto.
  - Fonte grande por padrão, com controle pra aumentar/diminuir.
  - Posição da janela é responsabilidade do usuário (arrasta pro
    monitor 2 manualmente toda vez que abre) -- não salva posição
    entre sessões.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

DEFAULT_FONT_SIZE = 32
MIN_FONT_SIZE = 14
MAX_FONT_SIZE = 96
FONT_STEP = 4


class MirrorWindow(QWidget):
    """Janela independente (não-modal) só com o texto do último
    resultado selecionado no app principal. Fica aberta enquanto o
    usuário não fechar, e é atualizada via show_result()."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Localizador — Tela de Leitura")
        self.resize(900, 600)
        self._font_size = DEFAULT_FONT_SIZE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        self.lbl_ref = QLabel("")
        self.lbl_ref.setObjectName("MirrorRefLabel")
        top_bar.addWidget(self.lbl_ref)
        top_bar.addStretch(1)

        self.btn_font_minus = QPushButton("A−")
        self.btn_font_minus.setFixedWidth(44)
        self.btn_font_minus.setToolTip("Diminuir fonte")
        self.btn_font_minus.clicked.connect(self._decrease_font)
        top_bar.addWidget(self.btn_font_minus)

        self.btn_font_plus = QPushButton("A+")
        self.btn_font_plus.setFixedWidth(44)
        self.btn_font_plus.setToolTip("Aumentar fonte")
        self.btn_font_plus.clicked.connect(self._increase_font)
        top_bar.addWidget(self.btn_font_plus)

        layout.addLayout(top_bar)

        self.txt_body = QTextEdit()
        self.txt_body.setObjectName("MirrorBodyText")
        self.txt_body.setReadOnly(True)
        self.txt_body.setFrameStyle(0)
        layout.addWidget(self.txt_body, stretch=1)

        self._apply_font()

    # ---------------------------------------------------------------- Fonte

    def _apply_font(self):
        body_font = QFont()
        body_font.setPointSize(self._font_size)
        self.txt_body.setFont(body_font)

        ref_font = QFont()
        ref_font.setPointSize(max(12, self._font_size // 2))
        ref_font.setBold(True)
        self.lbl_ref.setFont(ref_font)

    def _increase_font(self):
        self._font_size = min(MAX_FONT_SIZE, self._font_size + FONT_STEP)
        self._apply_font()

    def _decrease_font(self):
        self._font_size = max(MIN_FONT_SIZE, self._font_size - FONT_STEP)
        self._apply_font()

    # ------------------------------------------------------------ Conteúdo

    def show_result(self, reference: str, text: str):
        """Chamado pela janela principal sempre que um resultado é
        selecionado/exibido -- atualiza esta janela automaticamente,
        sem nenhuma ação do lado de quem está olhando o monitor 2."""
        self.lbl_ref.setText(reference)
        self.txt_body.setPlainText(text)
