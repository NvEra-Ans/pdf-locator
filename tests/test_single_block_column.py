"""
Reproducao do bug real: coluna direita inteira extraida pelo PyMuPDF como
UM UNICO bloco (sem quebra interna) -- confirmado com dado real do usuario
no extrato 87 da Parte B (pagina impressa "10-B" do livro de citacoes).

Regra antiga (`len(right) >= 2`) tratava essa pagina como coluna unica,
jogando o bloco gigante da direita para o TOPO da ordem de leitura --
antes de todo o texto da coluna esquerda. Regra corrigida aceita um lado
com 1 bloco so, desde que ele seja alto o bastante pra ser uma coluna de
verdade.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.layout import order_blocks_reading_order


def _block(x0, y0, x1, y1, text):
    return {
        "type": 0,
        "bbox": [x0, y0, x1, y1],
        "lines": [{"spans": [{"text": text}]}],
    }


def _make_page_blocks():
    page_width, page_height = 612.0, 792.0

    header = _block(406, 29, 569, 48, "WILLIAM MARRION BRANHAM")

    # Coluna esquerda: varios blocos pequenos (como o PyMuPDF realmente
    # fatiou no PDF real) -- inclui o inicio do extrato 87.
    left_blocks = [
        _block(43, 49, 299, 156, "intro capa texto anterior"),
        _block(170, 151, 299, 167, "Avergonzados de El, Pag. 34-35"),
        _block(191, 163, 299, 179, "Jeffersonville, Ind., 7-11-65"),
        _block(43, 186, 299, 350, "87 - Estas lineas de texto son directas..."),
        _block(43, 345, 299, 749, "Me doy a la tarea de escribir... Entonces yo dije:"),
    ]

    # Coluna direita: UM UNICO bloco gigante (o caso real do bug), do topo
    # quase ate o rodape da pagina -- sem quebra interna nenhuma.
    right_giant_block = _block(315, 49, 571, 726, "Desde cuando es mas importante tomar las ofrendas...")

    reference_title = _block(473, 721, 569, 737, "Revista Heraldo de Fe")
    reference_date = _block(506, 733, 568, 749, "Febrero de 1956")
    footer = _block(297, 751, 314, 763, "10-B")

    raw_blocks = (
        [footer, header, right_giant_block, reference_title, reference_date]
        + left_blocks
    )
    return raw_blocks, page_width, page_height


def test_single_block_right_column_stays_after_left_column():
    raw_blocks, page_width, page_height = _make_page_blocks()

    ordered = order_blocks_reading_order(raw_blocks, page_width, page_height)

    texts_in_order = [
        "".join(s["text"] for line in b["lines"] for s in line["spans"])
        for b in ordered
    ]

    idx_87_abre = next(i for i, t in enumerate(texts_in_order) if t.startswith("87 -"))
    idx_coluna_direita = next(
        i for i, t in enumerate(texts_in_order) if t.startswith("Desde cuando")
    )

    # O bloco gigante da coluna direita tem que vir DEPOIS de todo o corpo
    # da coluna esquerda (inclusive depois de onde o extrato 87 abre) --
    # nunca antes, senao ele e processado antes do extrato existir e vaza
    # pra entrada anterior, exatamente como aconteceu no caso real.
    assert idx_coluna_direita > idx_87_abre, (
        f"BUG: bloco da coluna direita (indice {idx_coluna_direita}) veio ANTES "
        f"do inicio do extrato 87 (indice {idx_87_abre}) -- isso faz o texto da "
        f"coluna direita vazar pra entrada errada, igual ao bug real reportado."
    )


if __name__ == "__main__":
    test_single_block_right_column_stays_after_left_column()
    print("OK: coluna direita (bloco unico) processada depois da esquerda, como esperado.")
