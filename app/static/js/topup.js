// Top-up flow: verify the player, pick a pack, apply a coupon, create the order.
import { api, usd, setStatus } from "./main.js";

const root = document.querySelector(".topup");
if (root) {
  const game = root.dataset.game;
  const playerInput = document.getElementById("player-id");
  const serverInput = document.getElementById("server");
  const checkButton = document.getElementById("check-player");
  const playerStatus = document.getElementById("player-status");
  const productInputs = [...document.querySelectorAll('input[name="product_id"]')];
  const couponInput = document.getElementById("coupon");
  const couponButton = document.getElementById("apply-coupon");
  const couponStatus = document.getElementById("coupon-status");
  const payButton = document.getElementById("pay");
  const payStatus = document.getElementById("pay-status");

  const state = { nickname: "", discount: 0, coupon: "", verified: false };

  const selected = () => productInputs.find((input) => input.checked);

  function render() {
    const product = selected();
    const subtotal = product ? Number(product.dataset.price) : 0;
    document.getElementById("sum-product").textContent =
      product ? product.closest(".product").querySelector("strong").textContent : "—";
    document.getElementById("sum-subtotal").textContent = usd(subtotal);
    document.getElementById("sum-discount").textContent =
      state.discount > 0 ? "−" + usd(state.discount) : "—";
    document.getElementById("sum-total").textContent = usd(subtotal - state.discount);
    document.getElementById("sum-player").textContent =
      state.verified ? `${state.nickname} (${playerInput.value.trim()})` : "—";
  }

  function resetVerification() {
    state.verified = false;
    state.nickname = "";
    render();
  }

  async function verifyPlayer() {
    const playerId = playerInput.value.trim();
    resetVerification();
    if (!playerId) {
      setStatus(playerStatus, "Enter your Player ID first.", "err");
      return;
    }
    checkButton.disabled = true;
    setStatus(playerStatus, "Checking with the game…");
    try {
      const data = await api("/api/players/check", {
        method: "POST",
        body: { game, player_id: playerId, server: serverInput?.value || "" },
      });
      state.nickname = data.nickname;
      state.verified = true;
      setStatus(playerStatus, `Nickname: ${data.nickname}`, "ok");
    } catch (error) {
      setStatus(playerStatus, error.message, "err");
    } finally {
      checkButton.disabled = false;
      render();
    }
  }

  async function applyCoupon() {
    const code = couponInput.value.trim();
    const product = selected();
    if (!code) {
      state.discount = 0;
      state.coupon = "";
      setStatus(couponStatus, "", "");
      render();
      return;
    }
    if (!product) {
      setStatus(couponStatus, "Choose a pack first.", "err");
      return;
    }
    couponButton.disabled = true;
    try {
      const data = await api("/api/coupons/check", {
        method: "POST",
        body: { code, subtotal_cents: Number(product.dataset.price) },
      });
      state.discount = data.discount_cents;
      state.coupon = data.code;
      setStatus(couponStatus, `${data.code} applied: −${usd(data.discount_cents)}`, "ok");
    } catch (error) {
      state.discount = 0;
      state.coupon = "";
      setStatus(couponStatus, error.message, "err");
    } finally {
      couponButton.disabled = false;
      render();
    }
  }

  async function pay() {
    const product = selected();
    if (!state.verified) {
      setStatus(payStatus, "Check your Player ID before paying.", "err");
      return;
    }
    if (!product) {
      setStatus(payStatus, "Choose a pack.", "err");
      return;
    }
    payButton.disabled = true;
    setStatus(payStatus, "Creating your order…");
    try {
      const data = await api("/api/orders", {
        method: "POST",
        body: {
          game,
          product_id: Number(product.value),
          player_id: playerInput.value.trim(),
          server: serverInput?.value || "",
          coupon: state.coupon,
          player_name: state.nickname,
        },
      });
      window.location.href = data.status_url;
    } catch (error) {
      setStatus(payStatus, error.message, "err");
      payButton.disabled = false;
    }
  }

  checkButton?.addEventListener("click", verifyPlayer);
  couponButton?.addEventListener("click", applyCoupon);
  payButton?.addEventListener("click", pay);
  productInputs.forEach((input) => input.addEventListener("change", () => {
    state.discount = 0;
    state.coupon = "";
    couponInput.value = "";
    setStatus(couponStatus, "", "");
    render();
  }));
  playerInput?.addEventListener("input", resetVerification);
  serverInput?.addEventListener("change", resetVerification);
  playerInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      verifyPlayer();
    }
  });

  render();
}
