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

Not enabled. It must preserve every recording_primary_* name and byte, write a reviewed plan, copy (never move), verify SHA-256, stop on conflicts and require operator approval. Manifest signing and output/OSS structure decisions must be resolved first.

## M4 — OSS upload

Not enabled and not tested against OSS. Requires an explicitly approved test bucket/prefix and secure child-process credential integration with the existing DPAPI profile. No production prefix has been touched.

## Desktop UI — first Settings slice

Implemented locally:
- A native Windows desktop shell using the Python standard-library Tkinter; no additional GUI package was added.
- Dark graphite / restrained signal-green styling aligned with DESIGN.md.
- Security & Keys page: decoder key state, public key display and clipboard copy, one-time key generation, optional allow-list JSON import, trusted-device count, local storage location and folder access.
- Trusted Devices is explicitly optional: no pairing is required to launch or use ZYBTool. If no allow-list is configured, QR signature checks are skipped while the normal metadata/video verification pipeline continues; no untrusted signer is treated as verified.
- Existing decoder key is never regenerated from the normal UI. The generate action is disabled after setup; key removal requires a warning that old QR may become undecryptable.
- `run-gui.ps1` launches the app without a console window; `zybtool-gui` is also registered as a project entry point.
- The other navigation items are intentionally disabled and are not presented as implemented screens.

Validation on local Windows workstation (2026-11-25):
- Ruff check: passed; Ruff format check: passed.
- mypy: no issues in 15 source modules.
- Latest unit/synthetic suite: 23 passed, 1 optional external-folder integration test skipped (no `ZYB_SAMPLES_DIR` was set for this run).
- Tkinter GUI self-test: passed (Tk 8.6); local settings status read successfully without generating a production decoder key.
- Desktop launch via `run-gui.ps1`: a `ZYBTool` window was observed running from the project environment.
- Regression: decoder key generation and `set_decoder_private_key` both refuse to replace an existing key.
- Latest wheel before public-fixture sanitization: `dist/zybtool-0.1.0-py3-none-any.whl`, 33,481 bytes; verified to contain `zybtool/gui.py` and the `zybtool-gui` console entry point. SHA-256: `f712c8de626b4f459c49bbb35fe1275d1e38664847e210c655650c2755e6f242`.

A standalone portable build is still not delivered.

## Project boundary

- AITQR was treated as a read-only contract dependency and was not modified.
- ZYWtool and Metaqr were not modified.
- The published source history is tracked in the project GitHub repository.
