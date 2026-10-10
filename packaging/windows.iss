#define MyAppVersion "0.2.1"
[Setup]
AppId={{5D95E7A8-A208-43C6-9876-F00B049BAC56}
AppName=延河课堂
AppVersion={#MyAppVersion}
AppPublisher=Yanhekt Downloader
AppPublisherURL=https://github.com/Fangwenky/yanhekt-downloader
DefaultDirName={localappdata}\Programs\YanhektDownloader
DefaultGroupName=延河课堂
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Yanhekt-Windows-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\YanhektDownloader.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Files]
Source: "..\dist\YanhektDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
[Icons]
Name: "{group}\延河课堂"; Filename: "{app}\YanhektDownloader.exe"
Name: "{autodesktop}\延河课堂"; Filename: "{app}\YanhektDownloader.exe"
[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "准备 WebView2 显示组件…"; Check: NeedsWebView2; Flags: waituntilterminated
Filename: "{app}\YanhektDownloader.exe"; Description: "打开延河课堂"; Flags: nowait postinstall skipifsilent
[Code]
function NeedsWebView2: Boolean;
var Version: String;
begin
  Result := not (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version));
end;
