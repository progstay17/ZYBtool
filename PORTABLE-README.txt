# ZYBTool Portable

Version: 0.2.19

1. Extract the complete ZYBTool folder.
2. Double-click ZYBTool.exe.
3. Open Overview to start. In Settings, generate or import the decoder keypair.
4. Copy only the public key to AITQR.

No Python installation, PowerShell setup, or administrator permission is required.
Keep the entire extracted folder together. Application security data is stored separately
under the current Windows user's LocalAppData and protected with Windows DPAPI.

Workspace pages: Overview, Verify Recordings, Review Queue, Arrange Folder, Output & Reports, Activity Log, Preferences and Settings.
Trusted Devices are optional. ZYBTool can start and run metadata/video checks without an allow-list.
ZYBTool does not connect to OSS and has no upload/download/transfer features.


Preferences stores the default source, report, Excel and Organized Folders paths. Excel Export automatically creates ZYB_Rekap.xlsx in the selected Excel folder. Arrange Folder follows the ZYWTool group format YYYYMMDD_MMxx_Recorder_ZYxxx_S<shift>_Activity; matching sessions share a group and keep their original session-folder names. Existing groups are reused without overwriting sessions. Arrange uses MOVE, a confirmation preview, SHA-256 checks, per-run Undo journals, _UNNAMED and _REJECTED groups. Hand Check and Preview Frames are not included.
