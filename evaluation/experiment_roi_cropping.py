"""Eksperimen ROI Cropping — Two-Pass OCR untuk mempercepat pipeline.

Pass 1 (lokalisasi cepat): EasyOCR di resolusi rendah (~800px lebar) untuk
menemukan bounding box marker "KOMPOSISI"/"COMPOSITION"/"INGREDIENTS".

Pass 2 (ekstraksi akurat): Crop area komposisi dari gambar resolusi penuh
(dengan padding besar), lalu jalankan preprocessing + EasyOCR seperti biasa.

Safety net: Kalau pass 1 gagal menemukan marker, fallback ke pipeline lama
(full-frame OCR).

TIDAK mengubah dataset, pipeline production, atau file lain. Murni eksperimen.

Cara pakai (dari root folder project):
  python evaluation/experiment_roi_cropping.py
"""

import sys
import time
from pathlib import Path

# Set console encoding to UTF-8 to prevent Windows CP1252 charmap errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np
from rapidfuzz import fuzz

# --- Path setup --------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.preprocessing.pipeline import (  # noqa: E402
    to_grayscale,
    reduce_noise,
    enhance_contrast,
    deskew,
)
from app.ocr.reader import (  # noqa: E402
    get_reader,
    _downscale,
    sort_reading_order,
    MAX_OCR_WIDTH,
)
from app.tokenizer.tokenizer import (  # noqa: E402
    extract_composition_section,
    tokenize,
    OPEN_MARKERS,
    MARKER_THRESHOLD,
)

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
RAW_PHOTOS_DIR = DATASET_DIR / "raw_photos"

# --- Knob eksperimen ---------------------------------------------------------
PASS1_MAX_WIDTH = 800     # resolusi rendah untuk lokalisasi marker
PASS2_MAX_WIDTH = 2000    # resolusi normal untuk ekstraksi akurat (sama seperti pipeline lama)
MARKER_FUZZY_THRESHOLD = 65  # sedikit lebih rendah dari tokenizer (70) karena resolusi rendah
PAD_HORIZONTAL = 0.40     # padding horizontal 40% dari lebar crop ke tiap sisi
PAD_TOP = 0.40            # padding atas 40% dari tinggi bbox marker
PAD_BOTTOM_MIN_FRAC = 0.55  # minimal 55% tinggi gambar ke bawah dari marker

SAMPLE_PHOTOS: list[tuple[str, str]] = [
    ("datar", "datar_001.jpeg"),
    ("datar", "datar_010.jpeg"),
    ("datar", "datar_025.jpeg"),
    ("datar", "datar_050.jpeg"),
    ("datar", "datar_075.jpeg"),
    ("melengkung", "melengkung_001.jpeg"),
    ("melengkung", "melengkung_025.jpeg"),
    ("melengkung", "melengkung_050.jpeg"),
    ("melengkung", "melengkung_099.jpeg"),
    ("melengkung", "melengkung_100.jpeg"),
]


