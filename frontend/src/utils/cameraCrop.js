export function cameraCrop(videoSize, videoRect, guideRect) {
  const scale = Math.max(
    videoRect.width / videoSize.width,
    videoRect.height / videoSize.height,
  );
  const shownWidth = videoSize.width * scale;
  const shownHeight = videoSize.height * scale;
  const left = (shownWidth - videoRect.width) / 2;
  const top = (shownHeight - videoRect.height) / 2;
  const rawX = (guideRect.left - videoRect.left + left) / scale;
  const rawY = (guideRect.top - videoRect.top + top) / scale;
  const rawW = guideRect.width / scale;
  const rawH = guideRect.height / scale;
  // Clamp kedua ujung: kalau area panduan keluar dari sisi kiri/atas frame
  // (mis. viewport ponsel landscape yang pendek), width/height harus ikut
  // menyusut sebesar bagian yang terpotong. Tanpa ini sx + sw > videoWidth
  // dan drawImage melempar IndexSizeError (shutter mati tanpa pesan).
  const x = Math.max(0, Math.round(rawX));
  const y = Math.max(0, Math.round(rawY));
  const right = Math.min(videoSize.width, Math.round(rawX + rawW));
  const bottom = Math.min(videoSize.height, Math.round(rawY + rawH));
  return {
    x,
    y,
    width: Math.max(0, right - x),
    height: Math.max(0, bottom - y),
  };
}
