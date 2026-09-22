"""
Localização do arquivo de dados (banco SQLite) do usuário.

Por que isso existe
--------------------
A partir da v2.1.0 o instalador (`installer.iss`) instala o app por máquina,
em "Arquivos de Programas" — o que é ótimo para o executável (fica
disponível a qualquer login do Windows), mas ruim para o banco de dados:
usuários comuns (sem direitos de administrador) não conseguem GRAVAR dentro
de "Arquivos de Programas". Se o banco de dados ficasse lá, a primeira
tentativa de escrita falha com `sqlite3.OperationalError: attempt to write
a readonly database`.

A solução padrão do Windows para isso é separar programa (só-leitura, em
Arquivos de Programas) de dados do usuário (gravável, em
`%LOCALAPPDATA%\<Nome>\...`, que é por conta de Windows e sempre gravável
por quem estiver logado, sem precisar de admin).

Em modo de desenvolvimento (rodando `python app/main.py` direto, não
empacotado pelo PyInstaller), mantém o comportamento antigo: usa a pasta
`data/` dentro do próprio projeto, para não mudar o fluxo de quem está
desenvolvendo/testando o código.
"""

import os
import sys

APP_DATA_FOLDER_NAME = "Localizador"


def get_data_dir() -> str:
    """Devolve (e cria, se preciso) a pasta onde o banco de dados do usuário
    deve ficar."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        data_dir = os.path.join(base, APP_DATA_FOLDER_NAME, "data")
    else:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        data_dir = os.path.join(project_root, "data")

    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_db_path() -> str:
    return os.path.join(get_data_dir(), "locator.db")
