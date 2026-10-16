const LANGUAGE_NAMES = {
  en: "英语", fr: "法语", es: "西班牙语", de: "德语", it: "意大利语", ja: "日语", zh: "中文",
};
// BCP 47 tags for the lang attribute, so each text renders with the right fonts and is read correctly
const LANGUAGE_TAGS = { zh: "zh-CN", en: "en", fr: "fr", es: "es", de: "de", it: "it", ja: "ja" };

const INTENT_NAMES = {
  transcript: "录音转写",
  podcast_text: "英文播客文稿",
  translated_text: "翻译文稿",
  audio: "配音播客",
  unsupported: "无法处理",
};

const STEP_NAMES = {
  transcribe: "转写",
  generate: "撰写文稿",
  translate: "翻译",
  synthesis: "配音",
};

export const languageName = (code) => LANGUAGE_NAMES[code] ?? code.toUpperCase();
export const languageTag = (code) => LANGUAGE_TAGS[code] ?? code;
export const intentName = (intent) => INTENT_NAMES[intent] ?? intent;

export function stepParts(name) {
  const [service, language] = name.split(":");
  return { title: STEP_NAMES[service] ?? service, language: language ?? null };
}

// Unix seconds -> "10月16日 14:30" in the viewer's time zone
export function recordingTime(createdAt) {
  if (!createdAt) return null;
  const d = new Date(createdAt * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatDuration(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}
