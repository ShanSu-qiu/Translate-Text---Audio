// 01 素材: upload a file or record one, then send it to the bucket.
import { api } from "./api.js";
import { el, emit, setStatus } from "./dom.js";
import { formatDuration } from "./labels.js";
import {
  MAX_RECORDING_MS, extensionFor, isRecordingSupported, recordingErrorMessage, startRecording,
} from "./recorder.js";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"];

export function initIntake({ dropzone, fileInput, recorderRoot, status }) {
  let busy = false;

  async function upload(file, filename) {
    if (busy) return;
    busy = true;
    dropzone.dataset.state = "uploading";
    setStatus(status, `正在上传 ${filename}…`);
    try {
      const { id } = await api.upload(file, filename);
      // A running job already downloaded its inputs, so this recording waits for the next one
      const jobRunning = document.body.dataset.onair === "true";
      setStatus(status, jobRunning
        ? `已上传为 ${id}。现在有任务在运行，这段录音会在下一次制作时处理。`
        : `已上传为 ${id}。接下来在「02 指令」里说你想要什么。`, "success");
      emit("recordings:changed");
      return id;
    } catch (error) {
      setStatus(status, `上传失败：${error.message}`, "error");
      return null;
    } finally {
      busy = false;
      delete dropzone.dataset.state;
    }
  }

  function validate(file) {
    const name = file.name.toLowerCase();
    const knownType = file.type.startsWith("audio/") || ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
    if (!knownType) return "这不是支持的音频文件。";
    if (file.size > MAX_UPLOAD_BYTES) return "文件超过 10 MB，请剪短一些再上传。";
    if (file.size === 0) return "文件是空的。";
    return null;
  }

  function handleFile(file) {
    if (!file) return;
    const problem = validate(file);
    if (problem) {
      setStatus(status, problem, "error");
      return;
    }
    upload(file, file.name);
  }

  fileInput.addEventListener("change", () => {
    handleFile(fileInput.files[0]);
    fileInput.value = "";
  });
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.dataset.drag = "over";
  });
  dropzone.addEventListener("dragleave", () => delete dropzone.dataset.drag);
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    delete dropzone.dataset.drag;
    handleFile(event.dataTransfer.files[0]);
  });

  initRecorder(recorderRoot, status, upload);
}

function initRecorder(root, status, upload) {
  let session = null;
  let frame = 0;
  let autoStop = 0;
  let previewUrl = null;

  function clearPreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }

  function showIdle() {
    clearPreview();
    if (!isRecordingSupported()) {
      root.replaceChildren(el("p", { class: "recorder__note", text: "这个浏览器不支持录音，请上传文件。" }));
      return;
    }
    root.dataset.state = "idle";
    root.replaceChildren(
      el("button", { type: "button", class: "btn btn--record", onclick: begin },
        el("span", { class: "btn--record__dot", "aria-hidden": "true" }), "开始录音"),
      el("p", { class: "recorder__note", text: `最长 ${MAX_RECORDING_MS / 60000} 分钟，请用英文讲。` }),
    );
  }

  function showRecording() {
    root.dataset.state = "recording";
    const timer = el("span", { class: "recorder__timer", text: "0:00" });
    const meterFill = el("span", { class: "meter__fill" });
    root.replaceChildren(
      el("div", { class: "recorder__live" },
        el("span", { class: "lamp lamp--live", "aria-hidden": "true" }),
        el("span", { class: "visually-hidden", text: "正在录音" }),
        timer,
        el("span", { class: "meter", "aria-hidden": "true" }, meterFill)),
      el("button", { type: "button", class: "btn btn--stop", onclick: finish }, "停止"),
    );
    const tick = () => {
      timer.textContent = formatDuration(performance.now() - session.startedAt);
      meterFill.style.transform = `scaleX(${Math.min(1, session.level() * 1.6).toFixed(3)})`;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
  }

  function showReview(blob, durationMs) {
    root.dataset.state = "review";
    clearPreview();
    previewUrl = URL.createObjectURL(blob);
    const filename = `recording.${extensionFor(blob.type)}`;
    const sendButton = el("button", { type: "button", class: "btn btn--ink" }, "上传这段录音");
    sendButton.addEventListener("click", async () => {
      sendButton.disabled = true;
      const id = await upload(blob, filename);
      if (id) showIdle();
      else sendButton.disabled = false;
    });
    root.replaceChildren(
      el("p", { class: "recorder__note", text: `录好了，时长 ${formatDuration(durationMs)}。先听一下：` }),
      el("audio", { class: "player", controls: true, src: previewUrl, "aria-label": "录音预览" }),
      el("div", { class: "recorder__actions" },
        sendButton,
        el("button", { type: "button", class: "btn btn--quiet", onclick: showIdle }, "重录")),
    );
  }

  async function begin() {
    try {
      session = await startRecording();
    } catch (error) {
      setStatus(status, recordingErrorMessage(error), "error");
      return;
    }
    setStatus(status, "");
    showRecording();
    autoStop = window.setTimeout(finish, MAX_RECORDING_MS);
  }

  async function finish() {
    if (!session) return;
    cancelAnimationFrame(frame);
    window.clearTimeout(autoStop);
    const current = session;
    session = null;
    const durationMs = performance.now() - current.startedAt;
    const blob = await current.stop();
    if (blob.size === 0) {
      setStatus(status, "没有录到声音，请再试一次。", "error");
      showIdle();
      return;
    }
    showReview(blob, durationMs);
  }

  window.addEventListener("pagehide", () => session?.cancel());
  showIdle();
}
