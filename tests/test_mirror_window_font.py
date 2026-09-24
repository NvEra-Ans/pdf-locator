"""
Teste de regressao para o bug real reportado pelo usuario: na Tela de
Leitura (segundo monitor), clicar em "A+" mudava a fonte de uma vez so
(salto), mas "A-" ia gradativamente. Causa raiz confirmada: o tema
global do app (app/ui/theme.py) tem uma regra "QWidget { font-size:
13px; }" que competia com o QFont definido programaticamente no texto
da Tela de Leitura -- o tamanho so passava a responder de forma
confiavel depois do primeiro clique "vencer" essa disputa.

Corrigido aplicando o tamanho via CSS local do proprio widget
(setStyleSheet), que tem prioridade sobre a regra global do tema.
Este teste roda com o TEMA REAL aplicado (nao um ambiente limpo), que
foi justamente o que reproduziu o bug originalmente -- testar sem o
tema aplicado NAO pegaria essa regressao de volta.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pyside6 = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.theme import ThemeManager
from app.ui.mirror_window import MirrorWindow, DEFAULT_FONT_SIZE, FONT_STEP


def _get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    # Aplica o tema real -- é exatamente essa regra global que causava o
    # bug, então o teste precisa do mesmo QSS que o app usa de verdade.
    app.setStyleSheet(ThemeManager().stylesheet())
    return app


def test_font_size_reflected_immediately_from_first_click_both_directions():
    _get_app()
    w = MirrorWindow()

    assert f"{DEFAULT_FONT_SIZE}pt" in w.txt_body.styleSheet()

    # Primeiro clique em "+" precisa refletir o tamanho novo imediatamente
    # (sem "salto" causado pela disputa com o tema global).
    w._increase_font()
    assert w._font_size == DEFAULT_FONT_SIZE + FONT_STEP
    assert f"{DEFAULT_FONT_SIZE + FONT_STEP}pt" in w.txt_body.styleSheet()

    # Primeiro clique em "-" (a partir de um estado recem-criado, sem
    # nenhum "+" antes) tambem precisa refletir de imediato -- era esse o
    # caminho que já funcionava, mas serve de comparação simétrica.
    w2 = MirrorWindow()
    w2._decrease_font()
    assert w2._font_size == DEFAULT_FONT_SIZE - FONT_STEP
    assert f"{DEFAULT_FONT_SIZE - FONT_STEP}pt" in w2.txt_body.styleSheet()


def test_font_size_steps_are_symmetric_in_both_directions():
    _get_app()
    w = MirrorWindow()

    sizes_up = [DEFAULT_FONT_SIZE]
    for _ in range(3):
        w._increase_font()
        sizes_up.append(w._font_size)

    sizes_down = [sizes_up[-1]]
    for _ in range(3):
        w._decrease_font()
        sizes_down.append(w._font_size)

    # Volta exatamente pro tamanho inicial -- os passos pra cima e pra
    # baixo têm que ser o mesmo incremento (FONT_STEP) em ambas direções.
    assert sizes_down[-1] == DEFAULT_FONT_SIZE
    assert sizes_up == [32, 36, 40, 44]
    assert sizes_down == [44, 40, 36, 32]


if __name__ == "__main__":
    test_font_size_reflected_immediately_from_first_click_both_directions()
    test_font_size_steps_are_symmetric_in_both_directions()
    print("OK: fonte da Tela de Leitura muda de forma consistente e simetrica em ambos os sentidos.")
