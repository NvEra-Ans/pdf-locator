# Localizador de Citações — A Voz do Último Dia

Aplicativo Desktop local para Windows capaz de indexar e realizar pesquisas estruturadas em coleções de documentos e livros PDF.

Versão atual: **2.1.1** (ver `app/version.py`)

## Funcionalidades
- **Arquitetura por Perfis de Documentos (`DocumentIndexProfile`)**:
  - **Perfil Tipo A (Livro Estruturado)**: Busca por Página, Parágrafo, Texto Exato e Aproximado.
  - **Perfil Tipo B (Livro de Citações/Extratos)**: Busca por Página, Número do Extrato, Texto e Metadados.
- **Indexação de Alta Performance**: Utiliza SQLite FTS5 para buscas textuais em milissegundos.
- **Leitura em ordem de colunas real**: PDFs em layout de 2 colunas são indexados na ordem de leitura correta (coluna esquerda inteira, depois a direita), evitando cortar parágrafos/extratos que atravessam a quebra de coluna (`analyzer/layout.py`).
- **Busca Aproximada (Fuzzy)**: Integração com RapidFuzz para tolerar erros de OCR e diferenças de acentuação.
- **Interface renovada**: cabeçalho com identidade visual, modo claro/escuro, fonte maior e mais legível no painel de resultado.
- **Atualização automática**: ao abrir, o app verifica se há uma versão mais nova publicada no GitHub e se oferece para se auto-atualizar (`app/updater.py`).
- **Visualizador e Exportador**: Permite copiar referências formatadas e texto selecionado com um clique.

## Instalação e Execução (Desenvolvimento)
1. Instale o Python 3.12+.
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Rode o app:
   ```bash
   python app/main.py
   ```

## Gerando o executável Windows e o instalador único
Pré-requisitos:
- `pip install -r requirements.txt` e `pip install pyinstaller` já rodados.
- [Inno Setup](https://jrsoftware.org/isdl.php) instalado (gratuito) — é o que gera o instalador de um arquivo só.

```
build_windows.bat
```

> Se aparecer `'pyinstaller' não é reconhecido...`, é PATH do Windows (comum quando o Python foi instalado sem a opção de adicionar tudo ao PATH). O script já roda com `python -m PyInstaller` em vez de `pyinstaller` sozinho justamente para evitar isso — mas se ainda assim der esse erro, confirme que `python --version` funciona no seu terminal antes de mais nada.
Isso gera dois artefatos:
- `dist/Localizador/Localizador.exe` — a pasta do app "solta" (o que o auto-update usa por baixo dos panos).
- `dist_installer/LocalizadorSetup.exe` — **o instalador único** para distribuir a outros PCs. É esse arquivo que você entrega: clica duas vezes, pede permissão de administrador (uma vez, na instalação), instala em `Arquivos de Programas`, cria atalho na Área de Trabalho e no Menu Iniciar **para qualquer login do Windows nesse PC**, e fica com desinstalador próprio no Windows.

Se o Inno Setup não estiver no PATH, o script só gera a pasta e avisa — instale o Inno Setup e rode `build_windows.bat` de novo, ou compile `installer.iss` manualmente abrindo-o no Inno Setup Compiler.

> **Trade-off consciente**: instalar em `Arquivos de Programas` (por máquina, todos os logins) em vez de `%LOCALAPPDATA%` (por usuário) foi escolhido porque o app deve estar disponível pra qualquer pessoa que logar no PC. O preço disso: o auto-update (`app/updater.py`) não consegue mais gravar ali silenciosamente — ele pede elevação (prompt de UAC do Windows) na hora de aplicar a atualização. Se quem estiver logado no momento não for administrador da máquina, o prompt aparece e não pode ser confirmado; a atualização simplesmente fica pendente e é oferecida de novo na próxima abertura do app, sem travar nada.

## Publicando uma nova versão (auto-update para quem já tem o app instalado)

1. Atualize `APP_VERSION` em `app/version.py` (ex.: `"2.1.0"`).
2. Confirme e faça push das mudanças:
   ```bash
   git add -A
   git commit -m "Versão 2.1.0"
   git push
   ```
3. Crie e envie a tag da versão (precisa começar com `v` e seguir `MAJOR.MINOR.PATCH`):
   ```bash
   git tag v2.1.0
   git push origin v2.1.0
   ```
4. O workflow `.github/workflows/release.yml` builda o `.exe` automaticamente numa máquina Windows do GitHub Actions, compacta em `Localizador-Windows.zip`, gera também `LocalizadorSetup.exe` (instalador único) e publica os dois num GitHub Release.
5. Todo app já instalado que for aberto a partir de agora vai detectar essa versão nova (comparando com `app/version.py` local), perguntar ao usuário se quer atualizar e, se aceito, baixar e substituir os arquivos sozinho, reabrindo o app já atualizado.

> Isso depende de `GITHUB_OWNER`/`GITHUB_REPO` em `app/version.py` apontarem para o repositório certo, e de o repositório ser público (ou o updater precisaria de autenticação, o que não está implementado nesta versão).

## Estrutura
```
app/
  assets/        Ícone e logo do aplicativo
  database/      Conexão SQLite e schema
  indexing/      Indexadores por perfil de documento (Parágrafos / Extratos)
  models/        Modelos de dados (SearchResult, ProfileType, ...)
  search/        Motor de busca (FTS5 + fuzzy)
  ui/            Interface (janela principal, temas claro/escuro)
  main.py        Ponto de entrada
  updater.py     Verificação e aplicação de atualizações via GitHub Releases
  version.py     Nome e versão do app
analyzer/
  pattern_detector.py   Detecção de números de página/parágrafo/extrato
  layout.py             Reordenação de blocos em ordem de leitura (colunas)
.github/workflows/release.yml   Build + publicação automática do release
installer.iss                   Script do Inno Setup (gera o instalador único)
```
