# ZYB Tool

Alat desktop lokal/offline untuk memeriksa recording camera project, mendekripsi QR MQ1, mengelompokkan segment berdasarkan bukti, menghasilkan laporan supervisor, dan menyiapkan output lokal. ZYBTool tidak terhubung ke OSS.

## Status implementasi

- **M1 — selesai:** discovery, parser, timeline video, grouping konservatif, status, laporan dan CLI.
- **M2 - QR MQ1 encrypted-only:** Scan selalu mendeteksi QR pada dua crop mata kamera. Jika private key tersedia, ZYBTool mendekripsi payload MQ1 dan memeriksa device ID terhadap session. Tidak ada signing key petugas, allow-list, atau replay log; MQ1 tidak mengautentikasi pembuat QR.
- **Trust:** `QR_DECRYPTED` berarti payload berhasil didekripsi dan lolos korelasi dasar (level 1), bukan bukti identitas pengirim.
- **M3 — fondasi lokal aktif:** Arrange Folder mengikuti grouping ZYWTool dengan template default YYYYMMDD_MMxx_NamaRecorder_ZYxxx_S<shift>_Aktivitas; sesi dengan kunci nama sama berbagi folder grup dan nama folder sesi asli tetap dipertahankan. MOVE mendukung Organized Folder yang sudah berisi grup sebelumnya, verifikasi SHA-256, jurnal Undo per proses, _UNNAMED untuk QR yang belum didekripsi, dan _REJECTED untuk recording CORRUPTED. Excel Export menyediakan sheet ZY White, Cek File, Scan Audit, Rekonsiliasi, serta mempertahankan kolom QC manual.
- **OSS Transfers — dihapus dari scope:** pola nama folder OSS hanya referensi format; tidak ada credential, bucket browser, upload, atau download.

Kontrak field dan pola nama folder untuk AITQR ada di AITQR_INTEGRATION.md. Lihat IMPLEMENTATION_STATUS.md untuk hasil validasi dan dependensi tahap berikutnya.

## Persyaratan

- Windows 10/11 x64
- Python 3.12.15
- PyAV 19.0.2
- Metaqr MQ1 encrypted-only pada commit tetap 4641544f616dcb2758cbedd089521dda9ec87aab (termasuk OpenCV reader)
- pytest 9.2.0, Ruff 0.17.5 dan mypy 2.4.1 untuk pengembangan

## Setup di Windows

Setup membuat virtual environment lokal, memasang PyAV dan Metaqr reader dari commit yang dipatok, dan tidak memerlukan hak administrator.

    powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1

Script mencari Python 3.12.15 pada lokasi instalasi standar pengguna dan instalasi uv. Dependensi dipasang hanya ke .venv.

## Aplikasi desktop

Jalankan workspace desktop tanpa membuka terminal aplikasi:

    .\run-gui.ps1

Workspace memiliki Overview, Verify Recordings, Review Queue, Arrange Folder, Output & Reports, Activity Log, Preferences, dan Settings. Preferences menyediakan JSON Variable Scanner untuk membaca field bertingkat/array, mapping token, template nama folder yang dapat diubah, live preview, dan opsi No Shift (SESSION dihilangkan, tidak pernah ditulis sebagai S0). Verifikasi berjalan di background agar UI tetap responsif; laporan JSON/CSV/HTML ditulis ke folder lokal terpisah. Settings menyediakan generate/import/export private key X25519, copy public key untuk AITQR, dan akses folder penyimpanan lokal. Tidak ada allow-list atau signing key petugas.

### Pengaturan kunci decoder

Alur normal: buka Settings → Generate decoder key → Copy public key → masukkan public key tersebut ke konfigurasi AITQR. **Private key tetap di PC decoder; hanya public key yang diberikan ke AITQR.** Tombol generate dinonaktifkan setelah key tersedia agar aplikasi tidak mengganti pasangan kunci secara tidak sengaja. Private key dapat diekspor secara eksplisit sebagai backup plaintext dengan peringatan keamanan.

Private key disimpan terenkripsi oleh Windows DPAPI untuk akun Windows saat ini. Menghapus key dapat membuat QR lama tidak dapat didekripsi lagi; UI meminta konfirmasi dan menjelaskan dampaknya.

Alternatif CLI tetap tersedia:

    .\run.ps1 settings generate-decoder-key
    .\run.ps1 settings show
    .\run.ps1 settings export-public-key
    .\run.ps1 settings export-private-key "D:\SecureBackup\ZYBTool-decoder-private.key"

