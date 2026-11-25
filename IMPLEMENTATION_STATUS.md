# ZYB Tool — Implementation Status

Updated: 2026-11-25

## M1 — offline verification foundation

Implemented:
- Deterministic recursive discovery, including hidden .live_* folders; symlinks are not followed.
- Tolerant parsing of session JSON, sync JSON, t0 JSON, app logs and IMU frametimes CSV.
- Streaming MKV demux/timeline inspection with PyAV; no full-video buffering.
- Conservative grouping. FINAL/LIVE linking requires matching device, live_root, creation time and identical media hashes. Uncertain links are not guessed.
- Central status decision point. Metadata-only recordings remain METADATA_ONLY; they never become VERIFIED.
- Atomic JSON inventory/groups/reports plus supervisor HTML and CSV views.
- CLI entry point: zybtool scan.
- Consumer-owned JSON Schema for the AITQR zyb-recording/v1 payload contract.
- Windows CI workflow with Ruff, mypy and pytest.

## M2 — Metaqr / QR verification foundation

Implemented in the local source:
- Metaqr 0.4.0 is pinned to commit baae37471201b3ae3477d0cf0dcb8ffd26e4dc76. No local cryptographic reimplementation.
- PyAV frame sampler reads incrementally, begins at usable_start_s, samples 5 fps over a 30-second window by default, and checks left/right eye crop rectangles from camera meta.json. Full-frame fallback is used only when valid crops are unavailable.
- MQ2 uses Metaqr.verify with the X25519 decoder private key and Ed25519 allow-list. MQ1/unsigned tokens are not accepted as identity proof.
- Allow-list import is validated by Metaqr. Replay source is recording_id, so the same token can repeat across frames/segments inside one recording but is rejected in another recording.
- Current zyb-recording/v1 payload shape is checked strictly, including exact field set and the available session device_id comparison.
- Decoder private key is protected with Windows DPAPI under the current Windows user profile; no plaintext fallback. CLI supports local key generation, concealed private-key import, public-key export, allow-list import, status and key removal.
- JSON/CSV/HTML reports include QR status, signer, token ID and first-seen time when scanning is configured.
- Approved output copies can enrich the existing camera session.json under zybtool.qr_metadata; native fields and source files are preserved. Verified QR output is blocked if the native session.json is missing or the enrichment namespace already exists. The manifest records both source and enriched output hashes.
- Trust is deliberately capped at level 2 and reported as VERIFIED_WITH_WARNING. The remaining time/session/camera correlations and signed manifest are not claimed complete.

## Validation on local Windows workstation (2026-11-25)

Environment: Python 3.12.15, PyAV 19.0.2, Metaqr 0.4.0, OpenCV reader, NumPy, Ruff 0.17.5, mypy 2.4.1, pytest 9.2.0.

- Metaqr VCS dependency installed successfully at the pinned commit.
- Ruff check: passed.
- Ruff format check: passed.
- mypy: no issues in 14 source modules.
- Unit/synthetic suite: 19 passed, 2 optional tests skipped.
- DPAPI key protect/unprotect round-trip: passed on Windows; test also confirmed settings.json does not contain the private key in plaintext.
- Signed QR end-to-end: MQ2 encoded, rendered, embedded in a synthetic MKV, found using the configured eye crop, decrypted, signature-verified and payload-checked.
- Replay test: the same signed QR token was accepted for its first recording and rejected when reused under a different recording_id.
- CLI version, settings help, temporary key-generation, status and public-key export smoke checks: passed. Test key was stored under a temporary test directory and removed afterward; no user's real decoder key was configured.
- Wheel: dist/zybtool-0.1.0-py3-none-any.whl built successfully (27,075 bytes; SHA-256 fa3a95e47a84fe13537a8db5b97d8126224630ba992291b564d106a7ceb5c655).
- Source recording folders remained read-only.

## M2 — still required before production use

- Run camera-real footage captured by AITQR and check readability at actual camera distance, blur, rotation, compression, crop alignment and first usable frame.
- AITQR's final payload contract and shared deterministic vectors are still pending. The present schema is the existing ZYBTool-side draft, not a final cross-repo agreement.
- Key ownership is agreed: ZYBTool generates and stores the X25519 decoder keypair; only the public key is handed to AITQR. The private key never leaves this Windows PC. AITQR must not generate or receive the decoder private key. The concealed CLI import remains a controlled recovery path only when no decoder key is configured; a public key alone cannot decrypt.
- Verify session ID, recorder, capture time, camera serial, QR time and segment mapping against the final AITQR payload before raising trust above level 2.
- Allow-list integrity/access control still depends on local file permissions; Metaqr's allow-list format is not itself signed.
- Replay log is single-writer only; run one scan process at a time when using the replay log.

## M3 — local output preparation

