@echo off
echo ===================================================
echo 1/2 - Gerando Executavel Windows (Localizador.exe)
echo ===================================================

python -m PyInstaller --noconfirm --onedir --windowed ^
    --name "Localizador" ^
    --icon "app/assets/icon.ico" ^
    --add-data "data;data" ^
    --add-data "app/assets;app/assets" ^
    --hidden-import "PySide6" ^
    --hidden-import "fitz" ^
    --hidden-import "rapidfuzz" ^
    app/main.py

if errorlevel 1 (
    echo Falha no build do PyInstaller. Abortando.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo 2/2 - Gerando instalador unico (LocalizadorSetup.exe)
echo ===================================================

for /f "delims=" %%v in ('python -c "import sys; sys.path.insert(0,'.'); from app.version import APP_VERSION; print(APP_VERSION)"') do set APP_VERSION=%%v
echo Versao detectada: %APP_VERSION%

where ISCC.exe >nul 2>nul
if errorlevel 1 (
    echo AVISO: Inno Setup (ISCC.exe) nao encontrado no PATH.
    echo Instale em https://jrsoftware.org/isdl.php e rode este script de novo,
    echo ou compile installer.iss manualmente pelo Inno Setup Compiler.
    echo O executavel da pasta ja foi gerado em dist\Localizador\Localizador.exe
    pause
    exit /b 0
)

ISCC.exe /DMyAppVersion=%APP_VERSION% installer.iss

echo.
echo Build concluido!
echo  - Pasta do app: dist\Localizador\
echo  - Instalador unico: dist_installer\LocalizadorSetup.exe
pause
