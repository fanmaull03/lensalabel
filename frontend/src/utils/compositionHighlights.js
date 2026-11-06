const WORD_CHARACTER = /[\p{L}\p{M}\p{N}_]/u;

const CATEGORIES = ["hindari", "perhatian", "aman"];

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function findCompositionHighlights(text, result) {
  if (typeof text !== "string" || !text) return [];

  const candidates = [];
  for (const [priority, category] of CATEGORIES.entries()) {
    for (const item of result?.[category] ?? []) {
      const window = item.matched_window?.trim();
      if (!window) continue;

      const pattern = window.split(/\s+/u).map(escapeRegExp).join("\\s+");
      const expression = new RegExp(pattern, "giu");
      for (const match of text.matchAll(expression)) {
        const start = match.index;
        const end = start + match[0].length;
        if ((start > 0 && WORD_CHARACTER.test(text[start - 1])) ||
            (end < text.length && WORD_CHARACTER.test(text[end]))) continue;
        candidates.push({ start, end, category, priority });
      }
    }
  }

  candidates.sort((a, b) =>
    (b.end - b.start) - (a.end - a.start) || a.priority - b.priority || a.start - b.start
  );

  const selected = [];
  for (const candidate of candidates) {
    if (!selected.some((span) => candidate.start < span.end && span.start < candidate.end)) {
      selected.push(candidate);
    }
  }
  return selected.sort((a, b) => a.start - b.start);
}
