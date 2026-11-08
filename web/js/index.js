import { api } from "./api.js";
import { requireUser } from "./session.js";
import { $, describeError, showError } from "./ui.js";

async function main() {
  const user = await requireUser();
  $("#user-email").textContent = user.email ?? user.username ?? "";
  $("#main").hidden = false;

  $("#logout").addEventListener("click", async () => {
    try {
      await api("POST", "/auth/logout");
      location.replace("login.html");
    } catch (error) {
      showError($("#error"), describeError(error));
    }
  });
}

main().catch((error) => showError($("#error"), describeError(error)));