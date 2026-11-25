# AITQR ↔ ZYBTool Integration Contract

Status: draft v1 — shared implementation agreement still requires deterministic vectors from AITQR.

## Product boundary

- AITQR owns the operator-facing configuration of the fields used to compose an operational folder name.
- AITQR creates and signs the QR payload. It receives only the ZYBTool decoder **public** key.
- ZYBTool owns the QR payload schema and verification rules. It stores the matching decoder **private** key locally using Windows DPAPI.
- The private decoder key must never be sent to AITQR, placed in a QR, or committed to either repository.
- ZYBTool has no OSS credentials, bucket browser, listing, upload, download, sync, or transfer functionality.
- Existing OSS folder names are a read-only naming-pattern reference only. The field values are configured in AITQR and transported in the signed QR payload.

## Current v1 payload

Schema: `schemas/zyb-recording-v1.schema.json`

| QR field | Meaning | AITQR configuration responsibility | Folder-name role |
|---|---|---|---|
| `p` | Constant `zyb-recording` | Fixed | Protocol discriminator |
| `pv` | Payload version `1` | Fixed | Compatibility |
| `s` | Unique 16-character Crockford Base32 session ID | Generate once per recording session | Correlation; not displayed |
| `r` | Recorder/operator label | Configure source field and validation | Recorder component |
| `dn` | Recorder number, format `ZY###` or `ZY####` | Configure and validate | ZY number component |
| `di` | Stable camera/device identifier | Bind to selected camera/device record | Correlation; not displayed |
| `l` | Location/site label | Configure source field and allowed values | Naming metadata; included only according to the agreed final template |
| `a` | Activity label | Configure source field and allowed values | Activity component |
| `sh` | Shift number, integer 1–3 | Configure shift selection | S number component |
| `b` | Branch/site code, format `MM##` through `MM####` | Configure and validate | MM code component |

### Naming reference

Observed reference pattern:

`yyyymmdd_MM<kode>_<Recorder>_ZY<nnn>_S<n>_<Aktivitas>`

The final template and normalization rules must be confirmed jointly before ZYBTool creates operational output folders. Date is correlated from the recording session metadata; it must not be inferred from the workstation clock. A missing or ambiguous required value must stop automatic naming. No automatic ` (2)` suffix, silent normalization, or guessing is allowed.

## Key exchange

1. Administrator generates the X25519 decoder keypair in ZYBTool.
2. Administrator copies the public key from ZYBTool Settings into AITQR's decoder configuration.
3. AITQR encrypts the QR payload for that public key and signs it with its device signing key.
4. ZYBTool decrypts with its locally stored private key and verifies the signature against the imported Metaqr allow-list.
5. Trusted-device pairing/allow-list is optional for normal metadata/video scanning. Without it, QR signature trust is not asserted and results must not be labelled VERIFIED.

## Required shared test vectors before production

AITQR must provide deterministic vectors for:
- valid MQ2 payload with each field at minimum/maximum valid values;
- malformed or missing required fields;
- wrong decoder public key;
- unknown, retired and revoked signing keys;
- replay of the same token in one recording versus a different recording;
- session/device mismatch and timestamp edge cases.

Both repositories must run the same vectors in CI. Until then, ZYBTool's trust level remains capped at level 2 and the final operational folder-name generation must remain gated.
