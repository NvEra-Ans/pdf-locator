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
  - Fica ativa mesmo se o app principal for minimizado (pedido real do
    usuário -- ver nota em MainWindow._toggle_mirror_window sobre não
    passar `self` como parent, exatamente por causa disso).
  - Tem um modo Tela Cheia (sem a barra do Windows com
    minimizar/maximizar/fechar), pra apresentação/tradução -- sai do
    modo tela cheia clicando na janela e apertando Esc, ou clicando de
    novo no botão.
"""
import html

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
from PySide6.QtCore import Qt

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

        # PEDIDO REAL do usuário: modo apresentação, sem a barra do
        # Windows (minimizar/maximizar/fechar) ocupando espaço na tela.
        self.btn_fullscreen = QPushButton("⛶ Tela Cheia")
        self.btn_fullscreen.setToolTip("Tela cheia, sem a barra de título (clique na janela e aperte Esc pra voltar)")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        top_bar.addWidget(self.btn_fullscreen)

        layout.addLayout(top_bar)

        self.txt_body = QTextEdit()
        self.txt_body.setObjectName("MirrorBodyText")
        self.txt_body.setReadOnly(True)
        self.txt_body.setFrameStyle(0)
        layout.addWidget(self.txt_body, stretch=1)

        self._apply_font()

    # ---------------------------------------------------------------- Fonte

    def _apply_font(self):
        # BUG real encontrado pelo usuário: o tema do app tem uma regra
        # global "QWidget { font-size: 13px; }" (app/ui/theme.py) que
        # compete com o tamanho de fonte definido programaticamente via
        # QFont/setFont() nestes widgets -- resultado: o tamanho ficava
        # "preso" no valor do tema até o primeiro clique em "A+", que então
        # sobrescrevia de uma vez (salto visível), enquanto cliques
        # seguintes (inclusive "A-") pareciam normais porque a disputa já
        # tinha sido resolvida. Confirmado reproduzindo com o tema real
        # aplicado: font().pointSize() ficava em -1 (tamanho em pixels
        # herdado do tema) até a primeira chamada de setFont() "vencer".
        #
        # Corrigido aplicando o tamanho via CSS local do próprio widget
        # (setStyleSheet), que tem prioridade sobre a regra global do tema
        # -- em vez de brigar com o QSS usando QFont, usamos QSS pra
        # sobrescrever QSS. Efeito: cada clique em A+/A- muda o tamanho de
        # forma consistente e imediata, desde o primeiro clique.
        self.txt_body.setStyleSheet(f"QTextEdit#MirrorBodyText {{ font-size: {self._font_size}pt; }}")

        ref_size = max(12, self._font_size // 2)
        self.lbl_ref.setStyleSheet(f"QLabel#MirrorRefLabel {{ font-size: {ref_size}pt; font-weight: 700; }}")

    def _increase_font(self):
        self._font_size = min(MAX_FONT_SIZE, self._font_size + FONT_STEP)
        self._apply_font()

    def _decrease_font(self):
        self._font_size = max(MIN_FONT_SIZE, self._font_size - FONT_STEP)
        self._apply_font()

    # ----------------------------------------------------------- Tela Cheia

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("⛶ Tela Cheia")
        else:
            self.showFullScreen()
            self.btn_fullscreen.setText("⛶ Sair da Tela Cheia")

    def keyPressEvent(self, event):
        # PEDIDO REAL do usuário: apertar Esc (com a janela em foco --
        # "clicar na janela e digitar esc") sai do modo tela cheia e
        # devolve a barra de título, sem precisar achar o botão (que fica
        # menos visível/acessível em tela cheia real).
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------ Conteúdo

    def show_result(self, reference: str, text: str):
        """Chamado pela janela principal sempre que um resultado é
        selecionado/exibido -- atualiza esta janela automaticamente,
        sem nenhuma ação do lado de quem está olhando o monitor 2."""
        self.lbl_ref.setText(reference)

        # Texto justificado (pedido do usuário, pra ficar mais
        # apresentável/parecido com o livro impresso) -- precisa ser HTML
        # com um <p> por parágrafo, e não um único bloco, porque assim a
        # última linha de cada parágrafo continua alinhada à esquerda em
        # vez de esticada (comportamento padrão de justificação
        # tipográfica). setPlainText não permite controlar alinhamento por
        # parágrafo de forma confiável, por isso trocamos pra setHtml.
        # Nota: "text-align: justify" via atributo style NÃO funciona no
        # mecanismo de rich text do Qt (testado e confirmado -- o
        # alinhamento fica ignorado); precisa do atributo HTML
        # align="justify" separado do style.
        paragraphs = text.split("\n\n")
        html_paragraphs = "".join(
            f'<p align="justify">{html.escape(p).replace(chr(10), "<br>")}</p>'
            for p in paragraphs
        )
        self.txt_body.setHtml(html_paragraphs)
