// Единственное место, где сайт обращается к серверу.
// Не задавайте mode: "same-origin": вместе с Referrer-Policy: no-referrer браузер
// отправит Origin: null, и сервер отклонит изменяющий запрос (проверка Origin).

export class ApiError extends Error {
  constructor(status, retryAfter = null) {
    super(`API error ${status}`);
    this.status = status; // 0 = нет связи с сервером
    this.retryAfter = retryAfter; // секунды из заголовка Retry-After
  }
}

export async function api(method, path, body) {
  const init = { method, credentials: "same-origin", cache: "no-store", headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0);
  }
  if (!response.ok) {
    const wait = Number.parseInt(response.headers.get("Retry-After") ?? "", 10);
    throw new ApiError(response.status, Number.isFinite(wait) ? wait : null);
  }
  if (response.status === 204) return null;
  return response.json();
}