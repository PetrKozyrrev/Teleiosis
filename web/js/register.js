import { api } from "./api.js";
import { redirectIfSignedIn } from "./session.js";
import {
  $, attachPasswordToggle, describeError, hideMessage, onSubmit, passwordProblem, showError,
} from "./ui.js";

redirectIfSignedIn();

const form = $("#register-form");
const error = $("#error");
attachPasswordToggle($("#toggle-password"), $("#password"));

// Пояс браузера нужен, чтобы напоминания приходили в удобное местное время.
// Если определить не получилось, поле не отправляется (сервер поставит UTC).
function browserTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

onSubmit(form, async () => {
  hideMessage(error);
  const password = $("#password").value;
  const problem = passwordProblem(password);
  if (problem) {
    showError(error, problem);
    $("#password").focus();
    return;
  }
  try {
    await api("POST", "/auth/register", {
      email: $("#email").value.trim(),
      password,
      consent: $("#consent").checked,
      timezone: browserTimeZone(),
    });
    location.replace("./");
  } catch (e) {
    showError(
      error,
      describeError(e, { 409: "Этот e-mail уже зарегистрирован. Войдите или восстановите доступ." }),
    );
  }
});