Jangan pernah mengirim private decoder key ke AITQR, menyimpan key di repository, atau membagikannya lewat chat/log. Public key AITQR tidak dapat dipakai ZYBTool untuk decrypt; ZYBTool harus mempertahankan private key pasangannya.

## Menjalankan

    .\run.ps1 scan "D:\Recording" --output "D:\ZYB_Reports"

Alternatif langsung:

    .\.venv\Scripts\zybtool.exe scan "D:\Recording" --output "D:\ZYB_Reports"

Scan selalu mencari QR MQ1 pada dua crop mata kamera dari meta.json, mulai dari usable_start_s, default 5 fps selama 30 detik. Jika private key belum tersedia, QR tetap terdeteksi tetapi belum dapat didekripsi. Jika private key tersedia, ZYBTool mendekripsi payload dan memeriksa kecocokan device ID dengan session. Scan tidak memodifikasi recording; MOVE hanya terjadi melalui Arrange yang dikonfirmasi.

## Pengujian

    .\.venv\Scripts\python.exe -m ruff check .
    .\.venv\Scripts\python.exe -m ruff format --check .
    .\.venv\Scripts\python.exe -m mypy src/zybtool
    .\.venv\Scripts\python.exe -m pytest

Tes integrasi sampel operasional bersifat opt-in karena file MKV besar tidak disertakan ke repo:

    $env:ZYB_SAMPLES_DIR = "D:\LocalSamples"
    .\.venv\Scripts\python.exe -m pytest -m integration

## Aturan keselamatan utama

- Scan tidak mengubah sumber. Arrange MOVE memindahkan recording setelah konfirmasi, menyimpan jurnal, dan menyediakan Undo.
- Nama recording_primary_* dan semua isinya tidak pernah di-rename.
- Folder .live_* ikut ditemukan tetapi dinilai INCOMPLETE sampai ada bukti finalisasi.
- Metadata saja tidak pernah menghasilkan QR_DECRYPTED.
- MQ1 hanya memberi kerahasiaan dan dekripsi; tidak membuktikan identitas pengirim QR.
- QR_DECRYPTED memiliki trust level 1; sender tidak diautentikasi dan manifest belum ditandatangani.
- Ambiguitas tidak diselesaikan dengan tebakan.
- ZYBTool tidak mempunyai fitur upload/download atau koneksi OSS. Nama folder OSS hanya referensi konvensi yang field-nya dikonfigurasi pada AITQR.
- Jangan menaruh AccessKey, Secret, private key atau data petugas di repository/log.

Lihat PRD.md, ARCHITECTURE.md, DESIGN.md, AITQR_INTEGRATION.md, dan AGENTS.md untuk kontrak produk.


## Arrange Folder, Preferences, dan Excel Export

Preferences menyediakan folder sumber default, Report output, Excel output, dan Organized Folders. Excel dibuat otomatis sebagai ZYB_Rekap.xlsx; folder tujuan dapat diubah kapan saja tanpa mengubah isi recording. Preview Frames dan Hand Check tidak termasuk scope ZYBTool.

Arrange Folder menggunakan format grup yang sama dengan ZYWTool: YYYYMMDD_MMxx_NamaRecorder_ZYxxx_S<shift>_Aktivitas, misalnya 20261117_MM12_RecorderA_ZY123_S2_Kitchen. Nama komponen dinormalisasi alfanumerik seperti ZYWTool. Recording dengan kunci grup sama digabung ke folder grup yang sama; nama folder sesi asli dan semua subfoldernya tetap dipertahankan. Sesi CORRUPTED masuk _REJECTED; QR yang belum dapat didekripsi masuk _UNNAMED.

Arrange melakukan MOVE, bukan copy. Folder Organized yang sudah berisi grup sebelumnya dapat digunakan kembali; folder sesi yang bentrok tidak akan ditimpa. Sebelum eksekusi, ZYBTool menampilkan preview dan meminta konfirmasi, memeriksa SHA-256, dan menyimpan jurnal per proses untuk Undo. Jangan mematikan PC atau mencabut media selama MOVE berjalan.

Excel Export menghasilkan workbook empat sheet: ZY White, Cek File, Scan Audit, dan Rekonsiliasi. Saat export ulang, kolom QC/status/supervisor manual dipertahankan dan workbook lama dibuatkan backup bertimestamp. Hand Check dan Preview Frames tidak termasuk scope.
