from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

class ProfileType(Enum):
    PARAGRAPH_BOOK = "PARAGRAPH_BOOK"  # Suporta Página, Parágrafo e Texto (Ex: Livro A)
    CITATIONS_BOOK = "CITATIONS_BOOK"  # Suporta Página, Extrato e Texto (Ex: Livro B)

@dataclass
class DocumentIndexProfile:
    profile_type: ProfileType
    supports_page_search: bool = True
    supports_paragraph_search: bool = False
    supports_entry_search: bool = False
    supports_text_search: bool = True
    supports_metadata_search: bool = False

    @staticmethod
    def get_profile(profile_type: ProfileType) -> 'DocumentIndexProfile':
        if profile_type == ProfileType.PARAGRAPH_BOOK:
            return DocumentIndexProfile(
                profile_type=ProfileType.PARAGRAPH_BOOK,
                supports_page_search=True,
                supports_paragraph_search=True,
                supports_entry_search=False,
                supports_text_search=True,
                supports_metadata_search=False
            )
        elif profile_type == ProfileType.CITATIONS_BOOK:
            return DocumentIndexProfile(
                profile_type=ProfileType.CITATIONS_BOOK,
                supports_page_search=True,
                supports_paragraph_search=False,
                supports_entry_search=True,
                supports_text_search=True,
                supports_metadata_search=True
            )
        raise ValueError(f"Perfil de indexação desconhecido: {profile_type}")

@dataclass
class SearchResult:
    document_id: int
    document_title: str
    pdf_page_index: int
    printed_page_label: str
    paragraph_number: Optional[str] = None
    entry_number: Optional[str] = None
    text_snippet: str = ""
    full_text: str = ""
    match_score: float = 100.0
    source_title: Optional[str] = None
    location: Optional[str] = None
    date_str: Optional[str] = None