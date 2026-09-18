const app = document.getElementById("app");
const element = (tag, text, className) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined && text !== null) node.textContent = String(text); return node; };

function renderComment(comment) {
  const node = element("article", null, "chat-msg");
  node.append(element("div", `${comment.author || "Неизвестный автор"} · ${comment.date_raw || comment.occurred_at || ""}`, "meta"), element("div", comment.text || "", "chat-text"));
  if (Array.isArray(comment.events)) comment.events.forEach((event) => node.append(element("div", event, "meta")));
  return node;
}

function renderTicket(ticket) {
  const card = element("article", null, "ticket");
  const header = element("button", `#${ticket.id ?? ""} — ${ticket.name || "Без названия"}`, "ticket-header");
  const body = element("div", null, "ticket-body");
  header.type = "button";
  body.append(element("div", ticket.description || "Описание отсутствует.", "ticket-desc"), element("h2", "История"));
  if (Array.isArray(ticket.chat) && ticket.chat.length) ticket.chat.forEach((comment) => body.append(renderComment(comment))); else body.append(element("p", "Нет сообщений в чате."));
  header.addEventListener("click", () => card.classList.toggle("open"));
  card.append(header, body);
  return card;
}

async function loadViewer() {
  try {
    const params = new URLSearchParams(location.search);
    let data;
    if (params.get("local")) data = JSON.parse(sessionStorage.getItem("ispano-local-json") || "");
    else if (params.get("job")) { const response = await fetch(`/api/jobs/${params.get("job")}/download`); if (!response.ok) throw new Error(`HTTP ${response.status}`); data = await response.json(); }
    else throw new Error("Не указан источник JSON.");
    if (!data || data.schema_version !== 2 || !Array.isArray(data.tickets)) throw new Error("Файл не является экспортом формата v2.");
    app.replaceChildren();
    if (!data.tickets.length) app.append(element("p", "Тикетов нет."));
    data.tickets.forEach((ticket) => app.append(renderTicket(ticket)));
  } catch (error) { app.textContent = `Не удалось загрузить выгрузку: ${error.message}`; }
}

loadViewer();
