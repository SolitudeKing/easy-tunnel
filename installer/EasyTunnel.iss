#define MyAppName "EasyTunnel"
#define MyAppPublisher "SolitudeKing"
#define MyAppVersion GetEnv("EASYTUNNEL_VERSION")
#define MySourceDir GetEnv("EASYTUNNEL_SOURCE_DIR")
#define MyOutputDir GetEnv("EASYTUNNEL_OUTPUT_DIR")
#define MyAppExeName "EasyTunnel.exe"

#if MyAppVersion == ""
  #error "EASYTUNNEL_VERSION must be set"
#endif

#if MySourceDir == ""
  #error "EASYTUNNEL_SOURCE_DIR must be set"
#endif

#if MyOutputDir == ""
  #error "EASYTUNNEL_OUTPUT_DIR must be set"
#endif

[Setup]
AppId={{B5E36459-EE8A-4D16-899C-7B132E7559F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EasyTunnel
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir={#MyOutputDir}
OutputBaseFilename=EasyTunnel-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
