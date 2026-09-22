import re
from typing import Dict, Any, List

class PatternDetector:
    """Detecta padrões de números de página e de parágrafo no texto extraído do PDF."""

    PAGE_NUMBER_PATTERN = re.compile(r'^\s*(?:pág|pág\.|página|page)?\s*(\d+[A-Za-z]?)\s*$', re.IGNORECASE)

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

        # Zona de cabeçalho/rodapé da página (topo 12% / rodapé 12%).
        is_header_or_footer = False
        if bbox:
            top_y = bbox[1]
            bottom_y = bbox[3]
            if top_y < page_height * 0.12 or bottom_y > page_height * 0.88:
                is_header_or_footer = True
        result["is_header_or_footer"] = is_header_or_footer

        # Marcador de Parte A/B — só conta se estiver no cabeçalho/rodapé
        # (mesma zona onde os números de página normais aparecem).
        if is_header_or_footer:
            part_match = cls.PART_PAGE_LABEL_PATTERN.match(clean_text)
            if part_match:
                result["is_part_label_candidate"] = True
                result["detected_part"] = part_match.group(2)
                result["detected_label"] = part_match.group(1)
                result["confidence_page_label"] = 0.95

        page_match = cls.PAGE_NUMBER_PATTERN.match(clean_text)
        if page_match and is_header_or_footer and not result["is_part_label_candidate"]:
            result["is_page_number_candidate"] = True
            result["detected_label"] = page_match.group(1)
            result["confidence_page_label"] = 0.95

        # Check for paragraph candidate — mas NUNCA no cabeçalho/rodapé
        # (ali só existe número de página avulso ou o cabeçalho repetido do
        # livro, nunca o início de um extrato de verdade) nem se for uma
        # referência "cap:versículo".
        if not is_header_or_footer and not cls.VERSE_REFERENCE_PATTERN.match(clean_text):
            para_match = cls.PARAGRAPH_PATTERN.match(clean_text)
            if para_match:
                result["is_paragraph_candidate"] = True
                result["detected_paragraph_num"] = para_match.group(1)

        # Check for a "Cidade, Estado., DD-MM-AA" attribution line (fecha um
        # extrato). Uma linha que já foi reconhecida como início de novo
        # parágrafo/extrato não pode ser também uma linha de atribuição.
        if not result["is_paragraph_candidate"]:
            loc_match = cls.LOCATION_DATE_PATTERN.match(clean_text)
            if loc_match:
                result["is_location_date_candidate"] = True
                result["detected_location"] = loc_match.group("location").strip()
                result["detected_date"] = loc_match.group("date").strip()

        return result
