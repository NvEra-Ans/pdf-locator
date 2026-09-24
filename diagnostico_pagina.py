"""
Script de diagnostico - roda DENTRO da pasta do repositorio (pdf_locator),
porque ele importa direto o codigo real de producao (analyzer/layout.py e
analyzer/pattern_detector.py) -- nao reimplementa nada, entao mostra
exatamente o que o indexador de verdade faz com essa pagina.

O que faz: abre o SEU PDF real na pagina que voce indicar (numero como
aparece no visualizador, 1-based) e mostra, em 3 etapas:

  1. Os blocos BRUTOS que o PyMuPDF extrai da pagina (ordem nativa),
     com bbox (x0,y0,x1,y1) e o comeco do texto de cada um.
  2. Como a funcao real order_blocks_reading_order() reordena esses
     blocos (cabecalho -> corpo coluna esquerda -> corpo coluna
     direita -> rodape), incluindo se a pagina foi tratada como
     2 colunas ou como fallback (coluna unica).
  3. Como cada LINHA (dentro dos blocos ja reordenados) e classificada
     pela funcao real PatternDetector.analyze_text_span() -- isso
     mostra se alguma linha do paragrafo que esta sumindo esta sendo
     classificada, por engano, como cabecalho/rodape/numero de pagina
     (o que faria ela ser descartada com "continue" no indexador real).

Como usar (PowerShell, DENTRO da pasta pdf_locator, onde estao as pastas
analyzer/ e app/):

  python diagnostico_pagina.py "C:\\caminho\\para\\o_livro.pdf" 202

  (202 = numero da pagina COMO APARECE NO VISUALIZADOR, comecando em 1;
  o script converte sozinho para o indice interno 0-based do PyMuPDF)

Gera "diagnostico_pagina_saida.txt" na pasta atual. Me manda esse arquivo.
"""
import sys
import os

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyzer.layout import order_blocks_reading_order
from analyzer.pattern_detector import PatternDetector