def _measure(fn, *args, **kwargs):
    """Jalankan fn, kembalikan (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0


def preprocess(image: np.ndarray) -> np.ndarray:
    """Jalankan 4 tahap preprocessing sesuai proposal."""
    gray = to_grayscale(image)
    blurred = reduce_noise(gray)
    contrast = enhance_contrast(blurred)
    return deskew(contrast)


def find_marker_bbox(
    ocr_results: list,
    markers: tuple[str, ...] = OPEN_MARKERS,
    threshold: float = MARKER_FUZZY_THRESHOLD,
) -> tuple[list | None, str | None, float]:
    """Cari bounding box yang teksnya paling cocok dengan salah satu marker.

    Mengembalikan (bbox, matched_text, best_score). bbox = None kalau tidak ada
    yang cocok di atas threshold.

    Setiap deteksi OCR bisa berupa satu kata atau beberapa kata. Kita cek
    masing-masing deteksi secara individu DAN gabungan 2-3 deteksi berturutan
    (karena marker bisa terpecah jadi beberapa bounding box oleh EasyOCR).
    """
    best_bbox, best_text, best_score = None, None, 0.0

    # Cek per deteksi individu
    for bbox, text, _conf in ocr_results:
        for marker in markers:
            score = fuzz.ratio(text.upper(), marker)
            if score > best_score:
                best_bbox, best_text, best_score = bbox, text, score

    # Cek gabungan 2-3 deteksi berturutan (marker terpecah)
    for window_size in (2, 3):
        for i in range(len(ocr_results) - window_size + 1):
            combined_text = " ".join(ocr_results[j][1] for j in range(i, i + window_size))
            # Gabungkan bbox: ambil bounding box terluar
            all_points = []
            for j in range(i, i + window_size):
                all_points.extend(ocr_results[j][0])
            xs = [p[0] for p in all_points]
            ys = [p[1] for p in all_points]
            combined_bbox = [
                [min(xs), min(ys)],
                [max(xs), min(ys)],
                [max(xs), max(ys)],
                [min(xs), max(ys)],
            ]
            for marker in markers:
                score = fuzz.ratio(combined_text.upper(), marker)
                if score > best_score:
                    best_bbox, best_text, best_score = combined_bbox, combined_text, score

    if best_score >= threshold:
        return best_bbox, best_text, best_score
    return None, best_text, best_score


def compute_crop_region(
    marker_bbox: list,
    scale_factor: float,
    orig_h: int,
    orig_w: int,
) -> tuple[int, int, int, int]:
    """Hitung crop region di koordinat gambar asli dari bbox pass-1.

    Mengembalikan (y_start, y_end, x_start, x_end) yang sudah di-clamp ke
    batas gambar asli.

    Strategi padding:
    - Horizontal: 35% lebar bbox ke kedua sisi (cukup untuk label melengkung
      yang teksnya bisa lebih lebar dari yang terdeteksi di low-res)
    - Atas: 15% tinggi bbox (sedikit ruang untuk header "Komposisi:" sendiri)
    - Bawah: minimal 60% tinggi gambar dari titik marker KE BAWAH, karena
      daftar komposisi bisa sangat panjang dan posisi marker biasanya di atas
    """
    # Koordinat bbox dalam skala pass-1 (low-res)
    xs = [p[0] for p in marker_bbox]
    ys = [p[1] for p in marker_bbox]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    bbox_w = x_max - x_min
    bbox_h = y_max - y_min

    # Mapping balik ke resolusi asli
    x_min_orig = x_min * scale_factor
    x_max_orig = x_max * scale_factor
    y_min_orig = y_min * scale_factor
    bbox_w_orig = bbox_w * scale_factor
    bbox_h_orig = bbox_h * scale_factor

    # Padding horizontal
    pad_x = bbox_w_orig * PAD_HORIZONTAL
    x_start = int(max(0, x_min_orig - pad_x))
    x_end = int(min(orig_w, x_max_orig + pad_x))

    # Pastikan crop minimal selebar 85% gambar (komposisi sering full-width)
    crop_w = x_end - x_start
    min_crop_w = int(orig_w * 0.85)
    if crop_w < min_crop_w:
        center_x = (x_start + x_end) // 2
        x_start = max(0, center_x - min_crop_w // 2)
        x_end = min(orig_w, x_start + min_crop_w)
        if x_end - x_start < min_crop_w:
            x_start = max(0, x_end - min_crop_w)

    # Padding vertikal: atas sedikit margin aman, bawah mencakup daftar bahan
    pad_top = max(bbox_h_orig * PAD_TOP, orig_h * 0.03)
    y_start = int(max(0, y_min_orig - pad_top))

    # Bawah: minimal 55% tinggi gambar dari posisi marker
    y_end_min = int(y_min_orig + orig_h * PAD_BOTTOM_MIN_FRAC)
    y_end = int(min(orig_h, y_end_min))

    return y_start, y_end, x_start, x_end


def run_full_frame(image: np.ndarray, reader) -> tuple[str, float, int]:
    """Pipeline lama: preprocess full → downscale → OCR. Return (text, time, n_regions)."""
    t0 = time.perf_counter()
    processed = preprocess(image)
    downscaled = _downscale(processed, MAX_OCR_WIDTH)
    results = reader.readtext(downscaled, detail=1)
    ordered = sort_reading_order(results)
    text = "\n".join(t for _, t, _ in ordered)
    elapsed = time.perf_counter() - t0
    return text, elapsed, len(results)


def run_two_pass(image: np.ndarray, reader) -> dict:
    """Two-pass ROI cropping (Opsi A: Preprocess full-frame sekali di awal).

    Langkah:
    1. Preprocess citra utuh sekali saja (grayscale -> blur -> CLAHE -> deskew).
       Biaya waktu hanya ~0.06 detik, tapi menjamin sudut rotasi & koordinat
       100% konsisten antara Pass 1, Pass 2, dan pipeline lama.
    2. Pass 1: Downscale preprocessed ke 800px untuk lokalisasi marker.
    3. Hitung ROI crop pada koordinat preprocessed.
    4. Pass 2: Crop langsung dari citra preprocessed (tanpa re-preprocess),
       downscale ke batas max width jika perlu, lalu jalankan OCR akurat.
    5. Fallback: Jika marker tidak ditemukan, jalankan OCR pada seluruh
       citra preprocessed.
    """
    orig_h, orig_w = image.shape[:2]
    info: dict = {
        "orig_resolution": f"{orig_w}x{orig_h}",
        "marker_found": False,
        "marker_text": None,
        "marker_score": 0.0,
        "fallback": False,
    }

    # ── TAHAP 0: Preprocessing full-frame sekali (Opsi A) ────────────────
    t0_prep = time.perf_counter()
    preprocessed_full = preprocess(image)
    t_prep = time.perf_counter() - t0_prep
    info["preprocess_time"] = t_prep

    # ── PASS 1: lokalisasi marker di low-res ─────────────────────────────
    t0_pass1 = time.perf_counter()

    scale_factor = orig_w / PASS1_MAX_WIDTH
    low_res = _downscale(preprocessed_full, PASS1_MAX_WIDTH)

    # OCR pass 1
    results_p1 = reader.readtext(low_res, detail=1)
    t_pass1 = time.perf_counter() - t0_pass1

    info["pass1_time"] = t_prep + t_pass1
    info["pass1_n_regions"] = len(results_p1)
    info["pass1_resolution"] = f"{low_res.shape[1]}x{low_res.shape[0]}"

    # Cari marker
    marker_bbox, marker_text, marker_score = find_marker_bbox(results_p1)
    info["marker_text"] = marker_text
    info["marker_score"] = marker_score

    if marker_bbox is None:
        # FALLBACK: marker tidak ditemukan, jalankan OCR full-frame
        info["fallback"] = True
        info["fallback_reason"] = f"Marker score terbaik {marker_score:.0f} < threshold {MARKER_FUZZY_THRESHOLD}"
        t0_fb = time.perf_counter()
        downscaled = _downscale(preprocessed_full, PASS2_MAX_WIDTH)
        results_fb = reader.readtext(downscaled, detail=1)
        ordered = sort_reading_order(results_fb)
        text = "\n".join(t for _, t, _ in ordered)
        t_fb = time.perf_counter() - t0_fb
        info["pass2_time"] = t_fb
        info["total_time"] = info["pass1_time"] + t_fb
        info["text"] = text
        info["pass2_n_regions"] = len(results_fb)
        info["crop_resolution"] = info["orig_resolution"]  # no crop
        return info

    info["marker_found"] = True

    # ── PASS 2: crop langsung dari preprocessed_full + OCR akurat ────────
    t0_pass2 = time.perf_counter()

    y1, y2, x1, x2 = compute_crop_region(marker_bbox, scale_factor, orig_h, orig_w)
    cropped = preprocessed_full[y1:y2, x1:x2]
    info["crop_region"] = f"y[{y1}:{y2}] x[{x1}:{x2}]"
    info["crop_resolution"] = f"{cropped.shape[1]}x{cropped.shape[0]}"
    info["crop_area_pct"] = round(
        (cropped.shape[0] * cropped.shape[1]) / (orig_h * orig_w) * 100, 1
    )

    # Downscale crop jika lebarnya masih melebihi PASS2_MAX_WIDTH
    downscaled = _downscale(cropped, PASS2_MAX_WIDTH)
    info["pass2_ocr_resolution"] = f"{downscaled.shape[1]}x{downscaled.shape[0]}"

    # OCR pass 2 (tidak perlu preprocess ulang karena cropped sudah preprocessed)
    results_p2 = reader.readtext(downscaled, detail=1)
    ordered = sort_reading_order(results_p2)
    text = "\n".join(t for _, t, _ in ordered)
    t_pass2 = time.perf_counter() - t0_pass2

    info["pass2_time"] = t_pass2
    info["pass2_n_regions"] = len(results_p2)
    info["total_time"] = info["pass1_time"] + t_pass2
    info["text"] = text
    return info


def text_similarity_report(text_old: str, text_new: str) -> dict:
    """Bandingkan dua teks OCR: apakah konten komposisi sama/setara."""
    section_old = extract_composition_section(text_old)
    section_new = extract_composition_section(text_new)

    tokens_old = set(t.lower() for t in tokenize(section_old))
    tokens_new = set(t.lower() for t in tokenize(section_new))

    char_sim = fuzz.ratio(section_old.strip(), section_new.strip())

    if not tokens_old and not tokens_new:
        return {
            "match": True,
            "note": "Keduanya kosong",
            "jaccard": 1.0,
            "char_sim": 100.0,
            "fuzzy_overlap": 1.0,
            "n_tokens_old": 0,
            "n_tokens_new": 0,
            "n_shared": 0,
            "missing": [],
            "extra": [],
        }

    intersection = tokens_old & tokens_new
    union = tokens_old | tokens_new
    jaccard = len(intersection) / len(union) if union else 1.0

    # Fuzzy match: hitung token lama yang punya padanan (skor >= 75) di token baru
    fuzzy_matched = 0
    for to in tokens_old:
        if any(fuzz.ratio(to, tn) >= 75 or fuzz.partial_ratio(to, tn) >= 85 for tn in tokens_new):
            fuzzy_matched += 1
    fuzzy_rate = fuzzy_matched / len(tokens_old) if tokens_old else 1.0

    missing = tokens_old - tokens_new
    extra = tokens_new - tokens_old

    return {
        "match": (jaccard >= 0.7 or (fuzzy_rate >= 0.75 and char_sim >= 70)),
        "jaccard": round(jaccard, 3),
        "char_sim": round(char_sim, 1),
        "fuzzy_overlap": round(fuzzy_rate, 3),
        "n_tokens_old": len(tokens_old),
        "n_tokens_new": len(tokens_new),
        "n_shared": len(intersection),
        "missing": sorted(missing)[:5] if missing else [],
        "extra": sorted(extra)[:5] if extra else [],
    }


def main():
    print("=" * 80)
    print("EKSPERIMEN ROI CROPPING — Two-Pass OCR")
    print(f"Pass 1: lokalisasi marker @ {PASS1_MAX_WIDTH}px lebar")
    print(f"Pass 2: OCR akurat @ {PASS2_MAX_WIDTH}px pada area crop")
    print(f"Fallback: full-frame kalau marker tidak ditemukan")
    print("=" * 80)

    # Validasi
    missing = []
    for cat, fname in SAMPLE_PHOTOS:
        if not (RAW_PHOTOS_DIR / cat / fname).exists():
            missing.append(f"{cat}/{fname}")
    if missing:
        print("ERROR: file tidak ditemukan:", missing)
        sys.exit(1)

    # Load model
    print("\nMemuat model EasyOCR (one-time)...")
    t0 = time.perf_counter()
    reader = get_reader()
    print(f"Model dimuat dalam {time.perf_counter() - t0:.1f} detik.\n")

    results = []

    for i, (category, filename) in enumerate(SAMPLE_PHOTOS, 1):
        photo_path = RAW_PHOTOS_DIR / category / filename
        print(f"\n{'='*80}")
        print(f"[{i}/{len(SAMPLE_PHOTOS)}] {category}/{filename}")
        print(f"{'='*80}")

        image = cv2.imread(str(photo_path))
        if image is None:
            print("  GAGAL membaca gambar!")
            continue

        # --- Pipeline lama (full-frame, baseline) ---
        print("  Pipeline LAMA (full-frame)...")
        text_old, time_old, n_regions_old = run_full_frame(image, reader)
        print(f"    Waktu: {time_old:.1f}s  |  #region: {n_regions_old}")

        # --- Two-pass ROI cropping ---
        print("  Pipeline BARU (two-pass ROI)...")
        roi_info = run_two_pass(image, reader)

        if roi_info["fallback"]:
            print(f"    FALLBACK: {roi_info['fallback_reason']}")
            print(f"    Pass 1: {roi_info['pass1_time']:.1f}s  |  "
                  f"Pass 2 (full): {roi_info['pass2_time']:.1f}s  |  "
                  f"Total: {roi_info['total_time']:.1f}s")
        else:
            print(f"    Marker ditemukan: \"{roi_info['marker_text']}\" "
                  f"(score={roi_info['marker_score']:.0f})")
            print(f"    Pass 1 ({roi_info['pass1_resolution']}): "
                  f"{roi_info['pass1_time']:.1f}s  ({roi_info['pass1_n_regions']} regions)")
            print(f"    Crop: {roi_info['crop_resolution']} "
                  f"({roi_info['crop_area_pct']}% area asli)")
            print(f"    Pass 2 OCR res: {roi_info.get('pass2_ocr_resolution', 'N/A')}  |  "
                  f"{roi_info['pass2_time']:.1f}s  ({roi_info['pass2_n_regions']} regions)")
            print(f"    Total: {roi_info['total_time']:.1f}s")

        # --- Perbandingan teks ---
        sim = text_similarity_report(text_old, roi_info.get("text", ""))
        speedup = time_old / roi_info["total_time"] if roi_info["total_time"] > 0 else 0

        print(f"\n  PERBANDINGAN:")
        print(f"    Waktu lama: {time_old:.1f}s  -->  Waktu baru: {roi_info['total_time']:.1f}s  "
              f"(speedup: {speedup:.2f}x)")
        print(f"    Token overlap (Jaccard): {sim.get('jaccard', 'N/A')}  "
              f"({sim['n_tokens_old']} old, {sim['n_tokens_new']} new, "
              f"{sim['n_shared']} shared)")
        if sim.get("missing"):
            print(f"    Token HILANG di baru: {sim['missing']}")
        if sim.get("extra"):
            print(f"    Token TAMBAHAN di baru: {sim['extra']}")
        print(f"    Konsisten: {'[v] YA' if sim['match'] else '[x] TIDAK'}")

        results.append({
            "photo": filename,
            "category": category,
            "time_old": time_old,
            "time_new": roi_info["total_time"],
            "pass1_time": roi_info["pass1_time"],
            "pass2_time": roi_info.get("pass2_time", 0),
            "speedup": speedup,
            "marker_found": roi_info["marker_found"],
            "marker_text": roi_info.get("marker_text"),
            "marker_score": roi_info.get("marker_score", 0),
            "fallback": roi_info["fallback"],
            "crop_area_pct": roi_info.get("crop_area_pct", 100),
            "jaccard": sim.get("jaccard", 0),
            "fuzzy_overlap": sim.get("fuzzy_overlap", 0),
            "char_sim": sim.get("char_sim", 0),
            "consistent": sim["match"],
            "n_regions_old": n_regions_old,
            "n_regions_new": roi_info.get("pass2_n_regions", 0),
        })

    # --- RINGKASAN AKHIR ---
    print("\n\n" + "=" * 110)
    print("RINGKASAN HASIL EKSPERIMEN ROI CROPPING (OPSI A)")
    print("=" * 110)

    header = (
        f"{'Foto':<22}"
        f"  {'Lama(s)':>7}"
        f"  {'P1(s)':>6}"
        f"  {'P2(s)':>6}"
        f"  {'Baru(s)':>7}"
        f"  {'Speedup':>7}"
        f"  {'Marker':>8}"
        f"  {'Crop%':>6}"
        f"  {'Jaccard':>7}"
        f"  {'Fuzzy%':>7}"
        f"  {'Char%':>6}"
        f"  {'OK?':>4}"
    )
    print(header)
    print("-" * len(header))

    for r in results:
        marker_status = "[v]" if r["marker_found"] else "FALLBACK"
        ok = "[v]" if r["consistent"] else "[x]"
        print(
            f"{r['photo']:<22}"
            f"  {r['time_old']:>7.1f}"
            f"  {r['pass1_time']:>6.1f}"
            f"  {r['pass2_time']:>6.1f}"
            f"  {r['time_new']:>7.1f}"
            f"  {r['speedup']:>6.2f}x"
            f"  {marker_status:>8}"
            f"  {r['crop_area_pct']:>5.1f}%"
            f"  {r['jaccard']:>7.3f}"
            f"  {r['fuzzy_overlap']*100:>6.1f}%"
            f"  {r['char_sim']:>5.1f}%"
            f"  {ok:>4}"
        )

    # Statistik
    valid = [r for r in results if not r["fallback"]]
    fallbacks = [r for r in results if r["fallback"]]
    consistent = [r for r in results if r["consistent"]]

    print(f"\n--- STATISTIK ---")
    print(f"  Total foto            : {len(results)}")
    print(f"  Marker ditemukan      : {len(valid)}/{len(results)}")
    print(f"  Fallback (full-frame) : {len(fallbacks)}/{len(results)}")
    print(f"  Konsisten Teks        : {len(consistent)}/{len(results)}")

    if valid:
        avg_speedup = sum(r["speedup"] for r in valid) / len(valid)
        avg_old = sum(r["time_old"] for r in valid) / len(valid)
        avg_new = sum(r["time_new"] for r in valid) / len(valid)
        avg_crop = sum(r["crop_area_pct"] for r in valid) / len(valid)
        avg_jaccard = sum(r["jaccard"] for r in valid) / len(valid)
        avg_fuzzy = sum(r["fuzzy_overlap"] for r in valid) / len(valid) * 100
        avg_char = sum(r["char_sim"] for r in valid) / len(valid)
        print(f"\n  Untuk {len(valid)} foto yang di-crop:")
        print(f"    Rata-rata waktu lama  : {avg_old:.1f}s")
        print(f"    Rata-rata waktu baru  : {avg_new:.1f}s")
        print(f"    Rata-rata speedup     : {avg_speedup:.2f}x")
        print(f"    Rata-rata area crop   : {avg_crop:.1f}%")
        print(f"    Rata-rata Jaccard     : {avg_jaccard:.3f}")
        print(f"    Rata-rata Fuzzy Match : {avg_fuzzy:.1f}%")
        print(f"    Rata-rata Char Sim    : {avg_char:.1f}%")
        print(f"    Target <30s tercapai  : "
              f"{sum(1 for r in valid if r['time_new'] < 30)}/{len(valid)} foto")

    if fallbacks:
        avg_fb = sum(r["time_new"] for r in fallbacks) / len(fallbacks)
        print(f"\n  Untuk {len(fallbacks)} foto fallback:")
        print(f"    Rata-rata waktu total : {avg_fb:.1f}s (pass1 + full-frame)")

    print(f"\nSelesai. Tidak ada file pipeline yang diubah.\n")


if __name__ == "__main__":
    main()
