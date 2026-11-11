import { createLibrary } from "./library.js";
import { initQuickAdd } from "./quickadd.js";
import { initTopbar, requireUser } from "./session.js";
import { loadStats, pendingCount } from "./stats.js";
import { $, describeError, el, markReady, showError } from "./ui.js";

const strip = $("#stats-strip");

// Строка над библиотекой. Статистика не обязательна: при любой ошибке строка скрыта.
async function refreshStrip() {
  try {
    const stats = await loadStats();
    if (stats.total === 0) {
      strip.hidden = true;
      return;
    }
    strip.replaceChildren(
      document.createTextNode(
        `Не изучено: ${pendingCount(stats)} · Изучено: ${stats.by_status.studied} · `,
      ),
      el("a", { text: "Подробнее", attrs: { href: "progress.html" } }),
    );
    strip.hidden = false;
  } catch {
    strip.hidden = true;
  }
}

async function main() {
  const user = await requireUser();
  initTopbar(user);
  $("#main").hidden = false;
  markReady();

  // library используется внутри обработчика после создания, поэтому порядок безопасен
  const quickAdd = initQuickAdd({
    onSaved: async () => {
      await library.showNewest();
      await refreshStrip();
    },
  });
  const library = createLibrary({ onCategories: quickAdd.setCategories });
  await Promise.all([library.start(), refreshStrip()]);
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});