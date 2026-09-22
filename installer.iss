; Script do Inno Setup — gera um instalador único (LocalizadorSetup.exe)
; a partir da build do PyInstaller (dist/Localizador).
;
; Como usar (no Windows, depois de já ter rodado build_windows.bat):
;   1. Instale o Inno Setup: https://jrsoftware.org/isdl.php
;   2. Abra este arquivo com o Inno Setup Compiler (ou rode via linha de
;      comando: "ISCC.exe installer.iss")
;   3. O instalador final fica em dist_installer\LocalizadorSetup.exe
;
; Instala em %LOCALAPPDATA% (por usuário, SEM precisar de admin) de propósito:
; assim o auto-update do app (app/updater.py) consegue substituir os arquivos
; sozinho, sem pedir permissão de administrador toda vez.

#define MyAppName "Localizador de Citações"
; MyAppVersion normalmente é passada pela linha de comando do build
; (ISCC.exe /DMyAppVersion=2.1.0 installer.iss), para não precisar manter a
; versão duplicada aqui e em app/version.py. Se não for passada, usa este
; valor padrão.
#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif
#define MyAppPublisher "Associação Missionária A Voz do Último Dia"
#define MyAppExeName "Localizador.exe"

[Setup]
AppId={{BC850132-2769-4E66-BBC8-8B810BCDC7FA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Localizador
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist_installer
OutputBaseFilename=LocalizadorSetup
SetupIconFile=app\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Ícones adicionais:"

[Files]
Source: "dist\Localizador\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent
