import sys
import os

# Garante que a raiz do projeto esteja no PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication, QMessageBox
from app.database.connection import DatabaseConnection
from app.database.schema import DatabaseSchemaManager
from app.ui.main_window import MainWindow
from app.version import APP_NAME_SHORT, APP_VERSION
from app.updater import check_for_updates_async, download_and_apply_update
from app.paths import get_db_path


class _UpdateNotifier(QObject):
    """BUG real reportado pelo usuário (na igreja): ao abrir o app com uma
    versão antiga, a janela de "atualização disponível" congelava e travava
    o aplicativo inteiro, sem atualizar nada.

    Causa raiz confirmada (reproduzida isolada, fora do app, antes de
    mexer aqui): `check_for_updates_async` roda a checagem numa QThread
    separada -- correto, evita travar a UI durante a chamada de rede. Só
    que o sinal `update_available`, emitido de DENTRO dessa thread, era
    conectado a uma função Python "solta" (uma closure comum, não um
    método de QObject). O Qt só consegue entregar um sinal na thread
    CORRETA (a principal, dona da interface) quando o receptor é um
    QObject com afinidade de thread conhecida -- pra uma função solta,
    sem QObject nenhum por trás, o Qt não tem como saber em qual thread
    entregar, e a chamada acaba rodando na PRÓPRIA thread de rede que
    emitiu o sinal, mesmo pedindo conexão em fila explicitamente
    (Qt.QueuedConnection não resolve sozinho sem um QObject receptor).

    Como o callback abre um QMessageBox (interface gráfica), rodar isso
    fora da thread principal viola a regra do Qt de só mexer na UI pela
    thread principal -- o resultado observado é exatamente uma janela
    que "aparece" mas não responde a mais nada, travando o app inteiro
    (comportamento indefinido do Qt nessa situação, não um erro com
    mensagem clara, o que tornava isso difícil de diagnosticar só pelo
    relato do usuário).

    Corrigido tornando o callback um MÉTODO deste QObject (instanciado na
    thread principal, junto com o resto da UI) em vez de uma função
    solta -- agora o Qt sabe entregar o sinal na thread certa de
    verdade."""

    def __init__(self, app: QApplication, window: MainWindow):
        super().__init__()
        self.app = app
        self.window = window

    @Slot(str, str, str)
    def on_update_available(self, remote_version: str, notes: str, download_url: str):
        resp = QMessageBox.question(
            self.window,
            "Atualização disponível",
            f"Uma nova versão ({remote_version}) está disponível.\n"
            f"Versão atual: {APP_VERSION}\n\n"
            f"Deseja baixar e instalar agora? O aplicativo será reiniciado.",
        )
        if resp == QMessageBox.Yes:
            ok = download_and_apply_update(download_url)
            if ok:
                self.app.quit()
            else:
                QMessageBox.warning(
                    self.window, "Atualização",
                    "Não foi possível aplicar a atualização automaticamente. "
                    "Baixe a nova versão manualmente na página de releases do GitHub."
                )


def main():
    app = QApplication(sys.argv)
    # BUG real reportado pelo usuário (print de tela): a caixa de seleção de
    # documento (QComboBox) aparecia com uma borda amarela grossa e cantos
    # cortados/quadrados em vez do arredondado definido no tema -- causa
    # raiz: sem um estilo base explícito, o Qt usa o estilo nativo do Windows
    # ("windowsvista"), que desenha sua própria moldura/foco por cima da
    # QSS customizada (border-radius, border-color) em vez de deixar a QSS
    # controlar sozinha. É um conflito conhecido do Qt entre estilo nativo e
    # style sheets -- a correção recomendada pela própria documentação do Qt
    # é usar o estilo "Fusion", que é 100% desenhado pela QSS.
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME_SHORT)
    app.setApplicationVersion(APP_VERSION)

    # Inicializa Conexão e Schema do Banco de Dados. get_db_path() decide o
    # local certo: %LOCALAPPDATA%\Localizador\data (gravável sem precisar de
    # admin) quando empacotado, ou a pasta data/ do projeto em desenvolvimento.
    db_conn = DatabaseConnection(get_db_path())
    schema_mgr = DatabaseSchemaManager(db_conn)
    schema_mgr.initialize_database()

    # Inicia a Interface Gráfica (reaproveita a mesma conexão, em vez de cada
    # parte do app abrir a sua própria)
    window = MainWindow(db_conn=db_conn)
    window.show()

    # Verifica atualizações em segundo plano (não bloqueia a abertura do app).
    # Mantemos as referências (thread/worker/notifier) em app._update_refs
    # para que não sejam destruídas pelo garbage collector antes de terminar.
    # O callback precisa ser um MÉTODO de QObject (ver _UpdateNotifier acima)
    # -- não mais uma função solta -- pra garantir que rode na thread
    # principal, e não trave a UI (bug real corrigido, ver docstring da
    # classe).
    notifier = _UpdateNotifier(app, window)
    thread, worker = check_for_updates_async(notifier.on_update_available)
    app._update_refs = (thread, worker, notifier)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
