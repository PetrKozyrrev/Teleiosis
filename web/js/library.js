import { api } from "./api.js";
import { bindOpenTracking, renderItem } from "./cards.js";
import { redirectIfUnauthorized } from "./session.js";
import { $, describeError, el, hideMessage, showError } from "./ui.js";

const PAGE_SIZE = 20;
const SEARCH_DELAY_MS = 300;

export function createLibrary() {
  const controls = {
    q: $("#filter-q"),
    status: $("#filter-status"),
    source: $("#filter-source"),
    category: $("#filter-category"),
    sort: $("#filter-sort"),
  };
  const list = $("#items");
  const count = $("#count");
  const empty = $("#empty");
  const more = $("#more");
  const retry = $("#retry");
  const error = $("#list-error");

  const state = { items: [], total: 0, seq: 0, loading: false, lastReset: true, categories: new Map() };
  let timer = null;

  const filters = () => ({
    q: controls.q.value.trim(),
    status: controls.status.value,
    source: controls.source.value,
    category: controls.category.value,
    sort: controls.sort.value,
  });
  const isFiltered = () => {
    const f = filters();
    return Boolean(f.q || f.status || f.source || f.category);
  };

  function queryString(offset) {
    const f = filters();
    const params = new URLSearchParams({
      sort: f.sort,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (f.q) params.set("q", f.q);
    if (f.status) params.set("status", f.status);
    if (f.source) params.set("source", f.source);
    if (f.category === "none") params.set("uncategorized", "true");
    else if (f.category) params.set("category_id", f.category);
    return params.toString();
  }

  function render() {
    list.replaceChildren(...state.items.map((item) => renderItem(item, state.categories)));
    list.setAttribute("aria-busy", String(state.loading));

    const showEmpty = !state.loading && state.items.length === 0 && error.hidden;
    empty.hidden = !showEmpty;
    if (showEmpty) {
      const filtered = isFiltered();
      $("#empty-title").textContent = filtered ? "Ничего не найдено" : "Пока пусто";
      $("#empty-text").textContent = filtered
        ? "Измените запрос или фильтры."
        : "Вставьте ссылку или напишите заметку в поле выше.";
      $("#reset-filters").hidden = !filtered;
    }

    more.hidden = state.items.length >= state.total;
    more.disabled = state.loading;
    retry.hidden = error.hidden;

    if (state.loading && state.items.length === 0) count.textContent = "Загружаю…";
    else if (state.total) count.textContent = `${isFiltered() ? "Найдено" : "Материалов"}: ${state.total}`;
    else count.textContent = "";
  }

  // reset: true загружает первую страницу заново, false добавляет следующую
  async function load(reset) {
    const seq = ++state.seq; // ответ на устаревший запрос будет отброшен
    state.lastReset = reset;
    state.loading = true;
    hideMessage(error);
    if (reset) {
      state.items = [];
      state.total = 0;
    }
    render();
    try {
      const page = await api("GET", `/contents?${queryString(reset ? 0 : state.items.length)}`);
      if (seq !== state.seq) return;
      state.items = reset ? page.items : state.items.concat(page.items);
      state.total = page.total;
    } catch (e) {
      if (seq !== state.seq || redirectIfUnauthorized(e)) return;
      showError(error, describeError(e));
    } finally {
      if (seq === state.seq) {
        state.loading = false;
        render();
      }
    }
  }

  async function loadCategories() {
    try {
      const categories = await api("GET", "/categories");
      state.categories = new Map(categories.map((c) => [c.id, c.name]));
      for (const c of categories) {
        controls.category.append(el("option", { text: c.name, attrs: { value: String(c.id) } }));
      }
    } catch {
      // фильтр категорий останется с двумя пунктами, библиотека работает
    }
  }

  function resetFilters() {
    controls.q.value = "";
    controls.status.value = "";
    controls.source.value = "";
    controls.category.value = "";
    controls.sort.value = "newest";
  }

  bindOpenTracking(list);
  $("#filters").addEventListener("submit", (event) => event.preventDefault());
  controls.q.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => load(true), SEARCH_DELAY_MS);
  });
  for (const name of ["status", "source", "category", "sort"]) {
    controls[name].addEventListener("change", () => load(true));
  }
  more.addEventListener("click", () => load(false));
  retry.addEventListener("click", () => load(state.lastReset));
  $("#reset-filters").addEventListener("click", () => {
    resetFilters();
    load(true);
  });

  return {
    async start() {
      await loadCategories();
      await load(true);
    },
    // После сохранения: фильтры сбрасываются, чтобы новый материал был виден
    async showNewest() {
      clearTimeout(timer);
      resetFilters();
      await load(true);
    },
  };
}