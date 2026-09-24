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
