"""
Verificador de atualizações via GitHub Releases.

Como funciona
-------------
1. No início do app, `check_for_updates_async` consulta em background a API do
   GitHub (`/repos/{owner}/{repo}/releases/latest`) do repositório configurado
   em `app/version.py`.
2. Se a versão do release mais recente (tag, ex. "v2.1.0") for maior que
   `APP_VERSION`, um sinal Qt dispara a UI perguntando ao usuário se quer
   atualizar agora.
3. Se o usuário aceitar, baixa o asset .zip anexado ao release, extrai para
   uma pasta temporária e grava um script `.bat` que: espera o app fechar,
   substitui os arquivos da instalação atual pelos novos, apaga a pasta
   temporária e reabre o aplicativo. O app então se fecha e o `.bat` assume.

Isso só faz sentido rodando como executável empacotado pelo PyInstaller
(`build_windows.bat`, modo --onedir) — cada novo `git push` de uma tag `vX.Y.Z`
deve disparar o workflow do GitHub Actions (`.github/workflows/release.yml`)
que gera esse .zip e cria o Release automaticamente.
"""

import os
import sys
import json
import zipfile
import tempfile
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal, QThread

from app.version import APP_VERSION, GITHUB_OWNER, GITHUB_REPO

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
REQUEST_TIMEOUT = 8


def _parse_version(v: str) -> Tuple[int, ...]:
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _is_newer(remote: str, local: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


def fetch_latest_release() -> Optional[dict]:
    """Consulta o GitHub e devolve o JSON do release mais recente, ou None se
    não houver internet, o repositório não existir, ou não houver nenhum
    release publicado ainda. Nunca lança exceção para o chamador."""
    try:
        req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def find_windows_asset(release: dict) -> Optional[dict]:
    for asset in release.get("assets", []):
        name = asset.get("name", "").lower()
        if name.endswith(".zip") and ("windows" in name or "win" in name):
            return asset
    # fallback: primeiro .zip anexado, se não houver um nomeado explicitamente
    for asset in release.get("assets", []):
        if asset.get("name", "").lower().endswith(".zip"):
            return asset
    return None


class UpdateCheckWorker(QObject):
    """Roda a verificação de atualização em uma QThread separada, para não
    travar a UI durante a chamada de rede."""

    update_available = Signal(str, str, str)  # versao_remota, notas, url_download
    check_finished = Signal()

    def run(self):
        release = fetch_latest_release()
        if release:
            remote_version = release.get("tag_name", "")
            if remote_version and _is_newer(remote_version, APP_VERSION):
                asset = find_windows_asset(release)
                if asset:
                    self.update_available.emit(
                        remote_version,
                        release.get("body", "") or "",
                        asset.get("browser_download_url", "")
                    )
        self.check_finished.emit()


def check_for_updates_async(on_update_available):
    """Dispara a checagem em background. `on_update_available(versao, notas, url)`
    é chamado na thread principal (via Signal) se houver versão mais nova."""
    thread = QThread()
    worker = UpdateCheckWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.update_available.connect(on_update_available)
    worker.check_finished.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker  # o chamador deve manter referência viva até check_finished


def download_and_apply_update(download_url: str, progress_cb=None) -> bool:
    """Baixa o .zip do release, extrai, e agenda a substituição dos arquivos
    da instalação atual via script .bat que roda após o app fechar.
    Devolve True se o processo de atualização foi agendado com sucesso
    (o chamador deve encerrar o app logo em seguida)."""
    try:
        install_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        tmp_dir = tempfile.mkdtemp(prefix="locator_update_")
        zip_path = os.path.join(tmp_dir, "update.zip")

        with urllib.request.urlopen(download_url, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total:
                        progress_cb(downloaded, total)

        extract_dir = os.path.join(tmp_dir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        if not getattr(sys, "frozen", False):
            # Ambiente de desenvolvimento (não empacotado): não há executável
            # instalado para substituir; só deixa os arquivos baixados prontos.
            return False

        exe_name = os.path.basename(sys.executable)
        bat_path = os.path.join(tmp_dir, "apply_update.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(f"""@echo off
setlocal
set SRC={extract_dir}
set DEST={install_dir}

:wait_close
tasklist /FI "IMAGENAME eq {exe_name}" 2>NUL | find /I "{exe_name}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak > NUL
    goto wait_close
)

xcopy "%SRC%\\*" "%DEST%\\" /E /H /Y /I > NUL
start "" "%DEST%\\{exe_name}"
rmdir /S /Q "{tmp_dir}"
""")

        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        return True
    except Exception:
        return False