def block_text_preview(b, max_len=90):
    text = ""
    for line in b.get("lines", []):
        text += "".join(s.get("text", "") for s in line.get("spans", [])) + " "
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def main():
    if len(sys.argv) < 3:
        print("Uso: python diagnostico_pagina.py CAMINHO_DO_PDF NUMERO_DA_PAGINA_NO_VISUALIZADOR")
        print('Ex.:  python diagnostico_pagina.py "C:\\livro.pdf" 202')
        sys.exit(1)

    pdf_path = sys.argv[1]
    viewer_page_num = int(sys.argv[2])
    page_idx = viewer_page_num - 1  # 0-based, igual ao PyMuPDF/indexador real

    if not os.path.exists(pdf_path):
        print(f"Arquivo nao encontrado: {pdf_path}")
        sys.exit(1)

    doc = fitz.open(pdf_path)
    if page_idx < 0 or page_idx >= len(doc):
        print(f"Pagina {viewer_page_num} fora do intervalo (o PDF tem {len(doc)} paginas).")
        sys.exit(1)

    page = doc[page_idx]
    width, height = page.rect.width, page.rect.height
    page_dict = page.get_text("dict")
    raw_blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]

    out = []
    out.append(f"PDF: {pdf_path}")
    out.append(f"Pagina do visualizador: {viewer_page_num}  (pdf_page_index={page_idx}, 0-based)")
    out.append(f"page_width={width:.1f}  page_height={height:.1f}")
    out.append("")

    out.append("=" * 90)
    out.append(f"ETAPA 1 - Blocos BRUTOS (ordem nativa do PyMuPDF) -- total: {len(raw_blocks)}")
    out.append("=" * 90)
    for i, b in enumerate(raw_blocks):
        bbox = b.get("bbox", [0, 0, 0, 0])
        out.append(
            f"  [{i:3d}] bbox=(x0={bbox[0]:7.1f}, y0={bbox[1]:7.1f}, x1={bbox[2]:7.1f}, y1={bbox[3]:7.1f})  "
            f"n_lines={len(b.get('lines', [])):3d}  texto={block_text_preview(b)!r}"
        )
    out.append("")

    # Reproduz a classificacao de zona/coluna feita dentro de
    # order_blocks_reading_order/_order_body_by_columns, so para
    # relatorio (a decisao real de verdade e tomada pela funcao
    # importada abaixo, isto aqui e so pra mostrar o "porque").
    header_zone, footer_zone = 0.12, 0.88
    header_ids, footer_ids, body_ids = [], [], []
    id_of_block = {id(b): i for i, b in enumerate(raw_blocks)}
    for b in raw_blocks:
        if not block_text_preview(b, max_len=10**9):
            continue
        bbox = b.get("bbox", [0, 0, 0, 0])
        top_y, bottom_y = bbox[1], bbox[3]
        if bottom_y <= height * header_zone:
            header_ids.append(id_of_block[id(b)])
        elif top_y >= height * footer_zone:
            footer_ids.append(id_of_block[id(b)])
        else:
            body_ids.append(id_of_block[id(b)])

    mid = width / 2.0
    tolerance = width * 0.06
    left_ids, right_ids, ambig_ids = [], [], []
    for i in body_ids:
        b = raw_blocks[i]
        x0, x1 = b["bbox"][0], b["bbox"][2]
        if x1 <= mid + tolerance:
            left_ids.append(i)
        elif x0 >= mid - tolerance:
            right_ids.append(i)
        else:
            ambig_ids.append(i)

    total_body = len(body_ids)
    is_two_column = len(left_ids) >= 2 and len(right_ids) >= 2 and len(ambig_ids) < total_body * 0.4

    out.append("=" * 90)
    out.append("ETAPA 1b - Classificacao de zona/coluna (so para relatorio, mesma formula do layout.py)")
    out.append("=" * 90)
    out.append(f"  header_zone (blocos que terminam ate {header_zone*100:.0f}% da altura): indices {header_ids}")
    out.append(f"  footer_zone (blocos que comecam a partir de {footer_zone*100:.0f}% da altura): indices {footer_ids}")
    out.append(f"  body (resto): indices {body_ids}")
    out.append(f"    -> dentro do body: esquerda={left_ids}  direita={right_ids}  ambiguo(cruza meio)={ambig_ids}")
    out.append(f"    -> is_two_column = {is_two_column}  (left>=2: {len(left_ids)>=2}, right>=2: {len(right_ids)>=2}, ambig<40%: {len(ambig_ids)} < {total_body*0.4:.1f})")
    if not is_two_column:
        out.append("    !!! ATENCAO: pagina NAO foi tratada como 2 colunas -- caiu no fallback de coluna unica (ordena so por Y).")
    out.append("")

    out.append("=" * 90)
    out.append("ETAPA 2 - Ordem de leitura REAL (order_blocks_reading_order, funcao de producao importada)")
    out.append("=" * 90)
    ordered = order_blocks_reading_order(raw_blocks, width, height)
    out.append(f"Total de blocos depois de reordenar: {len(ordered)} (deveria ser igual ou menor que os {len(raw_blocks)} brutos, nunca maior)")
    for i, b in enumerate(ordered):
        bbox = b.get("bbox", [0, 0, 0, 0])
        orig_idx = id_of_block.get(id(b), "?")
        out.append(
            f"  ordem[{i:3d}] (era bruto[{orig_idx}])  bbox=(x0={bbox[0]:7.1f}, y0={bbox[1]:7.1f}, x1={bbox[2]:7.1f}, y1={bbox[3]:7.1f})  "
            f"texto={block_text_preview(b)!r}"
        )
    out.append("")

    # Conferencia: algum bloco bruto sumiu na reordenacao?
    raw_ids_set = set(id(b) for b in raw_blocks)
    ordered_ids_set = set(id(b) for b in ordered)
    missing = raw_ids_set - ordered_ids_set
    if missing:
        out.append("!!! ATENCAO: os seguintes blocos BRUTOS sumiram na reordenacao (nao aparecem em 'ordered'):")
        for i, b in enumerate(raw_blocks):
            if id(b) in missing:
                out.append(f"    bruto[{i}] texto={block_text_preview(b)!r}")
        out.append("")
    else:
        out.append("OK: nenhum bloco bruto sumiu na reordenacao -- todos os blocos brutos aparecem em 'ordered'.")
        out.append("")

    out.append("=" * 90)
    out.append("ETAPA 3 - Classificacao de cada LINHA pelo PatternDetector real (o que o indexador realmente ve)")
    out.append("=" * 90)
    for i, b in enumerate(ordered):
        bbox = b.get("bbox")
        for line in b.get("lines", []):
            line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not line_text:
                continue
            res = PatternDetector.analyze_text_span(line_text, bbox, width, height)
            if res["is_part_label_candidate"]:
                tag = "PART_LABEL (descartada, so atualiza secao)"
            elif res["is_page_number_candidate"]:
                tag = "PAGE_NUMBER (descartada)"
            elif res["is_paragraph_candidate"]:
                tag = f"NOVO_EXTRATO num={res['detected_paragraph_num']}"
            elif res["is_location_date_candidate"]:
                tag = f"LOCATION_DATE local={res['detected_location']!r} data={res['detected_date']!r}"
            elif res["is_header_or_footer"]:
                tag = "HEADER_OU_FOOTER (DESCARTADA -- nao vira chunk)"
            else:
                tag = "corpo normal (vira chunk)"
            out.append(f"  bloco_ordem[{i:3d}]  [{tag:55s}] | {line_text!r}")
    out.append("")

    conn_out = "\n".join(out)
    out_path = "diagnostico_pagina_saida.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(conn_out)

    print(f"Pronto! Arquivo gerado: {out_path}")
    print("Manda esse arquivo de volta.")


if __name__ == "__main__":
    main()
