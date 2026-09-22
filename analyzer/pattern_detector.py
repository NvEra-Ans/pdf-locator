import re
from typing import Dict, Any, List

class PatternDetector:
    """Detecta padrões de números de página e de parágrafo no texto extraído do PDF."""

    PAGE_NUMBER_PATTERN = re.compile(r'^\s*(?:pág|pág\.|página|page)?\s*(\d+[A-Za-z]?)\s*$', re.IGNORECASE)
    PARAGRAPH_PATTERN = re.compile(r'^\s*(\d{1,4})\s*[\-\–\—\.]?\s*')

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
            "is_paragraph_candidate": False,
            "detected_paragraph_num": "",
            "is_location_date_candidate": False,
            "detected_location": "",
            "detected_date": ""
        }

        if not text:
            return result

        clean_text = text.strip()

        # Check for page number candidate (usually top or bottom of page)
        is_header_or_footer = False
        if bbox:
            top_y = bbox[1]
            bottom_y = bbox[3]
            if top_y < page_height * 0.12 or bottom_y > page_height * 0.88:
                is_header_or_footer = True

        page_match = cls.PAGE_NUMBER_PATTERN.match(clean_text)
        if page_match and is_header_or_footer:
            result["is_page_number_candidate"] = True
            result["detected_label"] = page_match.group(1)
            result["confidence_page_label"] = 0.95

        # Check for paragraph candidate
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