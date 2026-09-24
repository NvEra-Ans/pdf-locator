"""
Reordenação de blocos de texto em ordem de leitura real (coluna a coluna).

Problema que este módulo resolve
---------------------------------
O PyMuPDF (fitz) devolve os blocos de uma página em `page.get_text("dict")["blocks"]`
aproximadamente na ordem em que aparecem no content stream do PDF — o que, na prática,
para layouts de 2 colunas, costuma intercalar blocos da coluna esquerda e da coluna
direita conforme a posição vertical (y) de cada um, e não "primeiro toda a coluna
esquerda, depois toda a coluna direita".

Isso quebra a extração de parágrafos/extratos que continuam de uma coluna para a
outra: o indexador processa os blocos na ordem errada, encontra um número de novo
extrato que na verdade pertence à coluna direita mas está na mesma altura do fim do
texto da coluna esquerda, e corta o texto anterior prematuramente.

A solução: detectar se a página tem um "gutter" (vão central sem nenhum bloco de
texto do corpo cruzando) e, se houver, particionar os blocos em coluna esquerda e
coluna direita, ordenar cada coluna por posição vertical (topo -> base) e concatenar
esquerda + direita. Documentos de coluna única continuam funcionando normalmente
(fallback: ordenação simples por y).
"""

from typing import List, Dict, Any


def _block_text(block: Dict[str, Any]) -> str:
    text = ""
    for line in block.get("lines", []):
        text += "".join(s.get("text", "") for s in line.get("spans", [])) + " "
    return text.strip()


def order_blocks_reading_order(
    blocks: List[Dict[str, Any]],
    page_width: float,
    page_height: float,
    header_zone: float = 0.12,
    footer_zone: float = 0.88,
) -> List[Dict[str, Any]]:
    """Recebe os blocos de texto (type == 0) de uma página e devolve a mesma lista,
    reordenada na ordem de leitura correta: cabeçalho (se houver) -> corpo (coluna
    esquerda inteira, depois coluna direita inteira, cada uma topo->base) -> rodapé.

    Blocos vazios ou que não são de texto (imagens, type != 0) são ignorados.
    """
    text_blocks = [b for b in blocks if b.get("type") == 0 and _block_text(b)]
    if not text_blocks:
        return []

    header, footer, body = [], [], []
    for b in text_blocks:
        bbox = b.get("bbox", [0, 0, 0, 0])
        top_y, bottom_y = bbox[1], bbox[3]
        if bottom_y <= page_height * header_zone:
            header.append(b)
        elif top_y >= page_height * footer_zone:
            footer.append(b)
        else:
            body.append(b)

    header.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    footer.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    body_ordered = _order_body_by_columns(body, page_width, page_height)

    return header + body_ordered + footer


def _side_is_a_real_column(blocks: List[Dict[str, Any]], page_height: float) -> bool:
    """Decide se um lado (esquerda ou direita) tem conteúdo suficiente pra ser
    considerado uma coluna de verdade.

    BUG real encontrado com dado do usuario: a regra antiga exigia PELO MENOS
    2 blocos de cada lado pra tratar a pagina como "2 colunas". Isso parte do
    pressuposto de que uma coluna inteira sempre vem fatiada em varios blocos
    pelo PyMuPDF -- mas isso NAO e garantido. No extrato real 87 da Parte B
    (pagina impressa "10-B"), a coluna direita inteira (59 linhas, do topo ate
    quase o rodape da pagina) saiu do PyMuPDF como UM UNICO bloco, porque o
    paragrafo nao tinha nenhuma quebra interna. Com a regra antiga, "right >= 2"
    dava False, a pagina inteira caia no fallback de ordenar so por Y (coluna
    unica), e esse bloco gigante -- que comeca no TOPO da pagina -- ficava
    ordenado ANTES de todo o texto da coluna esquerda, inclusive antes do "87 -"
    que abre o extrato. Resultado: o paragrafo inteiro da coluna direita era
    processado antes do extrato 87 existir e ia parar dentro da entrada
    ANTERIOR (a que estava ativa naquele ponto) -- sumindo por completo do
    extrato 87-B na busca.
    Corrigido aceitando um lado com um UNICO bloco como coluna valida, desde
    que esse bloco seja "alto" o bastante (>= 25% da altura da pagina) pra ser,
    de fato, uma coluna inteira -- e nao um bloco pequeno perdido do lado
    errado (que e exatamente o caso que a regra de 2+ blocos queria evitar).
    RISCO CONHECIDO (nao verificado): esse limiar de 25% e uma estimativa
    baseada só neste caso real confirmado; não tenho como garantir que ele
    cobre todo layout possível do livro sem rodar contra o livro inteiro.
    """
    if len(blocks) >= 2:
        return True
    if len(blocks) == 1:
        block_height = blocks[0]["bbox"][3] - blocks[0]["bbox"][1]
        return block_height >= page_height * 0.25
    return False


def _order_body_by_columns(
    body: List[Dict[str, Any]], page_width: float, page_height: float
) -> List[Dict[str, Any]]:
    if len(body) <= 1:
        return body

    mid = page_width / 2.0
    tolerance = page_width * 0.06  # margem de tolerância ao redor do centro da página

    left, right, ambiguous = [], [], []
    for b in body:
        x0, x1 = b["bbox"][0], b["bbox"][2]
        if x1 <= mid + tolerance:
            left.append(b)
        elif x0 >= mid - tolerance:
            right.append(b)
        else:
            ambiguous.append(b)  # bloco que cruza o centro da página (largura total)

    # Só tratamos como "2 colunas" se as duas colunas tiverem conteúdo real e os
    # blocos ambíguos (que cruzam o meio) não forem a maioria — senão é mais seguro
    # assumir coluna única e não arriscar reordenar errado.
    total = len(body)
    is_two_column = (
        _side_is_a_real_column(left, page_height)
        and _side_is_a_real_column(right, page_height)
        and len(ambiguous) < total * 0.4
    )

    if not is_two_column:
        # Fallback: coluna única, ordena por posição vertical (comportamento original)
        ordered = sorted(body, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        return ordered

    # Blocos ambíguos (largura total) são atribuídos à coluna mais próxima pelo centro
    for b in ambiguous:
        center_x = (b["bbox"][0] + b["bbox"][2]) / 2.0
        (left if center_x < mid else right).append(b)

    left.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    right.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

    return left + right
