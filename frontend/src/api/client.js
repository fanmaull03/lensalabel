// Wrapper fetch ke backend FastAPI.
// Base URL dari VITE_API_BASE_URL (.env), jangan hardcode supaya gampang
// dipindah kalau hosting berubah.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

/**
 * Kirim foto kemasan ke POST /identify, kembalikan hasil klasifikasi.
 *
 * CATATAN: request ini bisa 30 detik - 2 menit (OCR di CPU), bukan bug.
 */
export async function identifyPackage(imageFile) {
  const form = new FormData();
  form.append("file", imageFile);
  return send("/identify", { method: "POST", body: form });
}

/**
 * Kirim teks komposisi yang diketik manual ke POST /identify-manual.
 * Melewati OCR (tidak ada foto), tapi response-nya sama seperti /identify.
 */
export async function identifyManual(text) {
  return send("/identify-manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// Satu tempat penanganan fetch: pesan error sudah siap ditampilkan ke user.
async function send(path, init) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new Error(
      "Tidak bisa terhubung ke server. Pastikan backend LensaLabel sudah berjalan."
    );
  }

  if (!response.ok) {
    // Backend mengirim {"detail": "..."} untuk 400/503. Untuk 422 (validasi
    // Pydantic) detail berupa array, bukan string — abaikan, pakai pesan umum.
    const raw = await response
      .json()
      .then((body) => body.detail)
      .catch(() => null);
    const detail = typeof raw === "string" ? raw : null;

    if (response.status === 400 || response.status === 422) {
      throw new Error(detail ?? "Data tidak bisa diproses. Coba lagi.");
    }
    if (response.status === 503) {
      throw new Error(
        "Server belum siap. Coba lagi beberapa saat, atau hubungi pengelola."
      );
    }
    if (response.status === 413) {
      throw new Error("Foto terlalu besar. Pilih foto berukuran di bawah 10 MB.");
    }
    if (response.status === 429) {
      throw new Error("Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.");
    }
    if (response.status === 504) {
      throw new Error("Waktu pemrosesan habis. Coba lagi dengan foto yang lebih jelas.");
    }
    throw new Error(detail ?? `Terjadi kesalahan di server (kode ${response.status}).`);
  }

  return response.json();
}
