[Setup]
AppName=YouTube Floating Downloader
AppVersion=1.0.5
VersionInfoVersion=1.0.5.0
DefaultDirName={localappdata}\YTDownloader
DefaultGroupName=YT Downloader
OutputDir=..\dist_installer
OutputBaseFilename=YTDownloader_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest

[Files]
Source: "..\backend\dist\YTService\*"; DestDir: "{app}"; Flags: recursesubdirs
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: recursesubdirs

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "YTDownloaderService"; ValueData: """{app}\YTService.exe"""; Flags: uninsdeletevalue

[Icons]
Name: "{group}\YT Downloader"; Filename: "{app}\YTService.exe"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\YTService.exe"; Parameters: "--skip-update-check"; Flags: nowait postinstall runasoriginaluser