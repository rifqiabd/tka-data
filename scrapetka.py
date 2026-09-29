import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ALL_BASES = {
    "SMA": "https://pusmendik.kemendikdasmen.go.id/tka/tka/view/mata-pelajaran-wajib/sma",
    "SMP": "https://pusmendik.kemendikdasmen.go.id/tka/tka/view/mata-pelajaran-wajib/smp",
    "SD": "https://pusmendik.kemendikdasmen.go.id/tka/tka/view/mata-pelajaran-wajib/sd",
}
LEVELS = [x.strip().upper() for x in os.environ.get("TKA_LEVELS", "SMA").split(",") if x.strip()]
BASES = {level: ALL_BASES[level] for level in LEVELS if level in ALL_BASES}
if not BASES:
    raise SystemExit("TKA_LEVELS tidak berisi jenjang yang valid")
OUT = os.environ.get("TKA_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "matriks_tka.json")

# The origin serves an incomplete chain: the leaf certificate is issued by an
# intermediate that is not sent, so no public CA bundle can build a path to a
# root ("unable to get local issuer certificate" even with certifi). Verification
# is therefore off unless a usable bundle is supplied, and the choice is recorded
# in the output metadata.
VERIFY_SSL = os.environ.get("TKA_VERIFY_SSL", "").strip().lower() in {"1", "true", "yes"}
CA_BUNDLE = os.environ.get("TKA_CA_BUNDLE", "").strip()

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; TKA-Matrix-Research/1.0; +https://pusmendik.kemendikdasmen.go.id/)"
})
if CA_BUNDLE:
    session.verify = CA_BUNDLE
elif VERIFY_SSL:
    session.verify = True
else:
    session.verify = False
    print("[peringatan] Verifikasi sertifikat dimatikan: rantai sertifikat situs tidak lengkap. "
          "Set TKA_CA_BUNDLE=<ca.pem> atau TKA_VERIFY_SSL=1 untuk mengaktifkannya.")


def clean_text(value):
    if value is None:
        return ""
    text = value.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=[A-Za-zÀ-ÿ])", r"\1 ", text)
    # A few exported Word fragments leave these recurring prefixes separated.
    text = re.sub(r"\bO\s+perasi\b", "Operasi", text)
    text = re.sub(r"\bM\s+e\s+m\s+a\s+hami\b", "Memahami", text)
    text = re.sub(r"\b([B-HJ-Z])\s+([a-zÀ-ÿ]{3,})\b", r"\1\2", text)
    text = text.replace("Su b -elemen", "Subelemen").replace("Su b -ele men", "Subelemen")
    text = text.replace("Elemen/ Mater i", "Elemen/Materi").replace("Mater i", "Materi")
    text = text.replace("Elemen/ Materi", "Elemen/Materi").replace("Subelemen/ Submateri", "Subelemen/Submateri")
    # Collapse character-spaced fragments such as "A l j a bar", "M enganalisis",
    # and "m a n u s i a", while leaving ordinary multi-word phrases untouched.
    patterns = [
        r"\b[A-Z](?:\s+[a-z]){1,}\s+[a-z]{2,}\b",
        r"\b[A-Z]\s+[a-z]{2,}(?:\s+[a-z])\b",
        r"\b(?:[a-z]\s+){2,}[a-z]\b",
        # A leading word plus two or more one-to-two letter tails, e.g. "Elem e n"
        # and "Komp et e n si". The short-tail requirement keeps real phrases such
        # as "Mulai dengan" or "Nama saya" out of the match.
        r"\b[A-Z][a-z]{1,3}(?:\s+[a-z]{1,2}){2,5}\b",
    ]
    for pattern in patterns:
        text = re.sub(pattern, lambda m: re.sub(r"\s+", "", m.group(0)), text)
    return text.strip()


