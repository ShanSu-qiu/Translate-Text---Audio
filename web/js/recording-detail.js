// Expanded view of one recording: a reader for each text version and a player per language.
import { api } from "./api.js";
import { el } from "./dom.js";
import { languageName, languageTag } from "./labels.js";

const textCache = new Map();

function textVersions(rec) {
  return [
    rec.transcript && { key: "transcript", label: "转写", kind: "transcript", lang: "en" },
    rec.script && { key: "script", label: "英文文稿", kind: "script", lang: "en" },
    ...rec.translations.map((code) => ({
      key: `translation:${code}`, label: languageName(code), kind: "translation", language: code, lang: code,
    })),
  ].filter(Boolean);
}

async function loadText(rec, version) {
  const cacheKey = `${rec.id}|${version.key}`;
  if (!textCache.has(cacheKey)) {
    const { text } = await api.text(rec.id, version.kind, version.language);
    textCache.set(cacheKey, text);
  }
  return textCache.get(cacheKey);
}

function renderReader(rec) {
  const versions = textVersions(rec);
  if (!versions.length) {
    return el("div", { class: "detail__block" },
      el("h3", { class: "detail__title", text: "文字" }),
      el("p", { class: "detail__empty", text: "还没有文字。在「02 指令」里说「只要录音的转写文字」就会开始。" }));
  }

  const reader = el("article", { class: "reader", tabindex: "0", "aria-live": "polite" });
  const buttons = versions.map((version) => el("button", {
    type: "button", class: "segment", "aria-pressed": "false", text: version.label,
  }));

  async function show(index) {
    const version = versions[index];
    buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(i === index)));
    reader.lang = languageTag(version.lang);
    reader.dataset.state = "loading";
    reader.replaceChildren(el("p", { class: "reader__loading", text: "载入中…" }));
    try {
      const text = await loadText(rec, version);
      const paragraphs = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
      reader.replaceChildren(...paragraphs.map((p) => el("p", { text: p })));
      delete reader.dataset.state;
    } catch (error) {
      reader.dataset.state = "error";
      reader.replaceChildren(el("p", { text: `载入失败：${error.message}` }));
    }
  }

  buttons.forEach((button, index) => button.addEventListener("click", () => show(index)));
  show(versions.length - 1); // most processed version first
  return el("div", { class: "detail__block detail__block--text" },
    el("h3", { class: "detail__title", text: "文字" }),
    el("div", { class: "segments", role: "group", "aria-label": "选择文字版本" }, buttons),
    reader);
}

function renderPlayers(rec) {
  if (!rec.audio.length) {
    return el("div", { class: "detail__block" },
      el("h3", { class: "detail__title", text: "配音" }),
      el("p", { class: "detail__empty", text: "还没有配音。在「02 指令」里说「我想听中文版的播客」试试。" }));
  }
  return el("div", { class: "detail__block detail__block--audio" },
    el("h3", { class: "detail__title", text: "配音" }),
    el("ul", { class: "players" }, rec.audio.map((code) => {
      const url = api.audioUrl(rec.id, code);
      return el("li", { class: "players__item" },
        el("p", { class: "players__label" },
          languageName(code), el("span", { class: "chip__code", text: code })),
        el("audio", {
          class: "player", controls: true, preload: "none", src: url,
          "aria-label": `${languageName(code)}配音`,
        }),
        el("a", { class: "players__download", href: url, download: `${rec.id}-${code}.wav`, text: "下载 WAV" }));
    })));
}

export function renderDetail(rec) {
  return el("div", { class: "detail" }, renderReader(rec), renderPlayers(rec));
}
