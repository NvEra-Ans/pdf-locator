@echo off
echo ===================================================
echo Gerando Executavel Windows (Localizador.exe)
echo ===================================================

pyinstaller --noconfirm --onedir --windowed ^
    --name "Localizador" ^
    --icon "app/assets/icon.ico" ^
    --add-data "data;data" ^
    --add-data "app/assets;app/assets" ^
    --hidden-import "PySide6" ^
    --hidden-import "fitz" ^
    --hidden-import "rapidfuzz" ^
    app/main.py

echo Build concluido com sucesso! O executavel esta na pasta dist/Localizador.
pause