# Header labels exported from Word keep spacing inside the words, and mix
# separator styles. These substitutions are applied to column labels only, so
# they never rewrite prose inside the table body. The lookarounds stop a rule
# from re-matching a word that an earlier rule has already rebuilt.
_SPACED_HEADER_WORDS = [
    (r"(?<![A-Za-z])S\s*u\s*b\s*-?\s*e\s*l\s*e\s*m\s*e\s*n(?![a-z])", "Subelemen"),
    (r"(?<![A-Za-z])S\s*u\s*b\s*k\s*o\s*m\s*p\s*e\s*t\s*e\s*n\s*s\s*i(?![a-z])", "Subkompetensi"),
    (r"(?<![A-Za-z])S\s*u\s*b\s*m\s*a\s*t\s*e\s*r\s*i(?![a-z])", "Submateri"),
    (r"(?<![A-Za-z])E\s*l\s*e\s*m\s*e\s*n(?![a-z])", "Elemen"),
    (r"(?<![A-Za-z])K\s*o\s*m\s*p\s*e\s*t\s*e\s*n\s*s\s*i(?![a-z])", "Kompetensi"),
    (r"(?<![A-Za-z])B\s*a\s*t\s*a\s*s\s*a\s*n(?![a-z])", "Batasan"),
    (r"(?<![A-Za-z])C\s*a\s*t\s*a\s*t\s*a\s*n(?![a-z])", "Catatan"),
]


def normalize_header(value):
    text = clean_text(value)
    if not text:
        return ""
    for pattern, replacement in _SPACED_HEADER_WORDS:
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r"\s*([-/])\s*", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def unique_headers(headers):
    """Disambiguate repeated column labels so no column is lost downstream."""
    seen = {}
    result = []
    for position, header in enumerate(headers, 1):
        name = header or f"kolom_{position}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        result.append(name)
    return result


def visual_text(node):
    """Join letter-spaced Word spans tightly, while preserving real word spaces."""
    if isinstance(node, NavigableString):
        return str(node)
    if isinstance(node, Tag):
        if node.name == "span":
            return "".join(visual_text(child) for child in node.children)
        return " ".join(visual_text(child) for child in node.children)
    return ""


def cell_text(cell):
    # Preserve list items as semicolon-separated text.
    items = [clean_text(visual_text(li)) for li in cell.find_all("li")]
    if items:
        base = clean_text(visual_text(cell))
        for item in items:
            base = base.replace(item, "")
        base = clean_text(base)
        return "; ".join(([base] if base else []) + items)
    return clean_text(visual_text(cell))


def section_text(soup, heading_name):
    heading = None
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if heading_name.lower() in clean_text(tag.get_text(" ", strip=True)).lower():
            heading = tag
            break
    if not heading:
        return ""
    chunks = []
    for node in heading.find_all_next():
        if node is heading:
            continue
        if node.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            break
        if node.name in ["p", "li"]:
            value = clean_text(node.get_text(" ", strip=True))
            if value and value not in chunks:
                chunks.append(value)
    return "\n".join(chunks)


MATRIX_HINTS = ("kompetensi", "elemen", "materi", "subkompetensi", "batasan", "no")


def looks_like_matrix(table):
    """A matrix table always labels a 'Kompetensi' column next to a structural one.

    Pages that publish only example questions ("No Soal | 1") or takikim level
    tables ("Level | Deskripsi Level | ...") must never be mistaken for it.
    """
    rows = table.find_all("tr")
    if not rows:
        return False
    labels = [cell_text(cell).lower() for cell in rows[0].find_all(["th", "td"])]
    joined = " | ".join(labels)
    if "kompetensi" not in joined:
        return False
    return sum(1 for hint in MATRIX_HINTS if hint in joined) >= 2


def find_matrix_table(soup):
    # The official pages place the matrix table immediately after the
    # "Matriks Asesmen" heading, but some pages only publish example-question
    # tables, so every candidate is validated before it is accepted.
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if "matriks asesmen" not in clean_text(heading.get_text(" ", strip=True)).lower():
            continue
        for table in heading.find_all_next("table"):
            if looks_like_matrix(table):
                return table
        break
    for table in soup.find_all("table"):
        if looks_like_matrix(table):
            return table
    return None


