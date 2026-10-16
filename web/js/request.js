// 02 指令: send a free-form request and follow the job until it finishes.
import { api } from "./api.js";
import { emit } from "./dom.js";
import { createJobView } from "./job-view.js";

const POLL_MS = 1500;
const MAX_POLL_ERRORS = 5;
const isFinished = (job) => job.status === "done" || job.status === "failed";

export function initRequest({ form, textarea, submit, exampleButtons, jobRoot }) {
  const view = createJobView(jobRoot);
  let pollTimer = 0;
  let pollErrors = 0;

  function setRunning(running) {
    document.body.dataset.onair = running ? "true" : "false";
    submit.disabled = running;
    submit.setAttribute("aria-busy", String(running));
  }

  function follow(job) {
    window.clearTimeout(pollTimer);
    view.update(job);
    if (isFinished(job)) {
      setRunning(false);
      emit("recordings:changed");
      return;
    }
    setRunning(true);
    pollTimer = window.setTimeout(() => poll(job.id), POLL_MS);
  }

  async function poll(id) {
    try {
      const job = await api.job(id);
      pollErrors = 0;
      follow(job);
    } catch (error) {
      pollErrors += 1;
      if (pollErrors >= MAX_POLL_ERRORS) {
        setRunning(false);
        emit("banner", `暂时拿不到进度：${error.message}`);
        return;
      }
      pollTimer = window.setTimeout(() => poll(id), POLL_MS * 2);
    }
  }

  async function send() {
    const query = textarea.value.trim();
    if (!query) {
      textarea.focus();
      textarea.setAttribute("aria-invalid", "true");
      return;
    }
    textarea.removeAttribute("aria-invalid");
    setRunning(true);
    try {
      follow(await api.startJob(query));
    } catch (error) {
      setRunning(false);
      if (error.status === 409) {
        emit("banner", "已经有一个任务在跑，下面显示的就是它的进度。");
        resume();
        return;
      }
      emit("banner", error.message);
    }
  }

  async function resume() {
    try {
      follow(await api.latestJob());
    } catch (error) {
      if (error.status !== 404) emit("banner", error.message);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    send();
  });
  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      send();
    }
  });
  for (const button of exampleButtons) {
    button.addEventListener("click", () => {
      textarea.value = button.textContent;
      textarea.focus();
    });
  }

  // Pick up a job that is still running from before the page was opened
  resume();
}
