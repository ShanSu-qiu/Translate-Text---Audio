// 03 成品: one log row per recording, with a channel strip showing which languages have audio.
import { api } from "./api.js";
import { el } from "./dom.js";
import { languageName, recordingTime } from "./labels.js";
import { renderDetail } from "./recording-detail.js";

function stageChip(label, ready) {
  return el("li", { class: "stage", "data-ready": String(ready) },
    label, el("span", { class: "visually-hidden", text: ready ? "（已完成）" : "（未完成）" }));
}

function renderChannels(rec, languages, player, nowPlaying) {
  const choices = [
    { code: null, label: "原声", name: "原始录音", url: api.sourceUrl(rec.id), on: true },
    ...languages.map((code) => ({
      code, label: code, name: `${languageName(code)}配音`,
      url: api.audioUrl(rec.id, code), on: rec.audio.includes(code),
    })),
  ];
  const buttons = choices.map((choice) => el("button", {
    type: "button",
    class: choice.code ? "channel" : "channel channel--source",
    "data-on": String(choice.on),
    "aria-pressed": String(!choice.code),
    "aria-label": choice.on ? `播放${choice.name}` : `${languageName(choice.code)}还没有配音`,
    disabled: !choice.on,
    text: choice.label,
  }));
  buttons.forEach((button, index) => button.addEventListener("click", () => {
    const choice = choices[index];
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    nowPlaying.textContent = choice.name;
    player.src = choice.url;
    player.setAttribute("aria-label", choice.name);
    player.play().catch(() => {}); // autoplay can be refused; the controls still work
  }));
  return el("div", { class: "channels", role: "group", "aria-label": "选择要听的版本" }, buttons);
}

function renderRow(rec, languages, expanded, toggle) {
  const detailId = `detail-${rec.id}`;
  const time = recordingTime(rec.created_at);
  const nowPlaying = el("span", { class: "log__now-name", text: "原始录音" });
  const player = el("audio", {
    class: "player log__source", controls: true, preload: "none",
    src: api.sourceUrl(rec.id), "aria-label": "原始录音",
  });

  const button = el("button", {
    type: "button", class: "btn btn--quiet log__toggle",
    "aria-expanded": String(expanded), "aria-controls": detailId,
    text: expanded ? "收起" : "打开",
  });
  button.addEventListener("click", () => toggle(rec.id));

  const row = el("li", { class: "log__row", "data-id": rec.id, "data-expanded": String(expanded) },
    el("div", { class: "log__meta" },
      el("p", { class: "log__time", text: time ?? rec.id }),
      el("p", { class: "log__id", text: rec.id })),
    el("div", { class: "log__listen" },
      el("p", { class: "log__now" }, "正在听 · ", nowPlaying),
      player),
    el("div", { class: "log__progress" },
      rec.transcript ? null : el("p", { class: "log__pending" },
        el("span", { class: "log__pending-tag", text: "待处理" }),
        "在「02 指令」里下一个指令就会处理它"),
      el("ul", { class: "stages", "aria-label": "文字进度" },
        stageChip("转写", rec.transcript),
        stageChip("文稿", rec.script),
        stageChip(`翻译 ${rec.translations.length}`, rec.translations.length > 0)),
      renderChannels(rec, languages, player, nowPlaying)),
    button);

  const detail = el("div", { class: "log__detail", id: detailId, hidden: !expanded });
  if (expanded) detail.append(renderDetail(rec));
  row.append(detail);
  return row;
}

export function initLibrary({ list, refreshButton, languages }) {
  let recordings = [];
  let lastLoaded = "";
  const expanded = new Set();

  const rowFor = (rec) => renderRow(rec, languages, expanded.has(rec.id), toggle);

  function render() {
    if (!recordings.length) {
      list.replaceChildren(el("li", { class: "log__empty" },
        el("p", { class: "log__empty-title", text: "还没有录音" }),
        el("p", { text: "先在「01 素材」上传或录一段英文音频。" })));
      return;
    }
    list.replaceChildren(...recordings.map(rowFor));
  }

  // Only the toggled row is rebuilt, so audio playing in other rows keeps going
  function toggle(id) {
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
    const rec = recordings.find((r) => r.id === id);
    const oldRow = list.querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (!rec || !oldRow) return;
    const newRow = rowFor(rec);
    oldRow.replaceWith(newRow);
    newRow.querySelector(".log__toggle").focus();
  }

  async function refresh() {
    list.setAttribute("aria-busy", "true");
    refreshButton.disabled = true;
    try {
      const loaded = await api.recordings();
      const snapshot = JSON.stringify(loaded);
      // Skip re-rendering when nothing changed, so playing audio is not interrupted
      if (snapshot !== lastLoaded) {
        recordings = loaded;
        lastLoaded = snapshot;
        render();
      }
    } catch (error) {
      list.replaceChildren(el("li", { class: "log__empty", "data-tone": "error" },
        el("p", { class: "log__empty-title", text: "载入失败" }),
        el("p", { text: error.message })));
      lastLoaded = "";
    } finally {
      list.removeAttribute("aria-busy");
      refreshButton.disabled = false;
    }
  }

  refreshButton.addEventListener("click", refresh);
  refresh();
  return { refresh };
}
