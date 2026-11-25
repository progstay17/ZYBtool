# AITQR ↔ ZYBTool Integration Contract

Status: draft v1 — shared implementation agreement still requires deterministic vectors from AITQR.

## Product boundary

- AITQR owns the operator-facing configuration of the fields used to compose an operational folder name.
- AITQR creates and signs the QR payload. It receives only the ZYBTool decoder **public** key.
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

The camera-generated session.json remains the canonical native session document. After QR verification, ZYBTool adds the signed payload under session.json > zybtool > qr_metadata, preserving every existing native key and value. It must not rewrite the camera's people, device_id, timestamps, or other native fields. The source recording remains read-only; enrichment occurs only in the approved output copy. Existing zybtool.qr_metadata is never overwritten.

Observed OSS folder pattern:

`yyyymmdd_MM<kode>_<Recorder>_ZY<nnn>_S<n>_<Aktivitas>`

The output wrapper may follow the observed OSS folder pattern, but its values must come from the supplemented session record: native camera metadata plus the decrypted MQ1 metadata stored in that record. The QR is never treated as a replacement session document or a separate metadata source file. Date is correlated from native recording metadata, never from the workstation clock. A missing or ambiguous required value must stop automatic output preparation. No automatic suffix, silent normalization, or guessing is allowed.

## Key exchange

1. Administrator generates the X25519 decoder keypair in ZYBTool.
2. Administrator copies the public key from ZYBTool Settings into AITQR's decoder configuration.
3. AITQR encrypts the QR payload for that public key and signs it with its device signing key.
4. ZYBTool decrypts MQ1 with its locally stored X25519 private key. No signer key or allow-list is required.
5. MQ1 does not authenticate the QR creator; ZYBTool labels successful decryption `QR_DECRYPTED` and does not claim sender identity.

## Required shared test vectors before production

AITQR must provide deterministic vectors for:
- valid MQ1 payload with each field at minimum/maximum valid values;
- malformed or missing required fields;
- wrong decoder public key;
- unknown, retired and revoked signing keys;
- replay of the same token in one recording versus a different recording;
- session/device mismatch and timestamp edge cases.

Both repositories must run the same vectors in CI. Until then, ZYBTool's trust level is 1 because MQ1 provides confidentiality but not sender authentication. Folder naming may use the decrypted payload only after native device ID correlation passes.


## Protocol decision 2026-11-25

Use Metaqr MQ1 encrypted-only end-to-end. AITQR requires only the ZYBTool decoder public key; it does not generate staff signing keys or an allow-list. ZYBTool requires the matching decoder private key, which remains local and DPAPI-protected. MQ1 payloads are not proof of who created the QR.
