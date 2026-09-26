@echo off
setlocal enabledelayedexpansion
title Localizador de Citacoes - Enviar atualizacoes para o GitHub

set REPO_URL=https://github.com/NvEra-Ans/pdf-locator.git

echo ============================================================
echo  Localizador de Citacoes - envio automatico para o GitHub
echo ============================================================
echo.

REM Este .bat precisa estar DENTRO da pasta do projeto (a que tem a
REM pasta ".git" dentro dela -- normalmente "pdf_locator", extraida
REM do zip mais recente que o Claude te mandou).
if not exist ".git" (
    echo [ERRO] Esse arquivo precisa estar dentro da pasta do projeto
    echo        que contem a pasta ".git" ^(geralmente "pdf_locator"^).
    echo        Copie este .bat pra dentro dela e rode de novo.
    echo.
    pause
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Git nao encontrado neste computador. Instale em:
    echo        https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

REM Confere se ja existe um remoto "origin"; se nao existir (zip
REM extraido do zero), configura automaticamente.
git remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo Nenhum remoto "origin" configurado nesta pasta. Configurando...
    git remote add origin %REPO_URL%
    if errorlevel 1 (
        echo [ERRO] Nao consegui configurar o remoto. Veja a mensagem acima.
        pause
        exit /b 1
    )
    echo OK: origin -^> %REPO_URL%
) else (
    for /f "delims=" %%u in ('git remote get-url origin') do set CURRENT_URL=%%u
    echo Remoto "origin" ja configurado: !CURRENT_URL!
    if /I not "!CURRENT_URL!"=="%REPO_URL%" (
        echo [ATENCAO] O endereco configurado e diferente do esperado
        echo           ^(%REPO_URL%^). Prosseguindo mesmo assim.
    )
)
echo.

REM ---------------------------------------------------------------
REM BUG real reportado pelo usuario: rodar este .bat depois de trocar
REM os arquivos da pasta pelo conteudo do zip mais novo (v2.6.2 em
REM diante) sempre dava "Everything up-to-date", mesmo com arquivos
REM visivelmente diferentes -- porque este .bat so fazia "git push",
REM nunca "git add"/"git commit". Os arquivos do zip chegam SEM
REM historico do Git (o zip e gerado sem a pasta ".git", de proposito,
REM pra nao vazar o repositorio inteiro em cada entrega); a pasta
REM rastreada pelo Git no PC do usuario nunca "sabia" que esses
REM arquivos tinham mudado, entao nao havia commit novo nenhum pra
REM enviar. Corrigido comitando (e criando a tag de versao, lida
REM direto de app\version.py) ANTES de enviar.
echo Verificando se ha arquivos novos/alterados...
git add -A
git diff --cached --quiet
if not errorlevel 1 (
    echo Nenhuma mudanca nova encontrada -- pasta ja identica ao ultimo
    echo commit local. Pulando commit, indo direto pro envio.
    echo.
    goto :enviar
)

set VERSION=
for /f "tokens=2 delims== " %%v in ('findstr /b "APP_VERSION" app\version.py') do set VERSION=%%v
set VERSION=%VERSION:"=%
set VERSION=%VERSION: =%

if "%VERSION%"=="" (
    echo Nao consegui ler a versao em app\version.py -- comitando sem tag automatica.
    git commit -m "Atualizacao"
) else (
    echo Versao detectada em app\version.py: %VERSION%
    git commit -m "Atualizacao v%VERSION%"
)
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao comitar as mudancas. Veja a mensagem acima.
    pause
    exit /b 1
)
echo.

if not "%VERSION%"=="" (
    git rev-parse "v%VERSION%" >nul 2>nul
    if errorlevel 1 (
        git tag "v%VERSION%"
        echo Tag v%VERSION% criada.
    ) else (
        echo Tag v%VERSION% ja existia, nao recriei.
    )
    echo.
)

:enviar
echo Enviando a branch "master"...
git push origin master
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao enviar a branch master -- veja a mensagem acima
    echo        ^(login do GitHub pendente, sem internet, conflito etc.^).
    pause
    exit /b 1
)
echo.

echo Enviando as tags de versao...
git push origin --tags
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao enviar as tags. Veja a mensagem acima.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Tudo enviado com sucesso!
echo ============================================================
echo.
echo LEMBRETE: se teve alguma tag nova nesse envio ^(ex.: v2.5.3^) e
echo voce quer gerar o instalador do Windows, va em:
echo   https://github.com/NvEra-Ans/pdf-locator/actions
echo abra "Build e Publicar Release (Windows)", clique em
echo "Run workflow" e selecione a TAG mais nova (nao a branch) antes
echo de confirmar -- as vezes o GitHub nao dispara sozinho quando
echo varias tags sao enviadas de uma vez so.
echo.
pause
