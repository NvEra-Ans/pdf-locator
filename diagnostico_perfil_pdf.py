"""
Script de diagnostico EXPLORATORIO - roda DENTRO da pasta do
repositorio (pdf_locator), porque importa direto o PatternDetector real
de producao (nao reimplementa nada).

Diferente dos outros diagnosticos desta sessao (que ja sabiam qual
pagina/extrato olhar), este e pra um PDF NOVO que a gente ainda nao
conhece a estrutura -- ele amostra algumas paginas espalhadas pelo
documento e mostra, pra cada uma: dimensoes da pagina, os blocos brutos
(bbox + inicio do texto) e como cada linha seria classificada pelo
PatternDetector de producao (numero de pagina, inicio de paragrafo,
local/data, cabecalho/rodape, ou "nao reconhecido por nenhum padrao
atual"). Isso ajuda a decidir se o PDF se encaixa no perfil Tipo A, no
Tipo B, ou se precisa de ajuste/perfil novo -- sem eu ter que adivinhar
so pelo texto extraido.

Como usar (PowerShell, DENTRO da pasta pdf_locator):

  python diagnostico_perfil_pdf.py "C:\\caminho\\para\\o_livro.pdf"

Por padrao amostra 6 paginas espalhadas pelo documento (inicio, meio,
fim). Pra escolher paginas especificas (numero do visualizador, 1-based):

  python diagnostico_perfil_pdf.py "C:\\caminho\\para\\o_livro.pdf" 5 27 96 150

Gera "diagnostico_perfil_pdf_saida.txt" na pasta atual. Me manda esse
arquivo.
"""
import sys
import os

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyzer.pattern_detector import PatternDetector


def block_text_preview(b, max_len=90):
    text = ""
    for line in b.get("lines", []):
        text += "".join(s.get("text", "") for s in line.get("spans", [])) + " "
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def pick_sample_pages(total_pages, n=6):
    if total_pages <= n:
        return list(range(total_pages))
    # espalha as amostras do inicio ao fim, evitando so a capa (pula as
    # primeiras ~2% do documento, que costuma ser capa/rosto)
    start = max(1, int(total_pages * 0.02))
    step = max(1, (total_pages - start) // n)
    pages = list(range(start, total_pages, step))[:n]
    return pages


def main():
    if len(sys.argv) < 2:
        print("Uso: python diagnostico_perfil_pdf.py CAMINHO_DO_PDF [pagina1 pagina2 ...]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Arquivo nao encontrado: {pdf_path}")
        sys.exit(1)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if len(sys.argv) > 2:
        viewer_pages = [int(a) for a in sys.argv[2:]]
        page_indices = [p - 1 for p in viewer_pages]
    else:
        page_indices = pick_sample_pages(total_pages, n=6)

    out = []
    out.append(f"PDF: {pdf_path}")
    out.append(f"Total de paginas: {total_pages}")
    out.append(f"Paginas amostradas (0-based): {page_indices}  "
               f"(visualizador: {[i+1 for i in page_indices]})")
    out.append("")

    for page_idx in page_indices:
        if page_idx < 0 or page_idx >= total_pages:
            out.append(f"[pagina {page_idx+1} fora do intervalo, pulando]")
            continue

        page = doc[page_idx]
        width, height = page.rect.width, page.rect.height
        page_dict = page.get_text("dict")
        raw_blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]

        out.append("#" * 90)
        out.append(f"PAGINA (visualizador) {page_idx+1}  |  pdf_page_index={page_idx}  |  "
                   f"largura={width:.1f}  altura={height:.1f}  |  total_blocos={len(raw_blocks)}")
        out.append("#" * 90)

        for i, b in enumerate(raw_blocks):
            bbox = b.get("bbox", [0, 0, 0, 0])
            out.append(
                f"  bloco[{i:3d}] bbox=(x0={bbox[0]:6.1f}, y0={bbox[1]:6.1f}, "
                f"x1={bbox[2]:6.1f}, y1={bbox[3]:6.1f})  n_lines={len(b.get('lines', [])):3d}  "
                f"texto={block_text_preview(b)!r}"
            )

        out.append("")
        out.append("  -- classificacao linha a linha (PatternDetector real) --")
        for b in raw_blocks:
            bbox = b.get("bbox")
            for line in b.get("lines", []):
                line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                if not line_text:
                    continue
                res = PatternDetector.analyze_text_span(line_text, bbox, width, height)
                if res["is_part_label_candidate"]:
                    tag = f"PART_LABEL num={res['detected_label']} parte={res['detected_part']}"
                elif res["is_page_number_candidate"]:
                    tag = f"PAGE_NUMBER '{res['detected_label']}'"
                elif res["is_paragraph_candidate"]:
                    tag = f"NOVO_PARAGRAFO/EXTRATO num={res['detected_paragraph_num']}"
                elif res["is_location_date_candidate"]:
                    tag = f"LOCATION_DATE local={res['detected_location']!r} data={res['detected_date']!r}"
                elif res["is_header_or_footer"]:
                    tag = "HEADER_OU_FOOTER"
                else:
                    tag = "nao reconhecido (corpo normal)"
                out.append(f"    [{tag:50s}] | {line_text!r}")
        out.append("")

    out_path = "diagnostico_perfil_pdf_saida.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print(f"Pronto! Arquivo gerado: {out_path}")
    print("Manda esse arquivo de volta.")


if __name__ == "__main__":
    main()
