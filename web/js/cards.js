import { api } from "./api.js";
import { el, safeHttpUrl, shorten } from "./ui.js";

export const STATUS_LABELS = {
  unseen: "Не просмотрено",
  planned: "Запланировано",
  studied: "Изучено",
  irrelevant: "Неактуально",
};
export const SOURCE_LABELS = {
  youtube: "YouTube",
  telegram: "Telegram",
  web: "Сайт",
  other: "Заметка",
};
const SOURCE_ICONS = {
  youtube: "img/source-youtube.svg",
  telegram: "img/source-telegram.svg",
  web: "img/source-web.svg",
  other: "img/source-note.svg",
};

const dateFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

export function formatDate(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : dateFormat.format(date);
}

export function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

// Фиксирует открытие оригинала. Сбой записи не должен мешать открытию ссылки.
export function trackOpen(id) {
  return api("POST", `/contents/${encodeURIComponent(id)}/open`).catch(() => null);
}

// Один обработчик на контейнер: ссылки «Открыть оригинал» помечены data-open-id
export function bindOpenTracking(root, onTracked) {
  const handler = (event) => {
    const link = event.target.closest("a[data-open-id]");
    if (!link || (event.type === "auxclick" && event.button !== 1)) return;
    trackOpen(link.dataset.openId).then(() => onTracked?.());
  };
  root.addEventListener("click", handler);
  root.addEventListener("auxclick", handler);
}

// Карточка материала в списке. Все строки с чужих сайтов попадают на страницу только как текст.
export function renderItem(item, categoryNames) {
  const source = item.source in SOURCE_LABELS ? item.source : "other";
  const status = item.status in STATUS_LABELS ? item.status : "unseen";
  const href = item.url ? safeHttpUrl(item.url) : null;
  const category = item.category_id != null ? categoryNames.get(item.category_id) : null;
  const itemUrl = `item.html?id=${encodeURIComponent(String(item.id))}`;

  const meta = el(
    "div",
    { class: "item-meta" },
    el(
      "span",
      { class: "source" },
      el("img", { attrs: { src: SOURCE_ICONS[source], alt: "", width: "18", height: "18" } }),
      el("span", { text: SOURCE_LABELS[source] }),
    ),
    href && el("span", { text: hostOf(href) }),
    el("span", { class: `chip chip-${status}`, text: STATUS_LABELS[status] }),
    category && el("span", { text: category }),
    el("span", { text: `Добавлено ${formatDate(item.created_at)}` }),
  );

  return el(
    "li",
    { class: "item" },
    meta,
    el("h3", { class: "item-title" }, el("a", { text: item.title, attrs: { href: itemUrl } })),
    item.description && el("p", { class: "item-text", text: item.description }),
    item.note && el("p", { class: "item-note", text: shorten(item.note, 400) }),
    href &&
      el(
        "p",
        { class: "item-links" },
        el("a", {
          text: "Открыть оригинал",
          attrs: {
            href,
            target: "_blank",
            rel: "noopener noreferrer",
            "data-open-id": String(item.id),
          },
        }),
      ),
  );
}