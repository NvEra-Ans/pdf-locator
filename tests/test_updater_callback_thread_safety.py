"""
Teste de regressao para bug real reportado pelo usuario (na igreja): abrir
o app com uma versao antiga fazia a janela de "atualizacao disponivel"
congelar e travar o aplicativo inteiro, sem atualizar nada.

Causa raiz CONFIRMADA isolando o mecanismo fora do app (reproduzido
antes de mexer no codigo, com um script standalone): o sinal
`update_available`, emitido de DENTRO da QThread de verificacao (pra nao
travar a UI durante a chamada de rede -- isso em si esta certo), era
conectado a uma funcao Python "solta" (closure comum, sem QObject por
tras). O Qt so consegue entregar um sinal na thread principal quando o
RECEPTOR e um QObject com afinidade de thread conhecida -- pra uma
funcao solta, a chamada acaba rodando na PROPRIA thread de rede que
emitiu o sinal, mesmo com conexao em fila explicita (Qt.QueuedConnection
nao resolve sozinho sem um QObject receptor por tras, confirmado com um
teste isolado). Como o callback abre um QMessageBox (interface grafica),
isso viola a regra do Qt de so mexer na UI pela thread principal --
resultado: uma janela que "aparece" mas nao responde, travando o app
(comportamento indefinido do Qt, sem mensagem de erro clara).

Corrigido em app/main.py: o callback agora e um METODO de QObject
(_UpdateNotifier), nao mais uma funcao solta -- garantindo que o Qt
sempre entregue o sinal na thread principal de verdade.

Este teste verifica o MECANISMO geral (o mesmo usado por
app.updater.check_for_updates_async): um sinal emitido de dentro de uma
QThread, quando conectado a um metodo de QObject, deve ser entregue na
thread principal -- e, como contraprova, confirma que conectar a uma
funcao solta reproduz o bug (roda fora da thread principal), pra deixar
registrado o porque da correcao ser "usar metodo de QObject", nao
qualquer outro ajuste (como so adicionar Qt.QueuedConnection sozinho).
"""
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pyside6 = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication


def _get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class _EmitterWorker(QObject):
    done = Signal(str)

    def run(self):
        self.done.emit("oi")


class _QObjectReceiver(QObject):
    def __init__(self):
        super().__init__()
        self.ran_on_thread = None

    def on_done(self, msg):
        self.ran_on_thread = threading.current_thread()


def _run_emitter_and_wait(connect_fn, timeout=5.0):
    """Sobe uma QThread que emite o sinal 'done' uma vez, conecta com
    connect_fn(worker), espera terminar e devolve o resultado guardado
    pelo receptor. Mesma mecanica usada por
    app.updater.check_for_updates_async."""
    thread = QThread()
    worker = _EmitterWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    connect_fn(worker)
    worker.done.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)

    finished = {"done": False}

    def _mark_finished():
        finished["done"] = True

    thread.finished.connect(_mark_finished)
    thread.start()

    app = _get_app()
    deadline = time.time() + timeout
    while time.time() < deadline and not finished["done"]:
        app.processEvents()
        time.sleep(0.005)

    assert finished["done"], "A QThread de teste não terminou dentro do timeout"


def test_signal_to_qobject_method_runs_on_main_thread():
    """Mecanismo CORRIGIDO (o que app/main.py usa agora, via
    _UpdateNotifier): conectar o sinal emitido pela QThread a um METODO
    de QObject entrega a chamada na thread principal."""
    app = _get_app()
    main_thread = threading.current_thread()
    receiver = _QObjectReceiver()

    _run_emitter_and_wait(lambda worker: worker.done.connect(receiver.on_done))

    assert receiver.ran_on_thread is main_thread, (
        f"BUG: callback rodou fora da thread principal ({receiver.ran_on_thread!r}), "
        "reproduz o travamento real reportado pelo usuário"
    )


def test_signal_to_plain_function_runs_on_wrong_thread():
    """Contraprova: conectar a uma função Python solta (sem QObject por
    trás) -- o jeito ANTIGO, que causava o bug real -- roda fora da
    thread principal, mesmo hoje. Documenta por que a correção precisa
    ser "usar método de QObject", não outro ajuste qualquer."""
    app = _get_app()
    main_thread = threading.current_thread()
    result = {"ran_on_thread": None}

    def plain_callback(msg):
        result["ran_on_thread"] = threading.current_thread()

    _run_emitter_and_wait(lambda worker: worker.done.connect(plain_callback))

    assert result["ran_on_thread"] is not main_thread, (
        "Esperava reproduzir o bug (função solta rodando fora da thread "
        "principal) -- se isso passou a rodar na thread principal, o "
        "comportamento do PySide6 mudou e o comentário/justificativa da "
        "correção em app/main.py precisa ser revisto."
    )


if __name__ == "__main__":
    test_signal_to_qobject_method_runs_on_main_thread()
    test_signal_to_plain_function_runs_on_wrong_thread()
    print("OK: callback de atualização entregue na thread principal via método de QObject.")
