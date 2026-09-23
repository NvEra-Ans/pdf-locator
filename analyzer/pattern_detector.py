import re
from typing import Dict, Any, List

class PatternDetector:
    """Detecta padrões de números de página e de parágrafo no texto extraído do PDF.

    IMPORTANTE (aprendido com o PDF real do usuário): a ideia original de usar
    uma "zona" de cabeçalho/rodapé por posição na página (topo/rodapé em %)
    NÃO funciona nesse livro — as margens reais são pequenas demais e não tem
    "zona morta" nenhuma entre o título do cabeçalho e o começo do corpo do
    texto. Diagnóstico real mostrou extratos inteiros começando a 1 linha de
    distância do cabeçalho (ex.: extrato 44 na pág. 11), sendo descartados por
    inteiro porque caíam dentro dos 12% do topo.
    A abordagem que funciona é reconhecer cabeçalho/rodapé pelo CONTEÚDO da
    linha, não pela posição:
      - número de página / marcador Parte A-B: só reconhecido quando a linha
        INTEIRA é isso e mais nada (os padrões abaixo são ancorados no início
        E no fim, "^...$") — uma linha real de extrato sempre tem texto extra
        depois do número, então nunca bate por engano nessas expressões.
      - título repetido do livro (cabeçalho de página): reconhecido pelo
        texto exato (comparação, não posição) contra os títulos conhecidos,
        mais um heurístico genérico de "linha inteira em maiúsculas" (títulos
        de cabeçalho são sempre em caixa alta; texto do corpo sempre tem
        palavras em minúscula).
    """

    PAGE_NUMBER_PATTERN = re.compile(r'^\s*(?:pág|pág\.|página|page)?\s*(\d+[A-Za-z]?)\s*$', re.IGNORECASE)

    # Títulos de cabeçalho conhecidos, repetidos em (quase) toda página do
    # livro, alternando entre título da obra e nome do autor (padrão clássico
    # de página par/ímpar). Comparação é feita em maiúsculas, ignorando
    # acentos não é necessário aqui pois o texto já vem com acentuação
    # consistente do PDF.
    KNOWN_HEADER_TITLES = frozenset([
        "CITAS DEL MENSAJE DEL PROFETA",
        "WILLIAM MARRION BRANHAM",
    ])

    # Marcador de "Parte A" / "Parte B" (ex.: livro de citações com um corpo
    # principal numerado 1..1539 e mais duas seções extras ("Parte A", "Parte
    # B") que REAPROVEITAM os mesmos números (1..230) de novo. No PDF, esse
    # marcador aparece como um número de página SOZINHO na linha, seguido de
    # "-A" ou "-B" (ex.: "7-A", "1-B"), sempre no cabeçalho/rodapé da página
    # — nunca é, ele mesmo, o número de um extrato (confirmado no texto real
    # do livro: nenhum extrato de verdade tem esse sufixo colado no próprio
    # número; extratos são sempre dígitos puros).
    PART_PAGE_LABEL_PATTERN = re.compile(r'^\s*(\d{1,4})\s*[\-\–\—]\s*([AB])\s*$')

    # Número do extrato: SEMPRE dígitos puros no início da linha (confirmado
    # no texto real do livro — nenhum extrato genuíno tem letra colada ao
    # número; sufixos de letra só aparecem em marcadores de página, tratados
    # separadamente acima).
    PARAGRAPH_PATTERN = re.compile(r'^\s*(\d{1,4})\s*[\-\–\—\.]?\s*')

    # Número grande formatado ao estilo espanhol/latino, com ponto separando
    # milhares (ex.: "300.000", "1.234.567") — NAO pode ser confundido com
    # início de extrato. Achado com dado real: o extrato 30 continuava na
    # outra coluna com "300.000 de esos en esa reunión...", e "300.000" batia
    # no PARAGRAPH_PATTERN como se fosse o extrato "300" começando ali,
    # cortando o extrato 30 no meio da frase e criando um extrato fantasma
    # "300". Verificado ANTES do PARAGRAPH_PATTERN.
    THOUSANDS_NUMBER_PATTERN = re.compile(r'^\s*\d{1,3}(?:\.\d{3})+\b')

    # Referência estilo "capítulo:versículo" (ex.: "100:872"), usada em
    # citações bíblicas dentro do corpo do texto — não é o mesmo esquema de
    # numeração de extrato do livro (que nunca usa ":"), então não pode virar
    # um novo extrato.
    VERSE_REFERENCE_PATTERN = re.compile(r'^\s*\d{1,4}\s*:\s*\d')

    # Linha de local/data que fecha cada extrato nos livros de citações, ex.:
    # "Jeffersonville, Ind., 12-29-63". Tudo antes da última vírgula é o
    # local (pode ter vírgulas internas, ex. "Jeffersonville, Ind."), e o que
    # vem depois é a data no formato M(M)-D(D)-AA(AA).
    LOCATION_DATE_PATTERN = re.compile(r'^\s*(?P<location>.+?),\s*(?P<date>\d{1,2}-\d{1,2}-\d{2,4})\s*$')

    @classmethod
    def analyze_text_span(cls, text: str, bbox: List[float], page_width: float, page_height: float) -> Dict[str, Any]:
        result = {
            "is_page_number_candidate": False,
            "confidence_page_label": 0.0,
            "detected_label": "",
            "is_header_or_footer": False,
            "is_part_label_candidate": False,
            "detected_part": None,
            "is_paragraph_candidate": False,
            "detected_paragraph_num": "",
            "is_location_date_candidate": False,
            "detected_location": "",
            "detected_date": ""
        }

        if not text:
            return result

        clean_text = text.strip()

        # 1. Marcador de Parte A/B: reconhecido pelo padrão ancorado no início
        # E no fim da linha ("^...$") — uma linha real de extrato sempre tem
        # texto além do número+letra, então nunca bate aqui por engano. Não
        # depende mais de posição na página (ver docstring da classe).
        part_match = cls.PART_PAGE_LABEL_PATTERN.match(clean_text)
        if part_match:
            result["is_part_label_candidate"] = True
            result["detected_part"] = part_match.group(2)
            result["detected_label"] = part_match.group(1)
            result["confidence_page_label"] = 0.95
            result["is_header_or_footer"] = True
            return result

        # 2. Número de página sozinho na linha: mesma lógica, padrão ancorado
        # nas duas pontas, não depende de posição.
        page_match = cls.PAGE_NUMBER_PATTERN.match(clean_text)
        if page_match:
            result["is_page_number_candidate"] = True
            result["detected_label"] = page_match.group(1)
            result["confidence_page_label"] = 0.95
            result["is_header_or_footer"] = True
            return result

        # 3. Início de um extrato numerado (ex.: "44 - ..."), a menos que seja
        # uma referência bíblica "capítulo:versículo" ou um número grande
        # formatado com ponto de milhar (ex.: "300.000").
        if not cls.VERSE_REFERENCE_PATTERN.match(clean_text) and not cls.THOUSANDS_NUMBER_PATTERN.match(clean_text):
            para_match = cls.PARAGRAPH_PATTERN.match(clean_text)
            if para_match:
                result["is_paragraph_candidate"] = True
                result["detected_paragraph_num"] = para_match.group(1)
                return result

        # 4. Linha "Cidade, Estado., DD-MM-AA" que fecha um extrato.
        loc_match = cls.LOCATION_DATE_PATTERN.match(clean_text)
        if loc_match:
            result["is_location_date_candidate"] = True
            result["detected_location"] = loc_match.group("location").strip()
            result["detected_date"] = loc_match.group("date").strip()
            return result

        # 5. Título de cabeçalho repetido do livro: reconhecido pelo texto
        # exato (contra os títulos conhecidos) OU pelo heurístico de "linha
        # inteira em maiúsculas" (títulos de cabeçalho são sempre em caixa
        # alta; texto real do corpo sempre tem alguma palavra em minúscula).
        # Isso substitui a antiga checagem por posição/zona da página, que se
        # mostrou incorreta no PDF real (corpo de extrato caindo dentro da
        # "zona" só por estar perto do topo/rodapé da página).
        has_letters = any(c.isalpha() for c in clean_text)
        # clean_text == clean_text.upper() já garante que não há nenhuma
        # letra minúscula na linha (se houvesse, a comparação falharia).
        is_all_caps = has_letters and clean_text == clean_text.upper()
        if clean_text.upper() in cls.KNOWN_HEADER_TITLES or is_all_caps:
            result["is_header_or_footer"] = True

        return result
