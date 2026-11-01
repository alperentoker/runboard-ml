// Loaded in <head>, before anything is drawn, so the page never flashes the other theme: dark unless the reader
// picked light or the system's own (auto).
(() => { let t = null; try { t = localStorage.getItem("rb-theme"); } catch {} document.documentElement.dataset.theme = ["light", "auto"].includes(t) ? t : "dark"; })();
