import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const { default: ResultPage } = await vite.ssrLoadModule("/src/pages/ResultPage.jsx");
  const result = {
    verdict: "hindari",
    hindari: [{ standard_name: "Terigu / Gandum", matched_window: "Tepung Terigu, Wheat Flour", score: 99 }],
    perhatian: [],
    aman: [{ standard_name: "Gula", matched_window: "Gula", score: 99 }],
    tidak_dikenali: [],
    raw_text: "Nama produk Komposisi: Tepung Terigu, Gula. Diproduksi oleh A",
    composition_text: "Komposisi: Tepung Terigu, Gula.",
    opening_marker_found: true,
    closing_marker_found: true,
    input_source: "photo",
  };
  const render = (data) => renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries: [{ pathname: "/hasil", state: data }] }, React.createElement(ResultPage))
  );
  const html = render(result);
  assert.match(html, /Teks komposisi yang dianalisis/);
  assert.match(html, /hingga sebelum penanda akhir/);
  assert.match(html, /<mark[^>]*>Tepung Terigu<\/mark>/);
  assert.match(html, /<mark[^>]*>Gula<\/mark>/);
  assert.match(html, /Lihat teks OCR lengkap/);
  assert.match(html, /Diproduksi oleh A/);
  assert.doesNotMatch(render({ ...result, input_source: "manual" }), /Lihat teks OCR lengkap/);
  console.log("hasil: komposisi, sorotan bahan, dan teks OCR lulus");
} finally {
  await vite.close();
}
