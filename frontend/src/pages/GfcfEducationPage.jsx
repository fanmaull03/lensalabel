import { useState } from "react";
import {
  articles,
  categoryLegend,
  EXPERT_REVIEWED,
  getReadMinutes,
  glossary,
} from "../data/educationContent";

const VERDICT_COLOR = {
  Aman: "border-emerald-500 text-emerald-600",
  "Perlu Perhatian": "border-amber-500 text-amber-700",
  Hindari: "border-red-500 text-red-600",
};

function EducationNotice({ reader = false }) {
  const color = reader ? "text-slate-500" : "text-white/65";
  return (
    <div className={`space-y-1 text-xs leading-relaxed ${color}`}>
      {!EXPERT_REVIEWED && <p>Konten ini dalam tinjauan ahli gizi</p>}
      <p>Konten edukasi umum, bukan pengganti nasihat dokter atau ahli gizi</p>
    </div>
  );
}

export default function GfcfEducationPage() {
  const [reading, setReading] = useState(null);
  const featured = articles.find((article) => article.featured) ?? articles[0];
  const rest = articles.filter((article) => article.id !== featured.id);

  if (reading) return <ArticleReader article={reading} onBack={() => setReading(null)} />;

  return (
    <div className="space-y-5 font-sans">
      <div>
        <h1 className="font-display text-2xl font-extrabold text-white">Belajar GFCF</h1>
        <p className="mt-1 text-sm text-white/65">Pahami diet dengan tenang.</p>
      </div>

      <button
        type="button"
        onClick={() => setReading(featured)}
        className="glass block w-full overflow-hidden rounded-3xl text-left shadow-2xl transition duration-200 active:scale-[.99]"
      >
        <div className="h-32 bg-gradient-to-br from-accent-blue to-accent-purple" />
        <div className="p-5 text-white">
          <div className="text-xs font-bold uppercase tracking-wide opacity-80">Mulai di sini</div>
          <div className="mt-1 break-words font-display text-xl font-extrabold leading-tight">{featured.title}</div>
          <div className="mt-2 text-sm text-white/70">
            {getReadMinutes(featured.body)} menit baca · {featured.category.toLowerCase()}
          </div>
        </div>
      </button>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/60">Artikel</h2>
        <div className="space-y-3">
          {rest.map((article) => (
            <button
              key={article.id}
              type="button"
              onClick={() => setReading(article)}
              className="glass flex w-full items-center gap-3 rounded-2xl p-3 text-left shadow-xl transition duration-200 hover:bg-white/20 active:scale-[.99]"
            >
              <div className="h-14 w-16 flex-none rounded-xl bg-gradient-to-br from-accent-green/70 to-accent-blue/60" />
              <div className="min-w-0 flex-1">
                <div className="break-words font-semibold text-white">{article.title}</div>
                <div className="text-xs text-white/60">{getReadMinutes(article.body)} menit baca</div>
              </div>
              <span className="text-white/50">›</span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/60">Glosarium istilah asing</h2>
        <div className="mb-3 space-y-1 rounded-2xl p-3 text-xs leading-relaxed text-white/80 glass">
          {categoryLegend.map((item) => (
            <p key={item.verdict}><strong>{item.verdict}:</strong> {item.description}</p>
          ))}
        </div>
        <div className="space-y-3">
          {glossary.map((item) => (
            <div key={item.kbId} className={`glass-white min-w-0 rounded-2xl border-l-4 p-4 shadow-xl ${VERDICT_COLOR[item.verdict]}`}>
              <div className="flex min-w-0 items-start justify-between gap-2">
                <span className="min-w-0 flex-1 break-words font-mono text-sm text-navy-base [overflow-wrap:anywhere]">{item.term}</span>
                <span className="max-w-[45%] shrink-0 text-right text-xs font-bold">{item.verdict}</span>
              </div>
              <p className="mt-1.5 break-words text-xs leading-relaxed text-slate-500 [overflow-wrap:anywhere]">{item.note}</p>
            </div>
          ))}
        </div>
      </div>

      <EducationNotice />
    </div>
  );
}

function ArticleBlock({ block }) {
  if (block.type === "heading") {
    return <h2 className="mt-6 break-words font-display text-lg font-bold text-navy-base">{block.text}</h2>;
  }
  if (block.type === "list") {
    return (
      <ul className="mt-4 list-disc space-y-2 pl-5 text-[15px] leading-relaxed text-slate-600 [overflow-wrap:anywhere]">
        {block.items.map((item, index) => <li key={`${index}-${item.slice(0, 20)}`}>{item}</li>)}
      </ul>
    );
  }
  return <p className="mt-4 text-[15px] leading-relaxed text-slate-600 [overflow-wrap:anywhere]">{block.text}</p>;
}

function ArticleReader({ article, onBack }) {
  return (
    <div className="animate-fade-up min-w-0 overflow-hidden rounded-3xl bg-[#F7F9FC] shadow-2xl">
      <div className="relative h-40 bg-gradient-to-br from-accent-blue to-accent-purple">
        <button
          type="button"
          onClick={onBack}
          aria-label="Kembali ke daftar artikel"
          className="absolute left-4 top-4 flex h-10 w-10 items-center justify-center rounded-xl border border-white/30 bg-navy-base/30 text-white backdrop-blur transition active:scale-90"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
        </button>
        <span className="absolute bottom-4 left-5 rounded-full border border-white/35 bg-accent-blue/60 px-3 py-1 text-xs font-bold uppercase tracking-wide text-white backdrop-blur">
          {article.category}
        </span>
      </div>

      <div className="min-w-0 p-6">
        <h1 className="break-words font-display text-2xl font-extrabold leading-tight text-navy-base">{article.title}</h1>
        <div className="mt-3 flex min-w-0 items-center gap-3">
          <div className="h-9 w-9 flex-none rounded-full bg-gradient-to-br from-accent-blue to-accent-green" />
          <div className="min-w-0">
            <div className="break-words text-sm font-semibold text-navy-base">{article.author}</div>
            <div className="break-words font-mono text-xs text-slate-400">
              {getReadMinutes(article.body)} menit baca · Diperbarui {article.updated}
            </div>
          </div>
        </div>

        <div>{article.body.map((block, index) => <ArticleBlock key={`${article.id}-${index}`} block={block} />)}</div>

        <div className="mt-5 rounded-2xl border-l-4 border-accent-blue bg-[#EAF0FD] p-4">
          <p className="break-words font-display text-sm font-semibold leading-snug text-navy-base [overflow-wrap:anywhere]">“{article.quote}”</p>
        </div>

        <section className="mt-6 min-w-0" aria-labelledby="education-references">
          <h2 id="education-references" className="font-display text-sm font-bold text-navy-base">Referensi</h2>
          <ol className="mt-2 space-y-3 text-xs leading-relaxed text-slate-600">
            {article.references.map((reference) => (
              <li key={reference.id} className="min-w-0 [overflow-wrap:anywhere]">
                <span className="font-semibold">[{reference.id}] </span>{reference.text}
                <a
                  href={reference.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block break-all text-accent-blue-link underline"
                >
                  {reference.url}
                </a>
              </li>
            ))}
          </ol>
        </section>

        <div className="mt-6"><EducationNotice reader /></div>
        <button
          type="button"
          onClick={onBack}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl border border-navy-base/10 bg-white py-3 font-display text-sm font-semibold text-accent-blue-link shadow-sm transition active:scale-[.98]"
        >
          ‹ Kembali ke daftar
        </button>
      </div>
    </div>
  );
}
