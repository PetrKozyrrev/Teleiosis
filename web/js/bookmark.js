import { initTopbar, requireUser } from "./session.js";
import { $, describeError, markReady, showError, showInfo } from "./ui.js";

// Код закладки. noopener: страница, на которой нажали закладку (она может быть
// чужой), не получает доступа к окну Teleiosis и не может его перенаправить.
function bookmarkletCode() {
  const target = `${location.origin}/app/add.html`;
  return (
    "javascript:(function(){" +
    `var u=${JSON.stringify(target)}+'#url='+encodeURIComponent(location.href)` +
    "+'&title='+encodeURIComponent(document.title);" +
    "window.open(u,'_blank','noopener,noreferrer,width=520,height=680');})();"
  );
}

async function main() {
  const user = await requireUser();
  initTopbar(user);
  $("#main").hidden = false;
  markReady();

  const link = $("#bookmarklet");
  link.setAttribute("href", bookmarkletCode());
  // Нажатие здесь заблокировала бы политика безопасности: закладку нужно перетащить
  link.addEventListener("click", (event) => {
    event.preventDefault();
    showInfo($("#info"), "Не нажимайте на кнопку здесь, а перетащите её на панель закладок браузера.");
  });
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});