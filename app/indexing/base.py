from abc import ABC, abstractmethod
import unicodedata
import re

class BaseIndexer(ABC):
    """Classe Base abstrata para todos os indexadores de perfil de documento."""

    @staticmethod
    def join_text_parts(parts) -> str:
        """Junta as linhas acumuladas de um parágrafo/extrato num texto só.

        BUG real reportado pelo usuário (print de tela): quando o PDF
        quebra uma palavra no fim da linha por causa da margem (hifenização
        de justificação, ex.: "es-" numa linha e "trechó" na linha
        seguinte, formando "estrechó"), o código antigo simplesmente unia
        TODAS as linhas com espaço (" ".join(...)), produzindo "es-
        trechó" -- com hífen E espaço sobrando -- em vez de reconstituir a
        palavra original "estrechó".

        Corrigido: quando uma linha termina em hífen simples ("-", não
        "--" nem travessão "–"/"—") e a letra antes dele e a letra que
        começa a próxima linha são ambas minúsculas (indício forte de
        quebra de PALAVRA, não de um hífen "de verdade" como um intervalo
        de datas "1975-1976" ou uma enumeração), o hífen é removido e as
        duas linhas são coladas sem espaço. Nos outros casos (hífen
        seguido de maiúscula/dígito, ou não é hífen simples), o
        comportamento antigo é mantido -- junta com espaço normalmente.
        """
        result = ""
        for part in parts:
            if not part:
                continue
            if (
                result.endswith("-")
                and not result.endswith("--")
                and len(result) >= 2
                and result[-2].isalpha() and result[-2].islower()
                and part[:1].isalpha() and part[:1].islower()
            ):
                result = result[:-1] + part
            elif result:
                result += " " + part
            else:
                result = part
        return result.strip()

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