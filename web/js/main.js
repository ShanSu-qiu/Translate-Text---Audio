import { api } from "./api.js";
import { $, $$, on } from "./dom.js";
import { initIntake } from "./intake.js";
import { languageName } from "./labels.js";
import { initLibrary } from "./library.js";
import { initRequest } from "./request.js";

const FALLBACK_LANGUAGES = ["en", "fr", "es", "de", "it", "ja", "zh"];
const BANNER_MS = 8000;

function initBanner() {
  const banner = $("#banner");
  let timer = 0;
  on("banner", (message) => {
    banner.textContent = message;
    banner.hidden = false;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => { banner.hidden = true; }, BANNER_MS);
  });
}

async function loadLanguages() {
  try {
    const { supported } = await api.languages();
    return supported;
  } catch (error) {
    document.dispatchEvent(new CustomEvent("banner", { detail: error.message }));
    return FALLBACK_LANGUAGES;
  }
}

async function main() {
  initBanner();
  const languages = await loadLanguages();
  $("#supported").textContent = `可用语言：${languages.map(languageName).join(" · ")}`;

  initIntake({
    dropzone: $("#dropzone"),
    fileInput: $("#file-input"),
    recorderRoot: $("#recorder"),
    status: $("#intake-status"),
  });
  initRequest({
    form: $("#request-form"),
    textarea: $("#query"),
    submit: $("#submit"),
    exampleButtons: $$(".chip--example"),
    jobRoot: $("#job"),
  });
  const library = initLibrary({ list: $("#recordings"), refreshButton: $("#refresh"), languages });
  on("recordings:changed", () => library.refresh());
}

main();
