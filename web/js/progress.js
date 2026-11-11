import { initTopbar, redirectIfUnauthorized, requireUser } from "./session.js";
import { loadStats, percent } from "./stats.js";
import { $, describeError, el, markReady, showError } from "./ui.js";

const dayFormat = new Intl.DateTimeFormat("ru-RU", {
  weekday: "short",
  day: "numeric",
  month: "short",
});

// "2026-11-10" -> локальная дата без сдвига часового пояса браузера
function formatDay(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return dayFormat.format(new Date(year, month - 1, day));
}

function renderTotals(stats) {
  $("#t-total").textContent = String(stats.total);
  $("#t-studied").textContent = String(stats.by_status.studied);
  $("#t-planned").textContent = String(stats.by_status.planned);
  $("#t-unseen").textContent = String(stats.by_status.unseen);
  $("#t-irrelevant").textContent = String(stats.by_status.irrelevant);
}

function renderStudied(stats) {
  const bar = $("#studied-bar");
  const denominator = stats.total - stats.by_status.irrelevant;
  if (denominator === 0) {
    $("#studied-text").textContent = "Пока нечего считать: все материалы отмечены как неактуальные.";
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  bar.max = denominator;
  bar.value = stats.by_status.studied;
  $("#studied-text").textContent =
    `Изучено ${stats.by_status.studied} из ${denominator} (${percent(stats.studied_share)}%). ` +
    "Неактуальные материалы не считаются.";
}

function renderReturns(stats) {
  const bar = $("#returns-bar");
  if (stats.with_url === 0) {
    $("#returns-text").textContent = "Пока нет материалов со ссылкой.";
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  bar.max = stats.with_url;
  bar.value = stats.opened;
  $("#returns-text").textContent =
    `Вы открывали ${stats.opened} из ${stats.with_url} материалов со ссылкой (${percent(stats.return_share)}%).`;
}

function renderWeek(stats) {
  $("#week-text").textContent = `Добавлено: ${stats.added_7d}. Изучено: ${stats.studied_7d}.`;
  $("#days-body").replaceChildren(
    ...stats.days.map((day) =>
      el(
        "tr",
        {},
        el("th", { text: formatDay(day.day), attrs: { scope: "row" } }),
        el("td", { text: String(day.added) }),
        el("td", { text: String(day.studied) }),
      ),
    ),
  );
}

function renderTopics(stats) {
  $("#topics-empty").hidden = stats.top_categories.length > 0;
  $("#topics").replaceChildren(
    ...stats.top_categories.map((category) =>
      el(
        "li",
        {},
        el("a", {
          text: category.name,
          attrs: { href: `./?category=${encodeURIComponent(String(category.id))}` },
        }),
        el("span", { text: ` — ${category.count}` }),
      ),
    ),
  );
}

async function main() {
  const user = await requireUser();
  initTopbar(user);
  $("#main").hidden = false;
  markReady();

  let stats;
  try {
    stats = await loadStats();
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    showError($("#stats-error"), describeError(e));
    return;
  }
  if (stats.total === 0) {
    $("#empty").hidden = false;
    return;
  }
  renderTotals(stats);
  renderStudied(stats);
  renderReturns(stats);
  renderWeek(stats);
  renderTopics(stats);
  $("#content").hidden = false;
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});