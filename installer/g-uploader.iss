; Inno Setup 스크립트. GitHub Actions(release.yml)에서 /DAppVersion=x.y.z 로 빌드한다.
; 사용자별 설치(관리자 권한 불필요)라서 자동 업데이트가 UAC 창 없이 덮어쓴다.
; 사용자 데이터(%APPDATA%\G-UPLOADER)는 건드리지 않는다.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0C2E3B-4B8A-4F5C-9D1E-6A2B7C9F1D21}
AppName=G-UPLOADER
AppVersion={#AppVersion}
AppPublisher=G-UPLOADER contributors
DefaultDirName={localappdata}\Programs\G-UPLOADER
DefaultGroupName=G-UPLOADER
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=G-UPLOADER-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
CloseApplications=force
RestartApplications=no
WizardStyle=modern
UninstallDisplayIcon={app}\G-UPLOADER.exe

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; Flags: unchecked

[Files]
Source: "..\dist\G-UPLOADER\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; 이전 버전의 프로그램 파일 정리(사용자 데이터는 다른 폴더라 안전)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\G-UPLOADER"; Filename: "{app}\G-UPLOADER.exe"
Name: "{autodesktop}\G-UPLOADER"; Filename: "{app}\G-UPLOADER.exe"; Tasks: desktopicon

[Run]
; 자동 업데이트(/SILENT) 후에도 다시 실행되도록 skipifsilent를 쓰지 않는다.
Filename: "{app}\G-UPLOADER.exe"; Description: "G-UPLOADER 실행"; Flags: nowait postinstall
