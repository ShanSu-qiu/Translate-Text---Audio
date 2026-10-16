// Where the orchestrator API lives.
// Empty string = same origin (the UI served by the orchestrator at http://localhost:9000).
// When the UI is deployed separately (e.g. on Vercel), set this to the backend URL, e.g.
//   apiBase: "https://orchestrator-xxxx.a.run.app"
// and add the UI's origin to ALLOWED_ORIGINS on the backend.
window.PIPELINE_CONFIG = {
  apiBase: "",
};
