// Microphone recording with a live input level, via MediaRecorder + Web Audio.

// Chrome/Firefox record webm/opus, Safari records mp4/aac
const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
// transcribe_audio waits at most 90 s for Speech-to-Text, which handles a few minutes of speech
export const MAX_RECORDING_MS = 5 * 60 * 1000;

export function isRecordingSupported() {
  return Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
}

/** @param {string} mimeType @returns {string} file extension the backend accepts */
export function extensionFor(mimeType) {
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

/** @param {unknown} error @returns {string} */
export function recordingErrorMessage(error) {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError") return "麦克风权限被拒绝了。请在浏览器地址栏允许使用麦克风后再试。";
  if (name === "NotFoundError") return "没有找到麦克风。";
  return "没法开始录音，请改用上传文件。";
}

/**
 * Start recording from the default microphone.
 * @returns {Promise<{startedAt: number, level: () => number, stop: () => Promise<Blob>, cancel: () => void}>}
 */
export async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks = [];
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size) chunks.push(event.data);
  });
  const stopped = new Promise((resolve) => {
    recorder.addEventListener("stop", () => {
      resolve(new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" }));
    });
  });

  const audioContext = new AudioContext();
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 512;
  audioContext.createMediaStreamSource(stream).connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);

  function release() {
    stream.getTracks().forEach((track) => track.stop());
    audioContext.close();
  }

  recorder.start(1000);
  return {
    startedAt: performance.now(),
    level() {
      analyser.getByteTimeDomainData(samples);
      let peak = 0;
      for (const sample of samples) peak = Math.max(peak, Math.abs(sample - 128));
      return peak / 128;
    },
    async stop() {
      if (recorder.state !== "inactive") recorder.stop();
      const blob = await stopped;
      release();
      return blob;
    },
    cancel() {
      if (recorder.state !== "inactive") recorder.stop();
      release();
    },
  };
}
