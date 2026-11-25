# ZYB Tool

Alat lokal/offline untuk memeriksa recording camera project, mengelompokkan segment berdasarkan bukti, menghasilkan laporan supervisor, menyiapkan salinan terverifikasi, dan pada tahap berikutnya mengunggahnya secara aman ke OSS.

## Status implementasi

- **M1 — selesai:** discovery, parser, timeline video, grouping konservatif, status, laporan dan CLI.
- **M2 — fondasi QR/MQ2 terintegrasi:** Metaqr 0.4.0 dipatok ke commit tetap; pemindaian dua crop mata kamera, verifikasi MQ2, allow-list, replay log, serta penyimpanan private key dengan Windows DPAPI.
- **M2 — belum final:** vektor kontrak final AITQR dan pengujian kamera nyata masih diperlukan. Trust dibatasi maksimum level 2 sampai seluruh korelasi session/kamera/waktu teruji.
- **M3 — belum diaktifkan:** output copy memerlukan plan, approval, integritas/hash dan manifest yang sah.
- **M4 — belum diaktifkan:** OSS memerlukan prefix uji yang disetujui dan integrasi kredensial DPAPI.

Lihat IMPLEMENTATION_STATUS.md untuk hasil validasi dan dependensi tahap berikutnya.

## Persyaratan

- Windows 10/11 x64
- Python 3.12.15
- PyAV 19.0.2
- Metaqr pada commit tetap baae37471201b3ae3477d0cf0dcb8ffd26e4dc76 (termasuk OpenCV reader)
- pytest 9.2.0, Ruff 0.17.5 dan mypy 2.4.1 untuk pengembangan

## Setup di Windows

Setup membuat virtual environment lokal, memasang PyAV dan Metaqr reader dari commit yang dipatok, dan tidak memerlukan hak administrator.

    powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1

Script mencari Python 3.12.15 pada lokasi instalasi standar pengguna dan instalasi uv. Dependensi dipasang hanya ke .venv.

## Aplikasi desktop

Jalankan halaman Settings tanpa membuka terminal aplikasi:

    .\run-gui.ps1

Desktop UI pertama berfokus pada **Security & Keys**. Halaman ini menyediakan status decoder key, generate pasangan X25519, copy public key untuk AITQR, impor allow-list perangkat secara opsional, dan akses ke folder penyimpanan lokal. Trusted Devices tidak wajib untuk membuka atau menjalankan ZYBTool; tanpa allow-list, pemeriksaan metadata/video tetap berjalan tetapi tanda tangan perangkat tidak dianggap tepercaya. Navigasi layar lain masih bertahap dan belum diaktifkan.

### Pengaturan kunci decoder

Alur normal: buka Settings → Generate decoder key → Copy public key → masukkan public key tersebut ke konfigurasi AITQR. **Private key tetap di PC decoder; hanya public key yang diberikan ke AITQR.** Tombol generate dinonaktifkan setelah key tersedia agar aplikasi tidak mengganti pasangan kunci secara tidak sengaja.

Private key disimpan terenkripsi oleh Windows DPAPI untuk akun Windows saat ini. Menghapus key dapat membuat QR lama tidak dapat didekripsi lagi; UI meminta konfirmasi dan menjelaskan dampaknya.

Alternatif CLI tetap tersedia:

    .\run.ps1 settings generate-decoder-key
    .\run.ps1 settings import-allowlist "D:\AITQR\allowlist.json"
    .\run.ps1 settings show
    .\run.ps1 settings export-public-key

Jangan pernah mengirim private decoder key ke AITQR, menyimpan key di repository, atau membagikannya lewat chat/log. Public key AITQR tidak dapat dipakai ZYBTool untuk decrypt; ZYBTool harus mempertahankan private key pasangannya.

## Menjalankan

    .\run.ps1 scan "D:\Recording" --output "D:\ZYB_Reports"

Alternatif langsung:

    .\.venv\Scripts\zybtool.exe scan "D:\Recording" --output "D:\ZYB_Reports"

Jika decoder key dan allow-list telah disiapkan, scan juga akan mencari dan memverifikasi MQ2 pada dua crop mata kamera dari meta.json, mulai dari usable_start_s, default 5 fps selama 30 detik. Jika allow-list belum tersedia, pemindaian/verifikasi tanda tangan QR dilewati tanpa menghentikan pemeriksaan metadata dan video. Sumber recording selalu read-only. Replay log disimpan di profil lokal pengguna Windows.

## Pengujian

    .\.venv\Scripts\python.exe -m ruff check .
    .\.venv\Scripts\python.exe -m ruff format --check .
    .\.venv\Scripts\python.exe -m mypy src/zybtool
    .\.venv\Scripts\python.exe -m pytest

Tes integrasi sampel operasional bersifat opt-in karena file MKV besar tidak disertakan ke repo:

    $env:ZYB_SAMPLES_DIR = "D:\LocalSamples"
    .\.venv\Scripts\python.exe -m pytest -m integration

## Aturan keselamatan utama

- Folder sumber tidak pernah diubah.
- Nama recording_primary_* dan semua isinya tidak pernah di-rename.
- Folder .live_* ikut ditemukan tetapi dinilai INCOMPLETE sampai ada bukti finalisasi.
- Metadata saja tidak pernah menghasilkan VERIFIED.
- MQ1 tidak diterima sebagai bukti identitas; mode verifikasi membutuhkan MQ2 + allow-list.
- QR valid saat ini menaikkan trust sampai level 2, bukan level 3/4; korelasi session dan manifest masih menunggu tes kontrak.
- Ambiguitas tidak diselesaikan dengan tebakan.
- Upload tetap nonaktif sampai plan, persetujuan operator, prefix uji dan pemeriksaan overwrite tersedia.
- Jangan menaruh AccessKey, Secret, private key, allow-list asli atau data petugas di repository/log.

Lihat PRD.md, ARCHITECTURE.md, DESIGN.md, dan AGENTS.md untuk kontrak produk.
