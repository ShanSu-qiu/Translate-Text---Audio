// Renders one job: how the request was understood, then the steps as a lit signal path.
// Rows are keyed by step name and updated in place so running lamps keep animating smoothly.
import { el } from "./dom.js";
import { formatDuration, intentName, languageName, stepParts } from "./labels.js";

const STATE_TEXT = { pending: "等待", running: "进行中", done: "完成", failed: "失败" };

function statusText(job) {
  if (job.status === "classifying") return "正在理解你的请求…";
  if (job.status === "done") {
    const took = formatDuration((job.finished_at - job.created_at) * 1000);
    return `全部完成 · 用时 ${took}`;
  }
  if (job.status === "failed") return "没能完成";
  if (!job.plan.length) return "正在安排步骤…";
  return `处理中 · 第 ${Math.min(job.done.length + 1, job.plan.length)} / ${job.plan.length} 步`;
}

function stepState(job, name) {
  if (job.done.includes(name)) return "done";
  if (job.current === name) return "running";
  if (job.status === "failed") {
    const firstUnfinished = job.plan.find((step) => !job.done.includes(step));
    if (firstUnfinished === name) return "failed";
  }
  return "pending";
}

function renderUnderstanding(job) {
  const result = job.classification;
  const intent = result?.intent ?? job.intent;
  const languages = result?.languages ?? job.languages;
  return [
    el("p", { class: "understood__label", text: job.query ? "理解为" : "直接执行" }),
    el("p", { class: "understood__intent", text: intentName(intent) }),
    languages.length
      ? el("ul", { class: "chips", "aria-label": "语言" },
        languages.map((code) => el("li", { class: "chip chip--lang" },
          languageName(code), el("span", { class: "chip__code", text: code }))))
      : null,
    result?.reason ? el("p", { class: "understood__reason", text: result.reason }) : null,
  ].filter(Boolean);
}

function renderStep(name) {
  const { title, language } = stepParts(name);
  const state = el("span", { class: "step__state" });
  const row = el("li", { class: "step", "data-step": name },
    el("span", { class: "step__lamp", "aria-hidden": "true" }),
    el("span", { class: "step__title", text: title }),
    language ? el("span", { class: "step__lang", text: languageName(language) }) : null,
    state);
  return { row, state };
}

export function createJobView(root) {
  const status = el("p", { class: "job__status", role: "status", "aria-live": "polite" });
  const query = el("p", { class: "job__query" });
  const understood = el("div", { class: "understood" });
  const steps = el("ol", { class: "signal-path", "aria-label": "执行步骤" });
  const error = el("p", { class: "job__error", role: "alert", hidden: true });
  const warnings = el("div", { class: "job__warnings", role: "status", hidden: true });
  root.replaceChildren(
    el("div", { class: "job__head" }, el("span", { class: "lamp", "aria-hidden": "true" }), status),
    query, understood, steps, warnings, error,
  );

  let jobId = null;
  let rows = new Map();
  let understoodShown = false;

  function update(job) {
    if (job.id !== jobId) {
      jobId = job.id;
      rows = new Map();
      understoodShown = false;
      steps.replaceChildren();
      understood.replaceChildren();
    }
    root.hidden = false;
    root.dataset.status = job.status;
    status.textContent = statusText(job);
    query.textContent = job.query ? `“${job.query}”` : "";

    if (!understoodShown && (job.classification || job.plan.length)) {
      understood.replaceChildren(...renderUnderstanding(job));
      understoodShown = true;
    }
    if (rows.size !== job.plan.length) {
      rows = new Map(job.plan.map((name) => [name, renderStep(name)]));
      steps.replaceChildren(...[...rows.values()].map((r) => r.row));
    }
    for (const [name, { row, state }] of rows) {
      const value = stepState(job, name);
      row.dataset.state = value;
      state.textContent = STATE_TEXT[value];
    }

    const skipped = job.warnings ?? [];
    warnings.hidden = skipped.length === 0;
    if (skipped.length) {
      warnings.replaceChildren(
        el("p", { class: "job__warnings-title", text: `有 ${skipped.length} 段录音被跳过，其他录音照常处理：` }),
        el("ul", {}, skipped.map((w) => el("li", { text: w }))),
      );
    }

    error.hidden = job.status !== "failed";
    error.textContent = job.classification?.intent === "unsupported"
      ? "这件事流水线做不了。试试说你想要转写、文稿、翻译，或者某种语言的配音。"
      : job.error ?? "";
  }

  return { update };
}
