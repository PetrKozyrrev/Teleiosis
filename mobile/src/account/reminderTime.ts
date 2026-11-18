export function reminderInstant(value: string) {
  // Requiring an offset makes ambiguous and missing DST times explicit.
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new Error('Укажите дату и смещение, например 2026-12-01T10:00+03:00.');
  }
  const date = new Date(value);
  if (!Number.isFinite(date.getTime()) || date.getTime() <= Date.now() ||
      date.getTime() > Date.now() + 366 * 86400000) throw new Error('Укажите время в будущем в пределах года.');
  // Date parsing normalizes invalid month days, so compare in the supplied offset.
  const offset = value.endsWith('Z') ? 0 :
    (Number(value.slice(-5, -3)) * 60 + Number(value.slice(-2))) * (value.at(-6) === '-' ? -1 : 1);
  if (new Date(date.getTime() + offset * 60000).toISOString().slice(0, 16) !== value.slice(0, 16)) {
    throw new Error('Проверьте календарную дату.');
  }
  return date.toISOString();
}
