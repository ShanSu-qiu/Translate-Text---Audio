// Client for the orchestrator API. The base URL comes from config.js.

const BASE = (window.PIPELINE_CONFIG?.apiBase ?? "").replace(/\/$/, "");
const enc = encodeURIComponent;

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

// FastAPI errors come as {detail: string | object | validation list}
function messageFrom(body, status) {
  const detail = body?.detail ?? body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  if (detail?.error) return detail.error;
  return `请求失败（HTTP ${status}）`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(BASE + path, options);
  } catch {
    throw new ApiError("连不上后端。请确认 docker compose 正在运行。", 0, null);
  }
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await response.json() : await response.text();
  if (!response.ok) throw new ApiError(messageFrom(body, response.status), response.status, body);
  return body;
}

function postJson(path, data) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export const api = {
  languages: () => request("/languages"),
  recordings: () => request("/recordings"),
  upload(file, filename) {
    const form = new FormData();
    form.append("file", file, filename ?? file.name);
    return request("/recordings", { method: "POST", body: form });
  },
  startJob: (query) => postJson("/jobs", { query }),
  job: (id) => request(`/jobs/${enc(id)}`),
  latestJob: () => request("/jobs/latest"),
  text(id, kind, language) {
    const query = language ? `?language=${enc(language)}` : "";
    return request(`/recordings/${enc(id)}/text/${enc(kind)}${query}`);
  },
  audioUrl: (id, language) => `${BASE}/recordings/${enc(id)}/audio/${enc(language)}`,
  sourceUrl: (id) => `${BASE}/recordings/${enc(id)}/source`,
};
