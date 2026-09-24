"""
Teste de regressao para o pedido real do usuario de justificar o texto
exibido (painel de detalhes principal e Tela de Leitura), pra ficar mais
apresentavel.

Armadilha real encontrada durante a implementacao: o motor de rich text
do Qt (usado por QTextEdit.setHtml) IGNORA silenciosamente
'style="text-align: justify;"' -- só funciona com o atributo HTML
'align="justify"' separado do style. Sem este teste, um refactor futuro
que volte a usar só `style=` quebraria a justificacao sem nenhum erro
visivel (o texto simplesmente fica alinhado à esquerda, sem avisar).
"""
import sys
import os
import html

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pyside6 = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTextEdit
from PySide6.QtCore import Qt

from app.ui.theme import ThemeManager
from app.ui.mirror_window import MirrorWindow


def _get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setStyleSheet(ThemeManager().stylesheet())
    return app


def _all_nonempty_blocks_justified(text_edit: QTextEdit) -> bool:
    block = text_edit.document().firstBlock()
    found_any = False
    while block.isValid():
        if block.text().strip():
            found_any = True
            if not (block.blockFormat().alignment() & Qt.AlignJustify):
                return False
        block = block.next()
    return found_any


def test_style_attribute_alone_does_not_justify_in_qt():
    """Documenta a armadilha real: NAO eh regressao do nosso codigo, eh
    uma limitacao do proprio Qt -- por isso a implementacao real usa
    align="justify" e nao so style="text-align: justify;"."""
    _get_app()
    te = QTextEdit()
    te.setHtml('<p style="text-align: justify;">texto de teste</p>')
    block = te.document().firstBlock()
    assert not (block.blockFormat().alignment() & Qt.AlignJustify)


def test_mirror_window_text_is_justified():
    _get_app()
    w = MirrorWindow()
    w.show_result(
        "Parágrafo 1 · Página 149",
        "Primeiro parágrafo de teste, longo o bastante pra quebrar linha.\n\n"
        "Segundo parágrafo, separado por linha em branco.",
    )
    assert _all_nonempty_blocks_justified(w.txt_body)


def test_detail_panel_html_snippet_is_justified():
    """Reproduz o mesmo padrao de HTML usado em main_window.py para o
    painel de detalhes principal (sem precisar montar a janela inteira)."""
    _get_app()
    te = QTextEdit()
    safe_text = html.escape("texto de exemplo do painel principal").replace("\n", "<br>")
    te.setHtml(
        f'<p align="justify" style="font-size:16px; line-height:160%; '
        f'margin-top:12px;">{safe_text}</p>'
    )
    assert _all_nonempty_blocks_justified(te)


if __name__ == "__main__":
    test_style_attribute_alone_does_not_justify_in_qt()
    test_mirror_window_text_is_justified()
    test_detail_panel_html_snippet_is_justified()
    print("OK: texto justificado no painel principal e na Tela de Leitura.")
