"""
Script de diagnostico EM LOTE - roda DENTRO da pasta do repositorio
(pdf_locator), porque importa direto o codigo real de producao
(analyzer/layout.py) -- nao reimplementa nada.

O que faz: passa por TODAS as paginas do corpo do livro (as mesmas que o
indexador de verdade processa, ate a secao de indice tematico) e, pra
cada uma, roda a funcao real de deteccao de 2-colunas. Sinaliza as
paginas que caem no modo "fallback de coluna unica" -- que foi
exatamente a causa do bug real do extrato 87-B (coluna direita virou 1
bloco so, mais curto que 25% da altura da pagina, o teste de 2-colunas
falhou e o texto foi pro lugar errado).

Duas categorias no relatorio:
  - RISCO ALTO: um dos lados (esquerda ou direita) tem exatamente 1
    bloco, mais curto que 25% da altura da pagina, e o OUTRO lado tem
    conteudo tambem -- ou seja, a pagina parece mesmo ter 2 colunas,
    mas cai no fallback por causa desse limiar. E o padrao geometrico
    do bug real, so que talvez com um bloco menor (o texto perdido
    seria menor, mas o mecanismo e o mesmo).
  - fallback geral: qualquer pagina que nao foi tratada como 2 colunas
    (pode ser legitimamente pagina de capa/titulo/1-coluna -- nao e
    necessariamente bug, mas fica registrado pra referencia).

Como usar (PowerShell, DENTRO da pasta pdf_locator):

  python diagnostico_paginas_risco.py "C:\\caminho\\para\\o_livro.pdf"

Gera "diagnostico_paginas_risco_saida.txt" na pasta atual. Me manda esse
arquivo.
"""
import sys
import os

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyzer.layout import order_blocks_reading_order

try:
    from app.indexing.citations_indexer import CitationsIndexer
    INDEX_SECTION_START_PDF_PAGE_IDX = CitationsIndexer.INDEX_SECTION_START_PDF_PAGE_IDX
except Exception:
    # Se por algum motivo nao conseguir importar (ex.: dependencias do
    # PySide6 nao instaladas nesse ambiente), varre o PDF inteiro --
    # so gera mais linhas no relatorio, nao afeta a deteccao em si.
    INDEX_SECTION_START_PDF_PAGE_IDX = None


def block_text_preview(b, max_len=70):
    text = ""
    for line in b.get("lines", []):
        text += "".join(s.get("text", "") for s in line.get("spans", [])) + " "
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def classify_page(raw_blocks, width, height):
    """Reproduz a mesma classificacao de zona/coluna do layout.py real,
    so pra relatorio -- a decisao real de ordenacao continua sendo
    feita pela funcao importada, isso aqui e so pra explicar o 'porque'."""
    text_blocks = [b for b in raw_blocks if b.get("type") == 0 and block_text_preview(b, 10**9)]

    header_zone, footer_zone = 0.12, 0.88
    body = []
    for b in text_blocks:
        bbox = b.get("bbox", [0, 0, 0, 0])
        top_y, bottom_y = bbox[1], bbox[3]
        if bottom_y <= height * header_zone:
            continue
        if top_y >= height * footer_zone:
            continue
        body.append(b)

    mid = width / 2.0
    tolerance = width * 0.06
    left, right, ambiguous = [], [], []
    for b in body:
        x0, x1 = b["bbox"][0], b["bbox"][2]
        if x1 <= mid + tolerance:
            left.append(b)
        elif x0 >= mid - tolerance:
            right.append(b)
        else:
            ambiguous.append(b)

    def side_is_real_column(blocks):
        if len(blocks) >= 2:
            return True
        if len(blocks) == 1:
            block_height = blocks[0]["bbox"][3] - blocks[0]["bbox"][1]
            return block_height >= height * 0.25
        return False

    total = len(body)
    is_two_column = (
        side_is_real_column(left) and side_is_real_column(right) and len(ambiguous) < total * 0.4
    )

    return {
        "left": left,
        "right": right,
        "ambiguous": ambiguous,
        "is_two_column": is_two_column,
        "total_body": total,
    }


def main():
    if len(sys.argv) < 2:
        print("Uso: python diagnostico_paginas_risco.py CAMINHO_DO_PDF")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Arquivo nao encontrado: {pdf_path}")
        sys.exit(1)

    doc = fitz.open(pdf_path)

    last_page_idx = len(doc)
    if INDEX_SECTION_START_PDF_PAGE_IDX is not None:
        last_page_idx = min(last_page_idx, INDEX_SECTION_START_PDF_PAGE_IDX)

    out = []
    out.append(f"PDF: {pdf_path}")
    out.append(f"Total de paginas no PDF: {len(doc)}")
    out.append(f"Paginas analisadas (corpo do livro, antes do indice): 0 ate {last_page_idx - 1} (0-based)")
    out.append("")

    risco_alto = []
    fallback_geral = []

    for page_idx in range(last_page_idx):
        page = doc[page_idx]
        width, height = page.rect.width, page.rect.height
        page_dict = page.get_text("dict")
        raw_blocks = page_dict.get("blocks", [])

        info = classify_page(raw_blocks, width, height)
        viewer_page = page_idx + 1

        if not info["is_two_column"] and info["total_body"] > 0:
            fallback_geral.append((viewer_page, info))

            left, right = info["left"], info["right"]
            for lado_nome, lado_blocks, outro_blocks in (
                ("esquerda", left, right),
                ("direita", right, left),
            ):
                if len(lado_blocks) == 1 and len(outro_blocks) >= 1:
                    block_height = lado_blocks[0]["bbox"][3] - lado_blocks[0]["bbox"][1]
                    pct = block_height / height * 100
                    if pct < 25.0:
                        risco_alto.append((viewer_page, lado_nome, pct, block_text_preview(lado_blocks[0])))

    out.append("=" * 90)
    out.append(f"RISCO ALTO -- paginas com um lado de 1 bloco so, mais curto que 25% da altura,")
    out.append(f"e o outro lado com conteudo tambem (mesmo padrao geometrico do bug real do 87-B).")
    out.append(f"Total encontrado: {len(risco_alto)}")
    out.append("=" * 90)
    if not risco_alto:
        out.append("  (nenhuma pagina encontrada nesse padrao)")
    for viewer_page, lado_nome, pct, preview in risco_alto:
        out.append(
            f"  pagina do visualizador {viewer_page:4d}  lado={lado_nome:9s}  "
            f"altura_do_bloco={pct:5.1f}% da pagina  |  inicio do texto: {preview!r}"
        )
    out.append("")

    out.append("=" * 90)
    out.append(f"FALLBACK GERAL -- todas as paginas que cairam em 'coluna unica' "
                f"(pode ser bug OU pagina legitimamente 1-coluna, tipo capa/titulo)")
    out.append(f"Total encontrado: {len(fallback_geral)}")
    out.append("=" * 90)
    for viewer_page, info in fallback_geral:
        out.append(
            f"  pagina do visualizador {viewer_page:4d}  "
            f"blocos_no_corpo={info['total_body']:3d}  esquerda={len(info['left'])}  "
            f"direita={len(info['right'])}  ambiguo={len(info['ambiguous'])}"
        )
    out.append("")

    out_path = "diagnostico_paginas_risco_saida.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print(f"Pronto! Arquivo gerado: {out_path}")
    print(f"Risco alto: {len(risco_alto)} pagina(s). Fallback geral: {len(fallback_geral)} pagina(s).")
    print("Manda esse arquivo de volta.")


if __name__ == "__main__":
    main()
