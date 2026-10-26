// Shared helpers for the storefront modules.
export const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";

export async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Something went wrong. Please try again.");
  }
  return data;
}

export const usd = (cents) =>
  "$" + (Number(cents || 0) / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export function setStatus(element, message, kind = "") {
  if (!element) return;
  element.textContent = message;
  element.className = "hint" + (kind ? " " + kind : "");
}
