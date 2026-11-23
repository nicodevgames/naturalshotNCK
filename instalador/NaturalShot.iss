; Instalador de NaturalShot PRO (NS-102.1), con Inno Setup 6 (https://jrsoftware.org/isinfo.php).
; Lo arma construir_instalador.bat después de construir_exe.bat:
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DVersion=1.0.1 instalador\NaturalShot.iss
;
; * Instala en %LOCALAPPDATA%\Programs\NaturalShot PRO, SIN pedir permisos de administrador
;   (PrivilegesRequired=lowest): así el actualizador de la app puede escribir en su carpeta.
; * Acceso directo en el menú Inicio (y en el escritorio si se elige) y desinstalador en
;   "Aplicaciones instaladas" de Windows.
; * Al desinstalar no toca las fotos ni las preferencias del usuario (QSettings), solo la carpeta de la app.

#ifndef Version
  #error Falta /DVersion=X.Y.Z (lo pasa construir_instalador.bat desde celular_natural/__init__.py)
#endif

#define AppName "NaturalShot PRO"
#define AppExe "NaturalShot.exe"

[Setup]
; AppId fijo: Windows reconoce cada versión nueva como la misma app (la actualiza, no la duplica).
AppId={{8C0E8F7A-4C52-4E8B-9C1D-5A7D2F3B6E91}
AppName={#AppName}
AppVersion={#Version}
AppVerName={#AppName} {#Version}
AppPublisher=NaturalShot
VersionInfoVersion={#Version}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
OutputDir=..\dist\instalador
OutputBaseFilename=NaturalShot-Setup-{#Version}
SetupIconFile=..\assets\icono.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
; Todo lo que arma PyInstaller (NaturalShot.exe y _internal).
Source: "..\dist\NaturalShot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: escritorio

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
