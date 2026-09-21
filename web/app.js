let csrf = "";
let sessionReady = false;

const jobLabels = {
  queued: "В очереди",
  running: "Выполняется",
  succeeded: "Готово",
  failed: "Ошибка",
};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clearStatus(node) {
  node.replaceChildren();
  node.hidden = true;
  node.removeAttribute("data-status");
}

function renderStatus(node, state) {
  node.hidden = false;
  node.dataset.status = state.status || "idle";
  node.replaceChildren();
  const card = element("div", null, "status-card");
  const heading = element("div", null, "status-card__heading");
  heading.append(element("span", jobLabels[state.status] || "Состояние", "status-chip"));
  heading.append(element("span", state.message || jobLabels[state.status] || "Ожидание"));
  card.append(heading);

  if (Array.isArray(state.progress) && state.progress.length) {
    const log = element("ol", null, "progress-log");
    state.progress.forEach((line) => log.append(element("li", line)));
    card.append(log);
  }
  if (state.error) card.append(element("p", state.error, "status-error"));
  if (state.status === "succeeded") {
    const actions = element("div", null, "status-actions");
    if (state.download_url) {
      const download = element("a", "Скачать результат", "button button--primary");
      download.href = state.download_url;
      actions.append(download);
    }
    if (state.viewer_url) {
      const viewer = element("a", "Открыть переписки", "button button--secondary");
      viewer.href = state.viewer_url;
      actions.append(viewer);
    }
    card.append(actions);
  }
  node.append(card);
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

async function watchJob(job, node) {
  while (true) {
    const state = await api(`/api/jobs/${job.id}`);
    renderStatus(node, state);
    if (state.status === "succeeded" || state.status === "failed") return;
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
}

async function submitJob(event, url, body, statusId) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const status = document.getElementById(statusId);
  button.disabled = true;
  button.classList.add("is-loading");
  button.setAttribute("aria-busy", "true");
  renderStatus(status, { status: "queued", message: "Задание поставлено в очередь", progress: [] });
  try {
    const job = await api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body()),
    });
    renderStatus(status, job);
    await watchJob(job, status);
  } catch (error) {
    renderStatus(status, { status: "failed", error: error.message, message: "Не удалось запустить задание" });
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    button.removeAttribute("aria-busy");
  }
}

function syncLocalButton() {
  const file = document.getElementById("local-json").files[0];
  const button = document.getElementById("open-local");
  button.disabled = !sessionReady || !file;
  document.getElementById("local-file-title").textContent = file ? file.name : "Выбрать файл JSON";
  clearStatus(document.getElementById("local-status"));
}

function openLocalViewer() {
  const file = document.getElementById("local-json").files[0];
  const status = document.getElementById("local-status");
  if (!file) {
    renderStatus(status, { status: "failed", message: "Файл не выбран", error: "Сначала выберите JSON-файл." });
    return;
  }
  const reader = new FileReader();
  reader.onerror = () => renderStatus(status, { status: "failed", message: "Ошибка чтения", error: "Не удалось прочитать выбранный файл." });
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!data || data.schema_version !== 2 || !Array.isArray(data.tickets)) {
        throw new Error("Файл не является экспортом формата v2.");
      }
      sessionStorage.setItem("ispano-local-json", reader.result);
      location.assign("/viewer?local=1");
    } catch (error) {
      renderStatus(status, { status: "failed", message: "Некорректный файл", error: error.message || "Не удалось открыть JSON-файл." });
    }
  };
  reader.readAsText(file);
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST" });
  } finally {
    location.assign("/login");
  }
}

async function initialize() {
  const statuses = [document.getElementById("json-status"), document.getElementById("report-status")];
  try {
    const session = await api("/api/session");
    csrf = session.csrf;
    sessionReady = true;
    document.getElementById("user").textContent = session.username;
    if (session.ai_enabled) document.getElementById("ai-row").classList.remove("hidden");
    document.querySelectorAll("button[type=submit], #logout, #mobile-logout").forEach((button) => { button.disabled = false; });
    statuses.forEach(clearStatus);
    syncLocalButton();
  } catch (error) {
    statuses.forEach((status) => renderStatus(status, { status: "failed", message: "Сессия недоступна", error: error.message }));
  }
}

document.getElementById("json-form").addEventListener("submit", (event) => submitJob(event, "/api/jobs/json", () => ({ since: document.getElementById("since").value }), "json-status"));
document.getElementById("report-form").addEventListener("submit", (event) => submitJob(event, "/api/jobs/report", () => ({ ticket_id: Number(document.getElementById("ticket-id").value), use_ai: document.getElementById("use-ai").checked }), "report-status"));
document.getElementById("logout").addEventListener("click", logout);
document.getElementById("mobile-logout").addEventListener("click", logout);
document.getElementById("local-json").addEventListener("change", syncLocalButton);
document.getElementById("open-local").addEventListener("click", openLocalViewer);
initialize();
