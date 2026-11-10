import { api, ApiError } from "./api.js";
import { initTopbar, redirectIfUnauthorized, requireUser } from "./session.js";
import {
  $, attachPasswordToggle, describeError, el, hideMessage, markReady, onSubmit,
  passwordProblem, showError, showInfo,
} from "./ui.js";

// Удобный список. Сервер принимает любой корректный пояс IANA, но в списке только частые.
const ZONES = [
  ["Europe/Kaliningrad", "Калининград"],
  ["Europe/Moscow", "Москва"],
  ["Europe/Samara", "Самара"],
  ["Asia/Yekaterinburg", "Екатеринбург"],
  ["Asia/Omsk", "Омск"],
  ["Asia/Novosibirsk", "Новосибирск"],
  ["Asia/Krasnoyarsk", "Красноярск"],
  ["Asia/Irkutsk", "Иркутск"],
  ["Asia/Yakutsk", "Якутск"],
  ["Asia/Vladivostok", "Владивосток"],
  ["Asia/Magadan", "Магадан"],
  ["Asia/Kamchatka", "Камчатка"],
  ["Europe/Minsk", "Минск"],
  ["Asia/Almaty", "Алматы"],
  ["Asia/Tashkent", "Ташкент"],
  ["Asia/Yerevan", "Ереван"],
  ["Asia/Tbilisi", "Тбилиси"],
  ["Asia/Baku", "Баку"],
  ["UTC", "UTC"],
];

let user = null;

const form = $("#settings-form");
const settingsError = $("#settings-error");
const settingsInfo = $("#settings-info");
const enabledInput = $("#reminders-enabled");
const timeInput = $("#reminder-time");
const zoneSelect = $("#timezone");

function ensureZoneOption(zone) {
  const known = [...zoneSelect.options].some((option) => option.value === zone);
  if (!known) zoneSelect.append(el("option", { text: zone, attrs: { value: zone } }));
}

function fillSettings() {
  zoneSelect.replaceChildren(
    ...ZONES.map(([value, label]) => el("option", { text: label, attrs: { value } })),
  );
  ensureZoneOption(user.timezone);
  zoneSelect.value = user.timezone;
  enabledInput.checked = user.reminders_enabled;
  timeInput.value = user.reminder_time;
}

function fillEmail() {
  if (!user.email) {
    $("#email-status").textContent = "Адрес не указан.";
    return;
  }
  $("#email-status").textContent = user.email_verified_at
    ? `${user.email}: подтверждён.`
    : `${user.email}: не подтверждён.`;
  $("#email-hint").textContent = user.email_verified_at
    ? "Напоминания будут приходить на этот адрес."
    : "Напоминания приходят только на подтверждённый адрес. Отправьте письмо кнопкой в плашке вверху страницы.";
}

$("#detect-timezone").addEventListener("click", () => {
  hideMessage(settingsError);
  let zone;
  try {
    zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    zone = undefined;
  }
  if (!zone) {
    showError(settingsError, "Браузер не сообщил часовой пояс. Выберите его из списка.");
    return;
  }
  ensureZoneOption(zone);
  zoneSelect.value = zone;
  showInfo(settingsInfo, `Определён пояс: ${zone}. Нажмите «Сохранить».`);
});

onSubmit(form, async () => {
  hideMessage(settingsError);
  hideMessage(settingsInfo);
  if (!timeInput.value) {
    showError(settingsError, "Укажите время подборки.");
    timeInput.focus();
    return;
  }
  const changes = {};
  if (enabledInput.checked !== user.reminders_enabled) changes.reminders_enabled = enabledInput.checked;
  if (timeInput.value !== user.reminder_time) changes.reminder_time = timeInput.value;
  if (zoneSelect.value !== user.timezone) changes.timezone = zoneSelect.value;
  if (Object.keys(changes).length === 0) {
    showInfo(settingsInfo, "Изменений нет.");
    return;
  }
  try {
    user = await api("PATCH", "/me/settings", changes);
    fillSettings();
    showInfo(settingsInfo, "Настройки сохранены.");
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    showError(
      settingsError,
      describeError(e, {
        422: "Не получилось сохранить. Возможно, этот часовой пояс не поддерживается: выберите другой из списка.",
      }),
    );
  }
});

const passwordForm = $("#password-form");
const passwordError = $("#password-error");
const passwordInfo = $("#password-info");
attachPasswordToggle($("#toggle-current"), $("#current-password"));
attachPasswordToggle($("#toggle-new"), $("#new-password"));

onSubmit(passwordForm, async () => {
  hideMessage(passwordError);
  hideMessage(passwordInfo);
  const current = $("#current-password").value;
  const next = $("#new-password").value;
  if (!current) {
    showError(passwordError, "Введите текущий пароль.");
    $("#current-password").focus();
    return;
  }
  const problem = passwordProblem(next);
  if (problem) {
    showError(passwordError, problem);
    $("#new-password").focus();
    return;
  }
  if (next === current) {
    showError(passwordError, "Новый пароль должен отличаться от текущего.");
    $("#new-password").focus();
    return;
  }
  try {
    await api("POST", "/auth/change-password", { current_password: current, new_password: next });
    passwordForm.reset();
    showInfo(passwordInfo, "Пароль изменён. На остальных устройствах нужно войти заново.");
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    showError(
      passwordError,
      describeError(e, {
        400: "Текущий пароль неверный.",
        422: "Новый пароль должен отличаться от текущего и быть от 10 до 128 символов.",
      }),
    );
    if (e instanceof ApiError && e.status === 400) $("#current-password").focus();
  }
});

async function main() {
  user = await requireUser();
  initTopbar(user);
  $("#main").hidden = false;
  markReady();
  fillSettings();
  fillEmail();
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});