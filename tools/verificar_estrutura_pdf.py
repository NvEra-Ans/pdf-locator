#!/usr/bin/env python3
"""
Verificador de estrutura de PDF -- roda ANTES de importar um livro novo no
app de verdade, pra apontar se ele foge dos formatos já suportados.

NÃO é um substituto do indexador real -- é uma inspeção separada, mais
simples, que reaproveita as mesmas expressões regulares e a mesma lógica de
detecção usadas em produção (analyzer/pattern_detector.py e
app/indexing/paragraph_indexer.py), pra reduzir a chance de só descobrir um
formato novo depois de reimportar e testar a busca de verdade -- que foi
como os bugs de v2.6.2, v2.6.3 e v2.6.4 foram encontrados.

O QUE ESTE SCRIPT VERIFICA (e o que NÃO verifica):
- [verificado] Conta quantas linhas começando com dígito batem nos formatos
  de parágrafo já suportados (3 formatos do Tipo A, ou o formato do Tipo B),
  e agrupa as que NÃO batem por "assinatura" (os primeiros caracteres depois
  do número), pra apontar se existe um 4º formato ainda não visto.
- [verificado] Pro perfil Tipo A, reaproveita a MESMA função de resolução de
  rótulo de página do indexador real (ParagraphIndexer._resolve_page_labels),
  então os números de confiança aqui são os mesmos que o app usaria.
- [verificado] Lista linhas com fonte bem maior que o corpo do texto
  (>=1,12x, mesmo limiar usado pro filtro de bloco decorativo) — útil pra
  conferir visualmente se são títulos/capitulares esperados ou algo
  inesperado.
- NÃO analisa o livro inteiro linha a linha com garantia de 100% -- é uma
  amostragem estrutural. Um formato raro, usado só 1 ou 2 vezes no livro
  inteiro, pode não aparecer com destaque no relatório.
- NÃO decide sozinho se o PDF está "pronto" -- reporta sinais objetivos
  (contagens, exemplos, números de página) pra você avaliar antes de
  reimportar. Achar 0 problema aqui não é garantia de que a busca vai
  funcionar perfeitamente -- só reduz a chance de repetir um dos bugs já
  vistos.

Uso:
    python3 tools/verificar_estrutura_pdf.py caminho/do/livro.pdf --tipo a
    python3 tools/verificar_estrutura_pdf.py caminho/do/livro.pdf --tipo b

--tipo a = Livro Estruturado por Parágrafos (perfil PARAGRAPH_BOOK)
--tipo b = Livro de Citações/Extratos (perfil CITATIONS_BOOK)
Se --tipo não for passado, assume "a" (foi o perfil de todos os bugs de
formato de parágrafo encontrados até agora).
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from analyzer.pattern_detector import PatternDetector
from app.indexing.paragraph_indexer import ParagraphIndexer

# Depois dos N dígitos iniciais de uma linha, pega até 4 caracteres seguintes
# como "assinatura" do separador usado (ex.: ". \t" vira ". <TAB>", "  - "
# vira " - "). Serve só pra agrupar linhas parecidas -- não é usado em
# nenhuma lógica de indexação de verdade.
_LEADING_DIGITS = re.compile(r'^\s*(\d{1,4})(.{0,4})')


def _signature_after_digits(clean_text: str) -> str:
    m = _LEADING_DIGITS.match(clean_text)
    if not m:
        return ""
    tail = m.group(2)
    return tail.replace("\t", "<TAB>")


def _iter_lines(doc):
    """Gera (page_idx, line, clean_text, bbox) para cada linha não-vazia do
    documento inteiro -- mesma estrutura bruta (page.get_text('dict')) usada
    pelo indexador real."""
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(s.get("text", "") for s in spans)
                clean = text.strip()
                if not clean:
                    continue
                yield page_idx, line, clean, line.get("bbox")


def analisar(pdf_path: str, tipo: str):
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    print(f"Arquivo: {pdf_path}")
    print(f"Páginas (PDF): {num_pages}")
    print(f"Perfil analisado: Tipo {tipo.upper()}")
    print("-" * 70)

    active_pattern = (
        PatternDetector.PARAGRAPH_PATTERN_TYPE_A if tipo == "a" else PatternDetector.PARAGRAPH_PATTERN
    )

    # ------------------------------------------------------------ Tipo A:
    # reaproveita a resolução de página de verdade do indexador (mesma
    # lógica de âncoras + reconciliação usada em produção).
    body_font_size = None
    if tipo == "a":
        # _resolve_page_labels é um método de instância, mas não toca em
        # banco de dados (db_conn) nenhum -- só lê o PDF. Instanciamos com
        # db_conn=None só pra poder chamar a mesma função usada em produção.
        indexer = ParagraphIndexer(db_conn=None)
        final_labels, final_confs, _raw_cache, body_font_size = indexer._resolve_page_labels(doc)
        confident = sum(1 for c in final_confs if c and c > 0.90)
        inferred = num_pages - confident
        print(f"Páginas com número impresso reconhecido com confiança: {confident}/{num_pages}")
        print(f"Páginas com rótulo INFERIDO (sem número impresso confiável): {inferred}/{num_pages}")
        if inferred:
            inferred_idxs = [i for i, c in enumerate(final_confs) if not (c and c > 0.90)]
            preview = ", ".join(str(i) for i in inferred_idxs[:20])
            more = f" (+{len(inferred_idxs) - 20} outras)" if len(inferred_idxs) > 20 else ""
            print(f"  Índices (0-based) das páginas inferidas: {preview}{more}")
        if body_font_size:
            print(f"Tamanho de fonte do corpo do texto (mediana ponderada): {body_font_size:.2f}pt")
        print("-" * 70)

    # ------------------------------------------------------- Formatos de
    # número de parágrafo/extrato: reconhecidos vs desconhecidos.
    recognized = 0
    unrecognized_examples = defaultdict(list)  # assinatura -> [(page_idx, texto), ...]
    dropcap_like = []  # linhas de 1 letra maiúscula, possível capitular
    oversized_lines = []  # linhas com fonte >=1.12x corpo (possível bloco decorativo)

    for page_idx, line, clean, bbox in _iter_lines(doc):
        # Candidatas a capitular / bloco decorativo -- só faz sentido no
        # Tipo A, que é onde esse padrão apareceu até agora (sermões com
        # capitular + título/autor/data). Mesmo limiar do indexador real.
        if body_font_size:
            line_size = ParagraphIndexer._line_font_size(line)
            if line_size and line_size >= 1.12 * body_font_size:
                if len(clean) == 1 and clean.isalpha():
                    dropcap_like.append((page_idx, clean))
                elif len(clean) >= 2:
                    oversized_lines.append((page_idx, clean, round(line_size, 1)))

        if not clean[0].isdigit():
            continue
        # Mesmas exclusões que o detector real usa antes de checar padrão de
        # parágrafo (referência bíblica "cap:versículo" e número de milhar
        # "300.000") -- senão essas linhas aparecem como "não reconhecidas"
        # por engano, quando na verdade são corretamente ignoradas.
        if PatternDetector.VERSE_REFERENCE_PATTERN.match(clean) or PatternDetector.THOUSANDS_NUMBER_PATTERN.match(clean):
            continue
        if active_pattern.match(clean):
            recognized += 1
            continue
        sig = _signature_after_digits(clean)
        if len(unrecognized_examples[sig]) < 3:
            unrecognized_examples[sig].append((page_idx, clean[:80]))

    print(f"Linhas reconhecidas como início de parágrafo/extrato (formatos já suportados): {recognized}")
    print("-" * 70)

    total_unrecognized = sum(len(v) for v in unrecognized_examples.values())
    if not unrecognized_examples:
        print("Nenhuma linha começando com dígito ficou sem reconhecer -- não achei sinal de formato novo.")
    else:
        print(f"Linhas começando com dígito que NÃO bateram em nenhum formato conhecido (amostra):")
        # Ordena por frequência de assinatura (mais repetida primeiro) --
        # assinatura que se repete muito é mais provável de ser um formato
        # de verdade (não ruído/coincidência isolada).
        sig_counts = Counter()
        for page_idx, line, clean, bbox in _iter_lines(doc):
            if not clean[0:1].isdigit():
                continue
            if PatternDetector.VERSE_REFERENCE_PATTERN.match(clean) or PatternDetector.THOUSANDS_NUMBER_PATTERN.match(clean):
                continue
            if active_pattern.match(clean):
                continue
            sig_counts[_signature_after_digits(clean)] += 1

        for sig, count in sig_counts.most_common():
            examples = unrecognized_examples.get(sig, [])
            marker = "  [ATENÇÃO -- possível formato novo, repete bastante]" if count >= 3 else ""
            print(f"  Assinatura {sig!r} -- {count} ocorrência(s){marker}")
            for page_idx, text in examples:
                print(f"      página (índice 0) {page_idx}: {text!r}")
        print(
            f"\nTotal de linhas não reconhecidas: {total_unrecognized}. "
            "Isso NÃO significa que todas são parágrafos de verdade -- pode "
            "incluir números soltos em citações, versículos, listas etc. "
            "Confira as assinaturas marcadas com [ATENÇÃO] primeiro."
        )
    print("-" * 70)

    if dropcap_like:
        print(f"Letras capitulares em linha própria detectadas: {len(dropcap_like)} (isso já é tratado pelo indexador -- só informativo)")
    if oversized_lines:
        print(f"Linhas com fonte destacada (>=1,12x o corpo) que podem ser blocos decorativos (título/autor/data): {len(oversized_lines)}")
        for page_idx, text, size in oversized_lines[:15]:
            print(f"    página (índice 0) {page_idx} [{size}pt]: {text[:80]!r}")
        if len(oversized_lines) > 15:
            print(f"    ... (+{len(oversized_lines) - 15} outras)")

    doc.close()


def main():
    parser = argparse.ArgumentParser(description="Verifica a estrutura de um PDF antes de importar no app.")
    parser.add_argument("pdf_path", help="Caminho do arquivo PDF a analisar")
    parser.add_argument("--tipo", choices=["a", "b"], default="a", help="Perfil do livro (a = Parágrafos, b = Citações/Extratos). Padrão: a")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Arquivo não encontrado: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    analisar(args.pdf_path, args.tipo)


if __name__ == "__main__":
    main()
