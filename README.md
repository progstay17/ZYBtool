# ZYB Tool

Alat desktop lokal/offline untuk memeriksa recording camera project, mendekripsi QR MQ1, mengelompokkan segment berdasarkan bukti, menghasilkan laporan supervisor, dan menyiapkan output lokal. ZYBTool tidak terhubung ke OSS.

## Status implementasi

- **M1 — selesai:** discovery, parser, timeline video, grouping konservatif, status, laporan dan CLI.
- **M2 - QR MQ1 encrypted-only:** Scan mendeteksi QR pada dua crop mata kamera, mendekripsi dengan private key lokal, dan memvalidasi envelope p=zyb-recording, pv=1, serta session ID. Jika payload menyertakan di dan session.json menyediakan device_id, nilainya harus cocok. Field di bersifat opsional; ketiadaannya bukan warning atau kegagalan.
- **Trust:** `QR_DECRYPTED` berarti payload berhasil didekripsi dan lolos korelasi dasar (level 1), bukan bukti identitas pengirim.
- **M3 — fondasi lokal aktif:** Arrange Folder mengikuti grouping ZYWTool dengan template default `YYYYMMDD_MMxx_NamaRecorder_ZYxxx_S<shift>_Aktivitas`; sesi dengan kunci nama sama berbagi folder grup dan nama folder sesi asli tetap dipertahankan. Preferences memiliki JSON Variable Scanner (Browse/Scan), deteksi nested object/array, field mapping, template editor dan live preview. No Shift menghilangkan token SESSION tanpa menghasilkan `S0`. MOVE tetap memakai verifikasi SHA-256 dan jurnal Undo. Excel Export menyediakan sheet ZY White, Cek File, Scan Audit, Rekonsiliasi, serta mempertahankan kolom QC manual.
- **OSS Transfers — dihapus dari scope:** pola nama folder OSS hanya referensi format; tidak ada credential, bucket browser, upload, atau download.

Kontrak payload AITQR dan mapping nama folder lokal ada di AITQR_INTEGRATION.md. Scanner dapat membaca `session.json` kamera atau JSON contoh payload QR; pemetaan hanya memengaruhi nama folder output. Lihat IMPLEMENTATION_STATUS.md untuk hasil validasi dan dependensi tahap berikutnya.

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

Scan mencari QR MQ1 pada dua crop mata kamera dari meta.json, mulai dari usable_start_s, default 5 fps selama maksimal 5 detik (maksimal 25 frame, dan berhenti lebih awal setelah 3 vote untuk token yang sama). Scanner melakukan seek ke keyframe sebelum titik awal QR dan memakai crop metadata yang sudah dibaca sekali. Jika private key belum tersedia, QR tetap terdeteksi tetapi belum dapat didekripsi. Jika private key tersedia, ZYBTool mendekripsi payload, memvalidasi envelope profil, dan membandingkan di dengan session.json.device_id bila field di tersedia. Ketiadaan di tidak menurunkan status. Recording yang lolos pemeriksaan menjadi VERIFIED. Capture stereo standalone yang formatnya sah tidak diwajibkan memiliki t0.json. Jika gate sinkronisasi standalone gagal tetapi QR dan video valid, hasilnya VERIFIED_WITH_WARNING dan tetap dapat dinamai dengan peringatan tercatat. Scan tidak memodifikasi recording; MOVE hanya terjadi melalui Arrange yang dikonfirmasi.

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
- VERIFIED memiliki trust level 3 saat QR berhasil didekripsi, envelope valid, dan metadata/timeline recording lolos. QR_DECRYPTED tetap menjadi status lapisan QR. MQ1 memang hanya digunakan untuk enkripsi; identitas penerbit bukan syarat penerimaan.
- Ambiguitas tidak diselesaikan dengan tebakan.
- ZYBTool tidak mempunyai fitur upload/download atau koneksi OSS. Nama folder OSS hanya referensi konvensi yang field-nya dikonfigurasi pada AITQR.
- Jangan menaruh AccessKey, Secret, private key atau data petugas di repository/log.

Lihat PRD.md, ARCHITECTURE.md, DESIGN.md, AITQR_INTEGRATION.md, dan AGENTS.md untuk kontrak produk.


## Arrange Folder, Preferences, dan Excel Export

Preferences menyediakan folder sumber default, Report output, Excel output, dan Organized Folders. Excel dibuat otomatis sebagai ZYB_Rekap.xlsx; folder tujuan dapat diubah kapan saja tanpa mengubah isi recording. Preview Frames dan Hand Check tidak termasuk scope ZYBTool.

