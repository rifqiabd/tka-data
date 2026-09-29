# Matriks Asesmen TKA

Data matriks asesmen Tes Kemampuan Akademik (TKA) untuk jenjang **SMA, SMP, dan SD**, diekstrak dari halaman resmi [Pusat Mendikdasmen](https://pusmendik.kemendikdasmen.go.id/tka/).

Disediakan sebagai satu berkas JSON statis supaya aplikasi lain bisa mengambilnya langsung lewat URL — tanpa API key, tanpa token, tanpa endpoint yang harus diinstalasi.

## Ambil datanya

Pilih salah satu. Keduanya mengembalikan isi berkas yang sama.

**GitHub Pages** (URL stabil, disarankan):

```
https://rifqiabd.github.io/tka-data/matriks_tka.json
```

**Raw GitHub** (cadangan, tidak bergantung pada status Pages):

```
https://raw.githubusercontent.com/rifqiabd/tka-data/main/matriks_tka.json
```

Keduanya mengirim header `Access-Control-Allow-Origin: *`, jadi bisa langsung dipakai dari browser dengan `fetch()` tanpa proxy.

```bash
curl -sSL https://rifqiabd.github.io/tka-data/matriks_tka.json -o matriks_tka.json
```

```python
import requests

data = requests.get("https://rifqiabd.github.io/tka-data/matriks_tka.json").json()

print(data["metadata"]["tanggal_scraping_utc"])

for mapel in data["mata_pelajaran"]:
    if mapel["status"] != "ok":
        continue
    for baris in mapel["matriks"]["rows"]:
        print(mapel["nama"], "|", baris.get("Kompetensi"))
```

```javascript
const res = await fetch("https://rifqiabd.github.io/tka-data/matriks_tka.json");
const { metadata, mata_pelajaran } = await res.json();

const matematika = mata_pelajaran.find((m) => m.nama === "Matematika");
console.log(matematika.matriks.jumlah_baris, "baris kompetensi");
```

Berkas ini sekitar 660 KB. Untuk halaman web, ambil sekali lalu simpan di cache atau localStorage, jangan memanggilnya di setiap render.

## Struktur data

```jsonc
{
  "metadata": {
    "sumber_indeks": ["https://pusmendik.kemendikdasmen.go.id/..."],
    "jenjang": ["SMA", "SMP", "SD"],
    "tanggal_scraping_utc": "2026-09-29T04:41:12.918374+00:00",
    "jumlah_tautan_ditemukan": 76,
    "jumlah_berhasil": 76,
    "jumlah_error": 0,
    "jumlah_tanpa_matriks": 2,
    "tls_verifikasi_sertifikat": false,
    "catatan": "..."
  },
  "mata_pelajaran": [
    {
      "nama": "Matematika",
      "jenjang": "SMA",
      "judul_halaman": "...",
      "url": "https://pusmendik.kemendikdasmen.go.id/...",
      "kelompok": "wajib",
      "definisi": "...",
      "muatan": "...",
      "kompetensi": "...",
      "matriks": {
        "headers": ["No.", "Elemen/Materi", "Subelemen/Submateri", "Kompetensi", "Batasan/Catatan"],
        "rows": [
          {
            "No.": "1",
            "Elemen/Materi": "Bilangan",
            "Subelemen/Submateri": "...",
            "Kompetensi": "...",
            "Batasan/Catatan": "..."
          }
        ],
        "jumlah_baris": 9
      },
      "status": "ok"
    }
  ],
  "errors": []
}
```

### Hal yang perlu diperhatikan

**`matriks.headers` tidak seragam antar mata pelajaran.** Tiap halaman TKA memakai tabel dengan kolom yang berbeda-beda: sebagian `No. | Elemen/Materi | Subelemen/Submateri | Kompetensi | Batasan/Catatan`, sebagian `No. | Kompetensi | Subkompetensi`, sebagian `Elemen | Sub Elemen | Kompetensi | Batasan/Catatan`. Mengakses `row["Kompetensi"]` langsung akan gagal untuk beberapa mata pelajaran, jadi periksa `headers` lebih dulu atau pakai `.get()` dengan nilai cadangan.

**`status: "no_matrix_table"` berarti datanya kosong, bukan error.** Dua halaman memang tidak memuat tabel matriks di situs: `Kimia` hanya punya tabel level takikim, dan `Bahasa Inggris Tingkat Lanjut` hanya punya tabel contoh soal. `matriks.rows` untuk keduanya adalah `[]`. Scraper sengaja tidak mengisinya dengan tabel lain agar tidak mengarang data.

**Periksa `metadata.tanggal_scraping_utc` sebelum dipakai.** Data di-refresh manual oleh pemilik repo, jadi isinya bisa tertinggal dari perubahan di situs. Lihat bagian [Refresh](#refresh).

**Kolom `url` menyimpan halaman asal.** Kalau butuh data yang lebih mutakhir atau sudah diverifikasi manual, ambil langsung dari `url` tersebut.

## Refresh

Data di-refresh manual, belum ada scraping otomatis. Untuk memperbarui:

```bash
git clone https://github.com/rifqiabd/tka-data.git
cd tka-data
pip install requests beautifulsoup4

# Default hanya SMA. Untuk semua jenjang:
TKA_LEVELS=SMA,SMP,SD python scrapetka.py

git commit -am "refresh data" && git push
```

GitHub Actions mempublish ulang berkasnya ke Pages setiap ada push ke `main`.

### Variabel lingkungan

| Variabel | Default | Keterangan |
|---|---|---|
| `TKA_LEVELS` | `SMA` | Jenjang yang discrape, dipisah koma: `SMA`, `SMP`, `SD` |
| `TKA_OUT` | `matriks_tka.json` di samping skrip | Lokasi keluaran |
| `TKA_VERIFY_SSL` | `0` | Set `1` untuk mengaktifkan verifikasi sertifikat TLS |
| `TKA_CA_BUNDLE` | — | Path ke CA bundle untuk verifikasi sertifikat |

### Catatan soal TLS

Situs `pusmendik.kemendikdasmen.go.id` mengirim rantai sertifikat yang tidak lengkap. Sertifikat leaf diterbitkan oleh intermediate yang tidak disertakan, sehingga tidak ada CA bundle publik yang bisa memverifikasinya (`unable to get local issuer certificate`, bahkan ketika memakai `certifi`). Karena itu `scrapetka.py` berjalan dengan `verify=False` dan mencatat `metadata.tls_verifikasi_sertifikat: false` di keluarannya.

Verifikasi bisa diaktifkan begitu situs memperbaiki rantai sertifikatnya, lewat `TKA_VERIFY_SSL=1` atau `TKA_CA_BUNDLE=/path/ke/ca.pem`. Jangan arahkan `TKA_CA_BUNDLE` ke sertifikat milik situs itu sendiri sebagai jalan pintas, karena itu setara mematikan verifikasi tanpa jejak.

## Sumber

Data ini adalah sadaran dari materi publik pemerintah Republik Indonesia di [pusmendik.kemendikdasmen.go.id](https://pusmendik.kemendikdasmen.go.id/tka/). Tiap entri pada berkas JSON menyimpan `url` halaman asalnya sebagai rujukan.
