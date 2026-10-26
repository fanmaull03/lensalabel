import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  articles,
  categoryLegend,
  glossary,
  AUTHOR,
  UPDATED,
} from "../src/data/educationContent.js";

const source = readFileSync(fileURLToPath(new URL("../src/data/educationContent.js", import.meta.url)), "utf8");
const content = JSON.stringify({ articles, glossary, categoryLegend, AUTHOR, UPDATED });
const blocked = [
  ["penanda verifikasi", /\[BUTUH/i],
  ["penanda sumber lama", /\[S/i],
  ["em dash", /\u2014/u],
  ["klaim menyembuhkan", /\bmenyembuhkan\b/i],
  ["klaim mengobati", /\bmengobati\b/i],
  ["klaim menjanjikan", /\bmenjanjikan\b/i],
  ["frasa tidak efektif", /tidak efektif/i],
];

const failures = [];
for (const [label, pattern] of blocked) {
  if (pattern.test(source) || pattern.test(content)) failures.push(label);
}

if (articles.length !== 4 || glossary.length !== 12) {
  failures.push("jumlah artikel atau kartu glosarium");
}
for (const article of articles) {
  if (!article.id || !article.title || !article.author || !article.updated || !article.quote) {
    failures.push(`metadata artikel ${article.id ?? "tanpa ID"}`);
  }
  if (!Array.isArray(article.body) || !article.body.every((block) =>
    ["paragraph", "heading", "list"].includes(block.type) &&
    (block.type === "list" ? Array.isArray(block.items) : typeof block.text === "string")
  )) failures.push(`blok artikel ${article.id}`);

  const ids = article.references.map((reference) => reference.id);
  if (ids.some((id, index) => id !== index + 1)) failures.push(`urutan referensi ${article.id}`);
  const bodyText = article.body.flatMap((block) => block.type === "list" ? block.items : [block.text]).join(" ");
  const firstSeen = [];
  for (const citation of bodyText.matchAll(/\[(\d+(?:,\s*\d+)*)\]/g)) {
    for (const id of citation[1].split(",").map((value) => Number(value.trim()))) {
      if (!ids.includes(id)) failures.push(`sitasi ${id} tanpa referensi pada ${article.id}`);
      if (!firstSeen.includes(id)) firstSeen.push(id);
    }
  }
  if (firstSeen.join(",") !== ids.join(",")) failures.push(`urutan kemunculan sitasi ${article.id}`);
}

if (failures.length) {
  console.error(`check:content gagal: ${failures.join("; ")}`);
  process.exitCode = 1;
} else {
  console.log(`check:content lulus: ${articles.length} artikel, ${glossary.length} kartu, sitasi dan kata terlarang diperiksa.`);
}
