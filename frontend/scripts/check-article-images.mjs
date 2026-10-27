import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { articles } from "../src/data/educationContent.js";

const vite = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const { default: EducationPage, ArticleReader } = await vite.ssrLoadModule("/src/pages/GfcfEducationPage.jsx");
  const listing = renderToStaticMarkup(React.createElement(EducationPage));
  assert.equal((listing.match(/<img /g) ?? []).length, articles.length);
  for (const article of articles) {
    const html = renderToStaticMarkup(React.createElement(ArticleReader, { article, onBack: () => {} }));
    assert.equal((html.match(/<img /g) ?? []).length, 2, `${article.id}: gambar utama dan pendukung`);
    assert.match(html, /<figure /, `${article.id}: gambar di dalam isi artikel`);
    assert.match(html, /\.webp/, `${article.id}: aset WebP`);
  }
  console.log(`gambar artikel lulus: ${articles.length} pratinjau dan isi artikel diperiksa`);
} finally {
  await vite.close();
}
