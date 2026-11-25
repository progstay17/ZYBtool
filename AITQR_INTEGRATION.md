# AITQR ↔ ZYBTool Integration Contract

Status: draft v1 — shared implementation agreement still requires deterministic vectors from AITQR.

## Product boundary

- AITQR owns the source values and validation used to compose the encrypted payload. ZYBTool Preferences owns the local output folder-name template and field mapping; this does not change the QR schema or AITQR payload.
- AITQR creates an encrypted-only MQ1 QR payload. It receives only the ZYBTool decoder **public** key; MQ1 does not authenticate the sender.
- ZYBTool owns the QR payload schema and verification rules. It stores the matching decoder **private** key locally using Windows DPAPI.
- The private decoder key must never be sent to AITQR, placed in a QR, or committed to either repository.
- ZYBTool has no OSS credentials, bucket browser, listing, upload, download, sync, or transfer functionality.
- Existing OSS folder names are a read-only naming-pattern reference only. AITQR transports metadata in an encrypted-only MQ1 QR payload; ZYBTool decrypts it and uses it only to supplement the camera native session.json, never to replace native metadata.

## Current v1 payload

Schema: `schemas/zyb-recording-v1.schema.json`

| QR field | Meaning | AITQR configuration responsibility | Supplemental session.json role |
|---|---|---|---|
| p | Constant zyb-recording | Fixed | Identifies the QR metadata schema |
| pv | Payload version 1 | Fixed | Schema version |
| s | Unique 16-character Crockford Base32 session ID | Generate once per recording session | Supplemental session correlation |
| r | Recorder/operator label | Configure source field and validation | Recorder metadata |
| dn | Recorder number, format ZY### or ZY#### | Configure and validate | Recorder number metadata |
| di | Stable camera/device identifier | Bind to selected camera/device record | Compare with native session.json device_id; never overwrite it |
| l | Location/site label | Configure source field and allowed values | Supplemental location metadata |
| a | Activity label | Configure source field and allowed values | Supplemental activity metadata |
| sh | Shift number, integer 1 to 3 | Configure shift selection | Supplemental shift metadata |
| b | Branch/site code, format MM## through MM#### | Configure and validate | Supplemental branch/site metadata |

### Metadata enrichment and naming reference

The camera-generated session.json remains the canonical native session document. After QR verification, ZYBTool adds the decrypted MQ1 payload under session.json > zybtool > qr_metadata, preserving every existing native key and value. It must not rewrite the camera's people, device_id, timestamps, or other native fields. The source recording remains read-only; enrichment occurs only in the approved output copy. Existing zybtool.qr_metadata is never overwritten.

Observed OSS folder pattern:

`YYYYMMDD_MM<kode>_<Recorder>_ZY<nnn>_S<n>_<Aktivitas>`

ZYBTool defaults to the same group ordering as ZYWTool: YYYYMMDD_LOCATION_OR_BRANCH_RECORDER_DEVICE_S<SHIFT>_ACTIVITY. Preferences can scan a sample JSON file, map nested fields to the naming tokens, edit token order/separators, preview the result, and enable No Shift to omit SESSION (never `S0`). The default values are date from native `capture_date`, branch/site code (`b`), recorder (`r`), device number (`dn`), shift (`sh`), and activity (`a`); descriptive location (`l`) remains supplemental metadata. AITQR payload short keys are defined by the selected profile and are not guaranteed to be `b/r/dn/sh/a`. Preferences must explicitly map the profile keys to naming tokens (use `qr.<short-key>` for QR fields and `session.<path>` for native metadata). The standard `zyb-recording/v1` keys remain the default mapping. This mapping affects only the output wrapper folder name; it cannot bypass MQ1 decryption or device correlation. Group-name components use ZYWTool's alphanumeric normalization. Recording folders with the same group key share one group folder; original recording folder names and contents remain unchanged. Date is correlated from native recording metadata, never from the workstation clock. Missing or ambiguous required values block automatic naming.

## Key exchange

1. Administrator generates the X25519 decoder keypair in ZYBTool.
2. Administrator copies the public key from ZYBTool Settings into AITQR's decoder configuration.
3. AITQR encrypts the QR payload for that public key using MQ1.
4. ZYBTool decrypts MQ1 with its locally stored X25519 private key. No signer key or allow-list is required.
5. MQ1 does not authenticate the QR creator; ZYBTool labels successful decryption `QR_DECRYPTED` and does not claim sender identity.

## Required shared test vectors before production

AITQR must provide deterministic vectors for:
- valid MQ1 payload with each field at minimum/maximum valid values;
- malformed or missing required fields;
- wrong decoder public key;
- session/device mismatch and timestamp edge cases.

Both repositories must run the same vectors in CI. Until then, ZYBTool's trust level is 1 because MQ1 provides confidentiality but not sender authentication. Folder naming may use the decrypted payload only after native device ID correlation passes.


## Protocol decision 2026-11-25

Use Metaqr MQ1 encrypted-only end-to-end. AITQR requires only the ZYBTool decoder public key; it does not generate staff signing keys or an allow-list. ZYBTool requires the matching decoder private key, which remains local and DPAPI-protected. MQ1 payloads are not proof of who created the QR.
