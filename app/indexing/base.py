from abc import ABC, abstractmethod
import unicodedata
import re

class BaseIndexer(ABC):
    """Classe Base abstrata para todos os indexadores de perfil de documento."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Aplica normalização Unicode, remoção de acentos e case folding."""
        if not text:
            return ""
        text = text.lower()
        # Remove acentuação
        nfkd_form = unicodedata.normalize('NFKD', text)
        text = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        # Normaliza espaçamentos e hífens
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @abstractmethod
    def index_document(self, doc_id: int, pdf_path: str) -> bool:
        pass