Arrange Folder menggunakan format grup yang sama dengan ZYWTool: YYYYMMDD_MMxx_NamaRecorder_ZYxxx_S<shift>_Aktivitas, misalnya 20261117_MM12_RecorderA_ZY123_S2_Kitchen. Nama komponen dinormalisasi alfanumerik seperti ZYWTool. Recording dengan kunci grup sama digabung ke folder grup yang sama; nama folder sesi asli dan semua subfoldernya tetap dipertahankan. Sesi CORRUPTED masuk _REJECTED; QR hilang/gagal didekripsi atau payload yang tidak lolos kontrak masuk _UNNAMED. Payload valid pada recording yang lolos pemeriksaan lokal diberi status VERIFIED atau VERIFIED_WITH_WARNING dan dapat diberi nama operasional. QR yang tidak ditemukan tetap masuk _UNNAMED; nama operasional tidak ditebak dari recording lain.

Arrange melakukan MOVE, bukan copy. Folder Organized yang sudah berisi grup sebelumnya dapat digunakan kembali; folder sesi yang bentrok tidak akan ditimpa. Sebelum eksekusi, ZYBTool menampilkan preview dan meminta konfirmasi, memeriksa SHA-256, dan menyimpan jurnal per proses untuk Undo. Jangan mematikan PC atau mencabut media selama MOVE berjalan.

Excel Export menghasilkan workbook empat sheet: ZY White, Cek File, Scan Audit, dan Rekonsiliasi. Saat export ulang, kolom QC/status/supervisor manual dipertahankan dan workbook lama dibuatkan backup bertimestamp. Hand Check dan Preview Frames tidak termasuk scope.


Arrange aman dijalankan ulang pada session.json yang sudah memiliki zybtool.qr_metadata: payload QR yang sama akan memperbarui detail verifikasi, sedangkan payload yang berbeda tetap memicu konflik agar metadata lama tidak tertimpa.


## v0.2.13 ? dukungan kamera stereo standalone

- Format kamera stereo_standalone dikenali sebagai recording final berdasarkan session.json.type, stereo/meta.json (stream=stereo_rgb, mode=standalone), session_sync.json, video, dan data IMU. t0.json memang tidak diwajibkan oleh format ini.
- Tanggal capture diambil dari session.created_iso jika capture_date tidak tersedia.
- Perbedaan durasi standalone diberi toleransi 3 detik. Jika session_sync secara eksplisit gagal, kegagalan gate sinkronisasi dicatat sebagai peringatan; QR valid + video yang dapat dibaca menghasilkan VERIFIED_WITH_WARNING (trust 2) dan tetap bisa di-Arrange. Format recorder lain tetap memakai aturan ketat sebelumnya.
- QR hilang tidak dipalsukan atau dipinjam dari sesi lain; recording tetap _UNNAMED sampai QR yang sesuai tersedia.


## v0.2.15 ? pewarisan QR berdasarkan urutan nama folder

- Folder stereo_standalone diproses menurut nama folder dengan natural sort (mis. ..._2 sebelum ..._10).
- Folder yang memiliki QR terdekripsi memulai kelompok recording baru dan menetapkan identitas QR aktif.
- Folder berikutnya tanpa QR mengikuti QR terakhir sampai ditemukan QR baru.
- Folder sebelum QR pertama tetap tidak teridentifikasi dan tidak boleh meminjam QR dari folder sesudahnya.
- Pengelompokan tidak lagi memakai jeda waktu atau durasi capture.
- Semua folder anggota kelompok dipindahkan bersama dalam satu folder Arrange dan menerima metadata QR kelompok yang sama.

Pemeriksaan timeline video tetap membaca seluruh paket MKV untuk memeriksa urutan PTS dan durasi. Pembatasan 5 detik hanya berlaku untuk pencarian QR; batas ini sengaja tidak mengurangi pemeriksaan integritas seluruh video.

## v0.2.19 — GUI version dan QR scan lebih efisien

- Menyamakan versi package yang dibaca GUI dengan versi release (`0.2.19`).
- QR scanner melakukan seek ke keyframe sebelum `usable_start_s`, sehingga tidak perlu decode semua frame dari awal video ketika QR window dimulai lebih akhir.
- Crop metadata dihitung sekali per scan, bukan membaca dan parsing ulang `meta.json` pada setiap frame sampel.
- Jendela QR tetap maksimal 5 detik pada 5 FPS; pemeriksaan paket MKV penuh tetap dipertahankan.
