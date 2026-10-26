// Order page: poll the status, run the countdown, offer the sandbox payment button.
import { api } from "./main.js";

const root = document.querySelector(".order");
if (root) {
  const orderNo = root.dataset.order;
  const statusEl = document.getElementById("order-status");
  const countdown = document.getElementById("countdown");
  const simulate = document.getElementById("simulate");
  const expiresAt = new Date(root.dataset.expires || Date.now());
  let settled = false;

  const label = (status) =>
    status.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

  function paint(status) {
    if (!statusEl) return;
    statusEl.textContent = label(status);
    statusEl.className = "status status-" + status;
    if (status !== "pending_payment" && timer) clearInterval(timer);
  }

  let timer = null;
  if (countdown) {
    const target = new Date(
      document.querySelector("[data-expires]")?.dataset.expires ||
        root.dataset.expires ||
        ""
    );
    const end = Number.isNaN(target.getTime()) ? null : target.getTime();
    timer = setInterval(() => {
      if (!end) return;
      const left = end - Date.now();
      if (left <= 0) {
        countdown.textContent = "expired";
        return;
      }
      const minutes = Math.floor(left / 60000);
      const seconds = Math.floor((left % 60000) / 1000);
      countdown.textContent = `${minutes}:${String(seconds).padStart(2, "0")}`;
    }, 1000);
  }

  async function poll() {
    if (settled) return;
    try {
      const data = await api(`/api/orders/${orderNo}`);
      paint(data.status);
      if (data.status !== "pending_payment") {
        settled = true;
        setTimeout(() => window.location.reload(), 700);
      }
    } catch (error) {
      // keep polling; a transient network error should not break the page
    }
  }

  simulate?.addEventListener("click", async () => {
    simulate.disabled = true;
    simulate.textContent = "Confirming…";
    try {
      await api(`/api/orders/${orderNo}/simulate-payment`, { method: "POST", body: {} });
      await poll();
    } catch (error) {
      simulate.disabled = false;
      simulate.textContent = "Simulate payment (sandbox)";
    }
  });

  setInterval(poll, 5000);
  poll();
}
