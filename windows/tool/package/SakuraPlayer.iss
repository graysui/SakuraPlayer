#ifndef AppVersion
#define AppVersion "0.0.0"
#endif
#ifndef SourceDir
#define SourceDir "."
#endif

[Setup]
AppId={{8F5BA8AA-5B7E-4B3C-9E9B-5B4D8F2B19D5}
AppName=SakuraPlayer
AppVersion={#AppVersion}
AppPublisher=SakuraPlayer
DefaultDirName={localappdata}\Programs\SakuraPlayer
DefaultGroupName=SakuraPlayer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputBaseFilename=SakuraPlayer-Windows-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\sakuraplayer_windows.exe

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\SakuraPlayer"; Filename: "{app}\sakuraplayer_windows.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\sakuraplayer_windows.exe"; Description: "启动 SakuraPlayer"; Flags: nowait postinstall skipifsilent