def parse_table(table):
    rows = table.find_all("tr")
    if not rows:
        return [], []
    def grid_row(row, occupancy):
        values = []
        col = 0
        for cell in row.find_all(["th", "td"]):
            while col in occupancy:
                values.append(occupancy[col][0])
                occupancy[col][1] -= 1
                if occupancy[col][1] <= 0:
                    del occupancy[col]
                col += 1
            value = cell_text(cell)
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))
            for offset in range(colspan):
                values.append(value)
                if rowspan > 1:
                    occupancy[col + offset] = [value, rowspan - 1]
            col += colspan
        while col in occupancy:
            values.append(occupancy[col][0])
            occupancy[col][1] -= 1
            if occupancy[col][1] <= 0:
                del occupancy[col]
            col += 1
        return values

    occupancy = {}
    header_values = grid_row(rows[0], occupancy)
    headers = unique_headers([normalize_header(x) for x in header_values])
    records = []
    for row in rows[1:]:
        if not row.find_all(["th", "td"]):
            continue
        values = grid_row(row, occupancy)
        if len(values) < len(headers):
            values += [""] * (len(headers) - len(values))
        if len(values) > len(headers):
            values = values[:len(headers)]
        record = {}
        for i, header in enumerate(headers):
            record[header] = values[i] if i < len(values) else ""
        if any(record.values()):
            records.append(record)
    return headers, records


def classify(url):
    return "wajib" if "/mata-pelajaran-wajib/" in url else "pilihan"


def main():
    if session.verify is False:
        requests.packages.urllib3.disable_warnings()
    links = []
    seen = set()
    for jenjang, base in BASES.items():
        index_resp = session.get(base, timeout=40)
        index_resp.raise_for_status()
        index_soup = BeautifulSoup(index_resp.text, "html.parser")
        for a in index_soup.find_all("a", href=True):
            href = urljoin(base, a["href"])
            if not re.search(rf"/tka/tka/view/mata-pelajaran-(wajib|pilihan)/{jenjang.lower()}/[^/]+/?$", href, re.I):
                continue
            href = href.split("#")[0].rstrip("/")
            if href not in seen:
                seen.add(href)
                links.append({"nama": clean_text(a.get_text(" ", strip=True)), "url": href,
                              "kelompok": classify(href), "jenjang": jenjang})

    results = []
    errors = []
    for idx, link in enumerate(links, 1):
        try:
            resp = session.get(link["url"], timeout=40)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else link["nama"]
            table = find_matrix_table(soup)
            headers, records = parse_table(table) if table else ([], [])
            item = {
                "nama": link["nama"],
                "jenjang": link["jenjang"],
                "judul_halaman": title,
                "url": link["url"],
                "kelompok": link["kelompok"],
                "definisi": section_text(soup, "Definisi"),
                "muatan": section_text(soup, "Muatan"),
                "kompetensi": section_text(soup, "Kompetensi"),
                "matriks": {
                    "headers": headers,
                    "rows": records,
                    "jumlah_baris": len(records)
                },
                "status": "ok" if table else "no_matrix_table"
            }
            results.append(item)
            print(f"[{idx}/{len(links)}] OK {link['jenjang']} — {link['nama']} ({len(records)} rows)")
        except Exception as exc:
            errors.append({**link, "error": str(exc)})
            print(f"[{idx}/{len(links)}] ERROR {link['nama']}: {exc}")
        time.sleep(0.15)

    payload = {
        "metadata": {
            "sumber_indeks": list(BASES.values()),
            "jenjang": list(BASES.keys()),
            "tanggal_scraping_utc": datetime.now(timezone.utc).isoformat(),
            "jumlah_tautan_ditemukan": len(links),
            "jumlah_berhasil": len(results),
            "jumlah_error": len(errors),
            "jumlah_tanpa_matriks": sum(1 for item in results if item["status"] != "ok"),
            "tls_verifikasi_sertifikat": session.verify if session.verify is not True else True,
            "catatan": "Data diekstrak dari halaman HTML resmi; teks dibersihkan dari spasi visual antarhuruf dan struktur tabel dipertahankan. Status no_matrix_table berarti halaman tidak memuat tabel matriks (hanya contoh soal/tabel level), sehingga matriks sengaja dikosongkan."
        },
        "mata_pelajaran": results,
        "errors": errors
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Saved {OUT}: {len(results)} subjects, {len(errors)} errors")


if __name__ == "__main__":
    main()
