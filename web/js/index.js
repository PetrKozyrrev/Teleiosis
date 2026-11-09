import { createLibrary } from "./library.js";
import { initQuickAdd } from "./quickadd.js";
import { initTopbar, requireUser } from "./session.js";
import { $, describeError, markReady, showError } from "./ui.js";

async function main() {
  const user = await requireUser();
  initTopbar(user);
  $("#main").hidden = false;
  markReady();

  // library используется внутри обработчика после создания, поэтому порядок безопасен
  const quickAdd = initQuickAdd({ onSaved: () => library.showNewest() });
  const library = createLibrary({ onCategories: quickAdd.setCategories });
  await library.start();
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});