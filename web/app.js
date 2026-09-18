let csrf = "";

function setStatus(node, message, isError = false) {
  node.replaceChildren(document.createTextNode(message));
  node.classList.toggle("error", isError);
}

async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrf;
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    location.assign("/login");
    throw new Error("Сессия закончилась.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Ошибка запроса");
  }
  return response.json();
}

function renderJob(node, state) {
  const labels = { queued: "В очереди", running: "Выполняется", succeeded: "Готово", failed: "Ошибка" };
  node.replaceChildren(document.createTextNode(labels[state.status] || state.status));
  node.classList.toggle("error", state.status === "failed");
  if (state.progress.length) node.append(document.createElement("br"), document.createTextNode(state.progress.join("\n")));
  if (state.error) node.append(document.createElement("br"), document.createTextNode(state.error));
  if (state.status !== "succeeded") return;
  const download = document.createElement("a");
  download.href = state.download_url;
  download.textContent = "Скачать результат";
  download.className = "result-link";
  node.append(document.createElement("br"), download);
  if (state.viewer_url) {
    const viewer = document.createElement("a");
    viewer.href = state.viewer_url;
    viewer.textContent = "Открыть переписки";
    node.append(viewer);
  }
}

async function watchJob(job, node) {
  while (true) {
    const state = await api(`/api/jobs/${job.id}`);
    renderJob(node, state);
    if (state.status === "succeeded" || state.status === "failed") return;
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
}

async function submitJob(event, url, body, statusId) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const status = document.getElementById(statusId);
  button.disabled = true;
  setStatus(status, "Задание поставлено в очередь…");
  try {
    const job = await api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body()) });
    await watchJob(job, status);
  } catch (error) {
    setStatus(status, error.message, true);
  } finally {
    button.disabled = false;
  }
}

function openLocalViewer() {
  const file = document.getElementById("local-json").files[0];
  const status = document.getElementById("local-status");
  if (!file) return setStatus(status, "Сначала выберите JSON-файл.", true);
  const reader = new FileReader();
  reader.onerror = () => setStatus(status, "Не удалось прочитать выбранный файл.", true);
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!data || data.schema_version !== 2 || !Array.isArray(data.tickets)) throw new Error("Файл не является экспортом формата v2.");
      sessionStorage.setItem("ispano-local-json", reader.result);
      location.assign("/viewer?local=1");
    } catch (error) {
      setStatus(status, error.message || "Некорректный JSON-файл.", true);
    }
  };
  reader.readAsText(file);
}

async function initialize() {
  try {
    const session = await api("/api/session");
    csrf = session.csrf;
    document.getElementById("user").textContent = session.username;
    if (session.ai_enabled) document.getElementById("ai-row").classList.remove("hidden");
    document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
    setStatus(document.getElementById("json-status"), "");
    setStatus(document.getElementById("report-status"), "");
  } catch (error) {
    setStatus(document.getElementById("json-status"), error.message, true);
    setStatus(document.getElementById("report-status"), error.message, true);
  }
}

document.getElementById("json-form").addEventListener("submit", (event) => submitJob(event, "/api/jobs/json", () => ({ since: document.getElementById("since").value }), "json-status"));
document.getElementById("report-form").addEventListener("submit", (event) => submitJob(event, "/api/jobs/report", () => ({ ticket_id: Number(document.getElementById("ticket-id").value), use_ai: document.getElementById("use-ai").checked }), "report-status"));
document.getElementById("logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); location.assign("/login"); });
document.getElementById("open-local").addEventListener("click", openLocalViewer);
initialize();
