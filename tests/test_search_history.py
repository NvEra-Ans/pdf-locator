"""
Teste da funcionalidade "Histórico de Pesquisas" -- pedido real do
usuário: registro cronológico do que foi buscado (e encontrado),
exportável pra um .txt (Bloco de Notas), organizado da pesquisa mais
antiga pra mais nova.

Decisões confirmadas com o usuário e cobertas aqui:
  - Cada linha registra a busca E o que foi encontrado.
  - Só buscas com resultado entram no histórico (ver
    test_document_switch_clears_fields.py e main_window.py --
    log_search só é chamado quando current_results não está vazio).
  - Histórico único (todos os documentos juntos), ordem cronológica.
  - Exportação pra .txt e limpeza do histórico inteiro.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.search.history import SearchHistoryManager
from app.models.document import SearchResult


def _make_manager():
    tmp_dir = tempfile.mkdtemp()
    db_conn = DatabaseConnection(os.path.join(tmp_dir, "test_history.db"))
    DatabaseSchemaManager(db_conn).initialize_database()
    return SearchHistoryManager(db_conn)


def test_build_query_summary_only_includes_filled_fields():
    summary = SearchHistoryManager.build_query_summary(page_label="250")
    assert summary == "Página: 250"

    summary_full = SearchHistoryManager.build_query_summary(
        page_label="250", paragraph_num="1", text_query="abc", use_fuzzy=True
    )
    assert "Página: 250" in summary_full
    assert "Parágrafo: 1" in summary_full
    assert 'Texto: "abc"' in summary_full
    assert "Busca Aproximada" in summary_full

    assert SearchHistoryManager.build_query_summary() == "(sem filtros)"


def test_build_result_summary_formats_references_and_caps_list():
    results = [
        SearchResult(document_id=1, document_title="T", pdf_page_index=0,
                     printed_page_label="250", paragraph_number="1"),
        SearchResult(document_id=1, document_title="T", pdf_page_index=0,
                     printed_page_label="300", entry_number="251"),
    ]
    summary = SearchHistoryManager.build_result_summary(results)
    assert "Página 250, Parágrafo 1" in summary
    assert "Página 300, Extrato 251" in summary

    many_results = [
        SearchResult(document_id=1, document_title="T", pdf_page_index=0,
                     printed_page_label=str(100 + i), paragraph_number=str(i))
        for i in range(8)
    ]
    capped = SearchHistoryManager.build_result_summary(many_results, max_refs=5)
    assert "(e mais 3)" in capped


def test_log_search_and_list_history_is_chronological():
    mgr = _make_manager()
    mgr.log_search("Livro dos Selos", "Página: 250", "Página 250, Parágrafo 1")
    mgr.log_search("Libro de Citas", "Extrato: 251", "Página 300, Extrato 251")

    entries = mgr.list_history()
    assert len(entries) == 2
    # A PRIMEIRA pesquisa feita deve vir primeiro (cronológico a partir
    # da primeira -- pedido explícito do usuário).
    assert entries[0].document_title == "Livro dos Selos"
    assert entries[1].document_title == "Libro de Citas"


def test_clear_history_removes_everything():
    mgr = _make_manager()
    mgr.log_search("Livro dos Selos", "Página: 250", "Página 250, Parágrafo 1")
    assert len(mgr.list_history()) == 1

    mgr.clear_history()
    assert len(mgr.list_history()) == 0


def test_export_to_txt_is_chronological_and_readable():
    mgr = _make_manager()
    mgr.log_search("Livro dos Selos", "Página: 250", "Página 250, Parágrafo 1")
    mgr.log_search("Libro de Citas", "Extrato: 251", "Página 300, Extrato 251")

    tmp_dir = tempfile.mkdtemp()
    out_path = os.path.join(tmp_dir, "historico.txt")
    count = mgr.export_to_txt(out_path)
    assert count == 2

    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()

    # A primeira pesquisa (Livro dos Selos) precisa aparecer ANTES da
    # segunda (Libro de Citas) no arquivo exportado.
    pos_selos = content.index("Livro dos Selos")
    pos_citas = content.index("Libro de Citas")
    assert pos_selos < pos_citas
    assert "Página 250, Parágrafo 1" in content
    assert "Página 300, Extrato 251" in content


if __name__ == "__main__":
    test_build_query_summary_only_includes_filled_fields()
    test_build_result_summary_formats_references_and_caps_list()
    test_log_search_and_list_history_is_chronological()
    test_clear_history_removes_everything()
    test_export_to_txt_is_chronological_and_readable()
    print("OK: historico de pesquisas registra, lista e exporta corretamente.")
