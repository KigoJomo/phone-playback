#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
[Setup]
AppId={{EBF88818-3938-4AF2-8598-B7267E03EFC7}
AppName=Phone Playback
AppVersion={#AppVersion}
AppPublisher=Jomo Kigo
AppPublisherURL=https://github.com/KigoJomo/phone-playback
AppSupportURL=https://github.com/KigoJomo/phone-playback/issues
DefaultDirName={localappdata}\Programs\Phone Playback
DefaultGroupName=Phone Playback
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
AppMutex=Local\PhonePlayback
WizardStyle=modern
SetupIconFile=..\docs\phone-playback.ico
UninstallDisplayIcon={app}\PhonePlayback.exe
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=PhonePlayback-Setup-{#AppVersion}-win-x64
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: startup; Description: "Start Phone Playback when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\dist\PhonePlayback\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Phone Playback"; Filename: "{app}\PhonePlayback.exe"
Name: "{autodesktop}\Phone Playback"; Filename: "{app}\PhonePlayback.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "PhonePlayback"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PhonePlayback"; ValueData: """{app}\PhonePlayback.exe"""; Tasks: startup

[Run]
Filename: "{app}\PhonePlayback.exe"; Description: "Open Phone Playback"; Flags: nowait postinstall skipifsilent
