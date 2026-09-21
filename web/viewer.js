const app = document.getElementById("app");
const ticketCount = document.getElementById("ticket-count");

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function displayDate(value) {
  if (!value) return "Не указано";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function renderComment(comment) {
  const item = element("li", null, "timeline-item");
  const message = element("article", null, "chat-msg");
  const head = element("header", null, "chat-msg__head");
  head.append(element("span", comment.author || "Неизвестный автор", "chat-author"));
  head.append(element("time", displayDate(comment.date_raw || comment.occurred_at), "meta"));
  message.append(head, element("div", comment.text || "Текст сообщения отсутствует.", "chat-text"));
  if (Array.isArray(comment.events) && comment.events.length) {
    const events = element("div", null, "chat-events");
    comment.events.forEach((event) => events.append(element("div", event)));
    message.append(events);
  }
  item.append(message);
  return item;
}

function ticketMeta(label, value) {
  const item = element("div", null, "ticket-overview__item");
  item.append(element("span", label, "ticket-overview__label"), element("span", value, "ticket-overview__value"));
  return item;
}

function renderTicket(ticket, index) {
  const card = element("article", null, "ticket");
  const bodyId = `ticket-details-${index}`;
  const comments = Array.isArray(ticket.chat) ? ticket.chat : [];
  const header = element("button", null, "ticket-summary");
  header.type = "button";
  header.setAttribute("aria-expanded", "false");
  header.setAttribute("aria-controls", bodyId);
  const main = element("span", null, "ticket-summary__main");
  main.append(element("span", `Тикет #${ticket.id ?? "—"}`, "ticket-summary__id"), element("span", ticket.name || "Без названия", "ticket-summary__title"));
  const meta = element("span", null, "ticket-summary__meta");
  meta.append(element("span", `Изменён: ${displayDate(ticket.changed_at)}`), element("span", `Сообщений: ${comments.length}`));
  if (ticket.status_id !== null && ticket.status_id !== undefined) meta.append(element("span", `Статус: ${ticket.status_id}`));
  main.append(meta);
  header.append(main, element("span", null, "ticket-summary__toggle"));

  const body = element("div", null, "ticket-body");
  body.id = bodyId;
  const overview = element("section", null, "ticket-overview");
  overview.append(ticketMeta("Описание", ticket.description || "Описание отсутствует."), ticketMeta("Создан", displayDate(ticket.created_at)), ticketMeta("Изменён", displayDate(ticket.changed_at)));
  const timelineSection = element("section");
  timelineSection.append(element("h2", "История переписки", "timeline-heading"));
  if (comments.length) {
    const timeline = element("ol", null, "timeline");
    comments.forEach((comment) => timeline.append(renderComment(comment)));
    timelineSection.append(timeline);
  } else {
    timelineSection.append(element("p", "В этой выгрузке нет сообщений.", "viewer-message"));
  }
  body.append(overview, timelineSection);
  header.addEventListener("click", () => {
    const opened = card.classList.toggle("open");
    header.setAttribute("aria-expanded", String(opened));
  });
  card.append(header, body);
  return card;
}

async function loadViewer() {
  try {
    const params = new URLSearchParams(location.search);
    let data;
    if (params.get("local")) data = JSON.parse(sessionStorage.getItem("ispano-local-json") || "");
    else if (params.get("job")) {
      const response = await fetch(`/api/jobs/${params.get("job")}/download`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } else throw new Error("Не указан источник JSON.");
    if (!data || data.schema_version !== 2 || !Array.isArray(data.tickets)) throw new Error("Файл не является экспортом формата v2.");
    app.replaceChildren();
    app.removeAttribute("aria-busy");
    ticketCount.textContent = `Тикетов: ${data.tickets.length}`;
    if (!data.tickets.length) app.append(element("p", "В выбранной выгрузке нет тикетов.", "viewer-message"));
    data.tickets.forEach((ticket, index) => app.append(renderTicket(ticket, index)));
  } catch (error) {
    app.replaceChildren(element("p", `Не удалось загрузить выгрузку: ${error.message}`, "viewer-message viewer-message--error"));
    app.removeAttribute("aria-busy");
  }
}

loadViewer();
