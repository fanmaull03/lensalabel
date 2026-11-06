import test from "node:test";
import assert from "node:assert/strict";
import { findCompositionHighlights } from "./compositionHighlights.js";

test("highlights only matched phrases in composition text", () => {
  const text = "Komposisi: Susu, Gula, Air. Informasi gizi: natrium.";
  const spans = findCompositionHighlights(text, {
    hindari: [{ matched_window: "Susu" }],
    perhatian: [{ matched_window: "Gula" }],
    aman: [{ matched_window: "Air" }, { matched_window: "Vitamin" }],
  });
  assert.deepEqual(spans.map(({ start, end, category }) => [text.slice(start, end), category]), [
    ["Susu", "hindari"], ["Gula", "perhatian"], ["Air", "aman"],
  ]);
});

test("longer phrase wins when matches overlap", () => {
  const text = "Minyak Kelapa Sawit dan minyak kelapa";
  const spans = findCompositionHighlights(text, {
    perhatian: [{ matched_window: "Minyak Kelapa Sawit" }],
    aman: [{ matched_window: "Minyak Kelapa" }],
  });
  assert.deepEqual(spans.map(({ start, end, category }) => [text.slice(start, end), category]), [
    ["Minyak Kelapa Sawit", "perhatian"], ["minyak kelapa", "aman"],
  ]);
});

test("same phrase uses the more cautious category and never overlaps", () => {
  const text = "Susu";
  const spans = findCompositionHighlights(text, {
    hindari: [{ matched_window: "Susu" }],
    aman: [{ matched_window: "Susu" }],
  });
  assert.equal(spans.length, 1);
  assert.equal(spans[0].category, "hindari");
});

test("matches punctuation literally, allows OCR line breaks, and skips partial words", () => {
  const text = "Susuu, INS 500(ii), Tepung\nBeras";
  const spans = findCompositionHighlights(text, {
    hindari: [{ matched_window: "Susu" }],
    perhatian: [{ matched_window: "INS 500(ii)" }],
    aman: [{ matched_window: "Tepung Beras" }],
  });
  assert.deepEqual(spans.map(({ start, end }) => text.slice(start, end)), [
    "INS 500(ii)", "Tepung\nBeras",
  ]);
});
