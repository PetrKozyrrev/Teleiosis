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

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

// Карточка материала. Все строки с чужих сайтов попадают на страницу только как текст.
export function renderItem(item, categoryNames) {
  const source = item.source in SOURCE_LABELS ? item.source : "other";
  const status = item.status in STATUS_LABELS ? item.status : "unseen";
  const href = item.url ? safeHttpUrl(item.url) : null;
  const category = item.category_id != null ? categoryNames.get(item.category_id) : null;

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
    el("span", { text: `Добавлено ${dateFormat.format(new Date(item.created_at))}` }),
  );

  const title = href
    ? el("a", { text: item.title, attrs: { href, target: "_blank", rel: "noopener noreferrer" } })
    : item.title;

  return el(
    "li",
    { class: "item" },
    meta,
    el("h3", { class: "item-title", text: href ? undefined : item.title }, href ? title : null),
    item.description && el("p", { class: "item-text", text: item.description }),
    item.note && el("p", { class: "item-note", text: shorten(item.note, 400) }),
  );
}