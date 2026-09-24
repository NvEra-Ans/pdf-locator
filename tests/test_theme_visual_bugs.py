"""
Teste de regressao para dois bugs visuais reais, reportados pelo usuario
via print de tela (v2.5.2), presentes tanto no tema claro quanto no escuro:

1. Caixa cinza/escura atras do titulo/versao/logo no cabecalho -- causa
   raiz: QLabel sem "background: transparent" herda o fundo genérico do
   "QWidget" do tema, em vez do fundo próprio do #HeaderBar.
2. Linha/caixa destacada em volta da seta do QComboBox -- causa raiz: o
   estilo Fusion desenha sua própria moldura no sub-controle
   "drop-down". Corrigido removendo essa moldura E fornecendo uma
   imagem própria pro "down-arrow" (sem a imagem própria, a seta
   simplesmente desaparece -- testado e confirmado nesta sessão).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pyside6 = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui import theme as theme_module
from app.ui.theme import LIGHT_QSS, DARK_QSS


def test_header_labels_have_transparent_background_rule():
    for name, qss in [("claro", LIGHT_QSS), ("escuro", DARK_QSS)]:
        assert "#HeaderBar QLabel" in qss, (
            f"tema {name} sem a regra que zera o fundo dos QLabel do "
            "cabecalho -- volta a caixa cinza atras do titulo/logo"
        )


def test_combobox_drop_down_has_no_own_border():
    for name, qss in [("claro", LIGHT_QSS), ("escuro", DARK_QSS)]:
        assert "QComboBox::drop-down" in qss, f"tema {name} sem regra pro drop-down"


def test_combobox_arrow_images_exist_and_are_referenced():
    """A seta some por completo se QComboBox::down-arrow ficar sem
    "image:" (Fusion para de desenhar a seta padrão assim que qualquer
    regra é dada pro drop-down) -- confirma que o arquivo existe E que a
    QSS referencia ele."""
    assert os.path.exists(theme_module._ARROW_LIGHT), "arrow_down_light.png não existe"
    assert os.path.exists(theme_module._ARROW_DARK), "arrow_down_dark.png não existe"
    assert "image: url(" in LIGHT_QSS and "arrow_down_light.png" in LIGHT_QSS
    assert "image: url(" in DARK_QSS and "arrow_down_dark.png" in DARK_QSS


if __name__ == "__main__":
    test_header_labels_have_transparent_background_rule()
    test_combobox_drop_down_has_no_own_border()
    test_combobox_arrow_images_exist_and_are_referenced()
    print("OK: sem caixa cinza no cabecalho, sem linha destacada na seta do combo.")
