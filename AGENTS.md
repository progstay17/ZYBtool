# AGENTS.md — ZYB Tool

Instruksi untuk agent coding. Singkat sengaja; detail ada di dokumen lain. **Baca dulu:** `PRD.md` (aturan bisnis, status), `ARCHITECTURE.md` (modul, algoritma). Jangan menurunkan ulang keputusan yang sudah tertulis di sana.

## 1. Status proyek
Fondasi M1/M2 sudah diimplementasikan. Pemilik telah menyetujui implementasi desktop Settings sebagai irisan UI pertama (alur decoder key + allow-list). Lanjutkan hanya pada cakupan yang diminta; tahap M3/M4 dan layar desktop lain tetap nonaktif sampai disetujui.

## 2. Konvensi
- Python (versi di-pin; lihat ARCHITECTURE §11), paket `zybtool`, type hint, dataclass `frozen`.
- Inti = fungsi murni atas dataclass; I/O di tepi. Tanpa state global.
- Identifier dan komentar kode dalam bahasa Inggris; pesan laporan/CLI untuk admin dalam bahasa Indonesia.
- Hasil deterministik: input sama → output sama (urutan stabil, tanpa bergantung urutan filesystem atau nama file).
- Keputusan berbasis bukti dan deterministik; tanpa AI/heuristik tak teruji. Gagal-tertutup: ragu → status lebih rendah atau `AMBIGUOUS`, bukan tebakan.

## 3. Batas modul
- Hanya `cli` yang mengorkestrasi. Modul lain tidak saling memanggil di luar kontrak dataclass/artefak JSON.
- `status` satu-satunya pembuat keputusan status. `qrverify` satu-satunya yang mengimpor Metaqr. `ossup` satu-satunya yang menjalankan `ossutil`.
- Tahap berkomunikasi lewat artefak (`inventory/groups/verification/manifest/report/plan/upload_state`), bukan objek bersama.

## 4. Keamanan
- Jangan membuat ulang kriptografi; pakai Metaqr. Jangan ubah repo Metaqr atau ZYWtool (pakai sebagai dependensi ber-versi).
- Jangan mencetak, mencatat, atau meng-commit: AccessKey/Secret, kunci privat, blob DPAPI, allowlist asli, nama petugas asli. Fixture wajib dianonimkan.
- Kredensial OSS hanya lewat environment proses anak; tidak di argv, disk, atau log. Dilarang `shell=True` dengan input terinterpolasi.
- Validasi path (tanpa traversal, tanpa mengikuti symlink).
- Tidak ada `VERIFIED` dari metadata saja. Level kepercayaan tidak boleh diklaim melebihi ARCHITECTURE §10.

## 5. Keselamatan file dan OSS (aturan keras)
- Input **read-only**. Jangan rename, pindah, hapus, atau ubah file sumber.
- **Jangan pernah rename** `recording_primary_*` atau file/subfolder di dalamnya. Nama operasional hanya untuk folder induk baru.
- Keluaran: salin + verifikasi SHA-256; tulis atomik (`.tmp` lalu rename). Tidak ada sufiks otomatis ` (n)`; bentrok → berhenti dan lapor.
- OSS: hanya `ls`, `stat`, `cp` ke prefix yang disetujui. Dilarang `rm`, `mv`, overwrite, `sync --delete`. Default dry-run; upload butuh persetujuan manusia atas `plan.json` setiap kali. Prefix produksi tidak dipakai di tes.
- Operasi destruktif atau tak dapat dibatalkan (hapus massal, `git push --force`, `reset --hard`) dilarang kecuali diminta eksplisit.

## 6. Jangan berasumsi
Bukan fakta kecuali dibuktikan dari data/inspeksi: struktur OSS selain yang tertulis di ARCHITECTURE §2.4; format kamera = container media; `object_id` unik; PTS container = waktu nyata; urutan segment dari nama file; makna kode site/batch; perilaku multi-segment final; format kamera selain `stereo`. Tandai **[F]/[A]/[?]** di dokumen dan komentar.

## 7. Pengujian (wajib)
- Unit per modul; golden untuk sampel 1 dan 2 (AC-01, AC-02); properti `grouper`; uji kegagalan (putus saat salin/upload); uji kontrak dengan AITQR.
- Tidak ada data operasional atau mkv besar di repo; tes integrasi lokal lewat variabel lingkungan dan penanda `@integration`.
- Tes tidak memakai jaringan atau OSS asli.

## 8. Definition of done
1. Kriteria penerimaan PRD yang relevan lulus dan tertaut ke tes.
2. Semua tes, lint, dan type-check hijau.
3. Tidak ada aturan §4–§5 yang dilanggar; tidak ada secret/data pribadi di diff.
4. Perilaku berubah → `PRD.md`/`ARCHITECTURE.md` diperbarui dalam perubahan yang sama.
5. Diff minimal; dependensi baru hanya dengan alasan tertulis.

## 9. Berhenti dan tanya
Hentikan pekerjaan dan tanyakan bila: bukti saling bertentangan; butuh tindakan destruktif; butuh kredensial; butuh asumsi tentang format/OSS; kriteria penerimaan ambigu; cakupan melebar dari tahap yang disetujui. Laporan akhir: apa yang berubah, tes apa yang dijalankan, apa yang belum terverifikasi.