Implemented foundation:
- Reviewed plan and explicit operator confirmation before copy.
- METADATA_ONLY recordings are copied under _UNNAMED/<recording-id>; no invented operational name.
- QR metadata is supplemental to the camera's native session.json; verified payload is stored under zybtool.qr_metadata in the output copy only. Existing native keys are preserved; conflicts are blocked.
- Original source folders are read-only; directory names and file bytes are preserved. Symlinks and special files are rejected.
- SHA-256 is streamed before and after copy; source is re-hashed to detect changes. Existing/non-empty destinations and file collisions stop the operation; no overwrite.
- Atomic staging directory, persisted output_plan.json, and local manifest with per-file hashes.

Remaining before production: trust level 3+ correlations, final shared AITQR vectors, administrator manifest signature, and validation of the downstream folder layout. The local manifest is explicitly marked unsigned.

## OSS integration — out of scope

ZYBTool has no OSS credentials, bucket listing, upload, download, sync or transfer functionality. OSS folder names are a naming-pattern reference only. AITQR owns the configurable source fields and emits the QR payload; ZYBTool validates that payload.

## Desktop UI — workspace foundation

Implemented locally:
- Functional Overview, Verify Recordings (background scan), Review Queue, Output & Reports (local JSON/CSV/HTML), Activity Log and Settings navigation.
- A native Windows desktop shell using the Python standard-library Tkinter; no additional GUI package was added.
- Dark graphite / restrained signal-green styling aligned with DESIGN.md.
- Security & Keys page: decoder key state, public key display and clipboard copy, one-time key generation, concealed two-entry private-key recovery import, optional allow-list JSON import, trusted-device count, local storage location and folder access.
- Trusted Devices is explicitly optional: no pairing is required to launch or use ZYBTool. If no allow-list is configured, QR signature checks are skipped while the normal metadata/video verification pipeline continues; no untrusted signer is treated as verified.
- Existing decoder key is never regenerated from the normal UI. The generate action is disabled after setup; key removal requires a warning that old QR may become undecryptable.
- `run-gui.ps1` launches the app without a console window; `zybtool-gui` is also registered as a project entry point.
- All workspace navigation pages are enabled; verification runs in a background worker and report actions open local artifacts.

Validation on local Windows workstation (2026-11-25):
- Ruff check: passed; Ruff format check: passed.
- mypy: no issues in 17 source modules.
- Latest unit/synthetic suite: 26 passed, 1 optional external-folder integration test skipped (no `ZYB_SAMPLES_DIR` was set for this run).
- Tkinter GUI self-test: passed (Tk 8.6); local settings status read successfully without generating a production decoder key.
- Desktop launch via `run-gui.ps1`: a `ZYBTool` window was observed running from the project environment.
- Regression: decoder key generation and `set_decoder_private_key` both refuse to replace an existing key.
- Latest wheel before public-fixture sanitization: `dist/zybtool-0.1.0-py3-none-any.whl`, 33,481 bytes; verified to contain `zybtool/gui.py` and the `zybtool-gui` console entry point. SHA-256: `f712c8de626b4f459c49bbb35fe1275d1e38664847e210c655650c2755e6f242`.

A standalone Windows x64 portable folder + ZIP is built with PyInstaller; the GUI executable was smoke-tested on the local workstation. Release v0.1.1 adds the Settings private-key import recovery flow. Workspace navigation, local reports and guarded local output-copy workflow are in the unreleased 0.2.1 development build.

## Project boundary

- AITQR was treated as a read-only contract dependency and was not modified.
- ZYWtool and Metaqr were not modified.
- The published source history is tracked in the project GitHub repository.


## Update 2026-11-25 — Arrange MOVE dan Excel Export

- Hand Check dan Preview Frames tidak termasuk scope ZYBTool.
- Arrange Folder memakai MOVE, bukan copy. Ada preview/konfirmasi, penolakan destination collision, pemeriksaan struktur dan SHA-256, manifest unsigned, journal `move_journal.json`, dan Undo guarded.
- Excel Export menulis ZY White, Cek File, Scan Audit, dan Rekonsiliasi; kolom manual QC/supervisor pada ZY White dipertahankan saat export ulang dan workbook lama di-backup.
- Dependensi openpyxl==3.1.5 ditambahkan agar fitur Excel ikut dalam portable build.
- Tes baru mencakup MOVE/Undo dan retensi kolom QC Excel.


## Superseding update 2026-11-25 ? MQ1 encrypted-only

The earlier MQ2/signature/allow-list implementation notes below are historical and no longer describe the active protocol. AITQR and ZYBTool now use Metaqr MQ1 encrypted-only. ZYBTool always scans the QR window; with no decoder private key it reports QR_DECRYPT_FAILED after detection, and with the matching private key it reports QR_DECRYPTED after payload/device-ID checks. There is no allow-list, per-staff signing key, signer identity, or replay log. MQ1 does not authenticate the QR creator. Settings now provide decoder key generate/import/export, public-key copy, and removal.

Arrange Folder uses MOVE with hash verification, journal and Undo. Excel Export creates ZY White, Cek File, Scan Audit and Rekonsiliasi and preserves manual QC fields. Hand Check and Preview Frames are explicitly out of scope.
