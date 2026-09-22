import sys
import os

# Garante que a raiz do projeto esteja no PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QMessageBox
from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.ui.main_window import MainWindow
from app.version import APP_NAME_SHORT, APP_VERSION
from app.updater import check_for_updates_async, download_and_apply_update


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME_SHORT)
    app.setApplicationVersion(APP_VERSION)

    # Inicializa Conexão e Schema do Banco de Dados
    db_conn = DatabaseConnection("data/locator.db")
    schema_mgr = DatabaseSchemaManager(db_conn)
    schema_mgr.initialize_database()

    # Inicia a Interface Gráfica
    window = MainWindow()
    window.show()

    # Verifica atualizações em segundo plano (não bloqueia a abertura do app).
    # Mantemos as referências (thread/worker) em app._update_refs para que não
    # sejam destruídas pelo garbage collector antes de terminar.
    def _on_update_available(remote_version, notes, download_url):
        resp = QMessageBox.question(
            window,
            "Atualização disponível",
            f"Uma nova versão ({remote_version}) está disponível.\n"
            f"Versão atual: {APP_VERSION}\n\n"
            f"Deseja baixar e instalar agora? O aplicativo será reiniciado.",
        )
        if resp == QMessageBox.Yes:
            ok = download_and_apply_update(download_url)
            if ok:
                app.quit()
            else:
                QMessageBox.warning(
                    window, "Atualização",
                    "Não foi possível aplicar a atualização automaticamente. "
                    "Baixe a nova versão manualmente na página de releases do GitHub."
                )

    app._update_refs = check_for_updates_async(_on_update_available)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
