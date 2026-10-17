
#define MyAppName "AstroWeather"
#define MyAppVersion "0.1.0"
#define MyAppExeName "AstroWeather.exe"

[Setup]
AppId={{B7A9C2D4-81F6-4D10-AE31-9C5F20A7B612}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\AstroWeather
DefaultGroupName=AstroWeather
OutputDir=installer-output
OutputBaseFilename=AstroWeather-Setup
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\AstroWeather\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AstroWeather"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\AstroWeather"; \
    Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch AstroWeather"; \
    Flags: postinstall nowait skipifsilent
