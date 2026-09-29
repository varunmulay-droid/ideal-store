const state = { services: [], chatOpen: false };

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function formatPrice(service) {
  if (!service.price || service.price_type === "on_request") return "On request";
  return `₹${Number(service.price).toLocaleString("en-IN")}${service.price_type === "starting_from" ? " onwards" : ""}`;
}

function renderServices() {
  const grid = $("#service-grid");
  const select = $("#service-select");
  if (!state.services.length) {
    grid.innerHTML = '<div class="loading-card">Services are being refreshed. Please call us for today’s menu.</div>';
    return;
  }
  grid.innerHTML = state.services.map((service, index) => `
    <article class="service-card">
      <div><span class="service-number">${String(index + 1).padStart(2, "0")} / ${escapeHtml(service.category)}</span>
      <h3>${escapeHtml(service.name)}</h3>
      <p>${escapeHtml(service.description)}</p></div>
      <div class="service-foot"><span class="service-price"><small>${service.duration_minutes ? `${service.duration_minutes} min · ` : ""}starting</small>${formatPrice(service)}</span>
      <button class="circle-button choose-service" data-service-id="${service.id}" aria-label="Enquire about ${escapeHtml(service.name)}">↗</button></div>
    </article>`).join("");
  select.innerHTML = '<option value="">Select a service</option>' + state.services.map((service) =>
    `<option value="${service.id}">${escapeHtml(service.name)}</option>`).join("");
  bindServiceButtons();
}

function bindServiceButtons() {
  $$(".choose-service").forEach((button) => button.addEventListener("click", () => {
    const service = button.dataset.serviceId
      ? state.services.find((item) => String(item.id) === button.dataset.serviceId)
      : state.services.find((item) => item.name === button.dataset.serviceName);
    if (service) $("#service-select").value = String(service.id);
    $("#booking").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}

async function loadServices() {
  try {
    const response = await fetch("/api/services");
    if (!response.ok) throw new Error("Services unavailable");
    state.services = await response.json();
    renderServices();
  } catch {
    $("#service-grid").innerHTML = '<div class="loading-card">Please refresh or call 07383 099 084 for our current service menu.</div>';
  }
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 4200);
}

async function submitBooking(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const status = form.querySelector(".form-status");
  const data = Object.fromEntries(new FormData(form).entries());
  data.service_id = data.service_id ? Number(data.service_id) : null;
  if (!data.appointment_date) data.appointment_date = null;
  if (!data.preferred_time) data.preferred_time = null;
  button.disabled = true;
  button.innerHTML = "Sending request…";
  status.textContent = "";
  try {
    const response = await fetch("/api/appointments", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Please check your details.");
    status.textContent = result.message;
    form.reset();
    showToast("Appointment request received.");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = "Send appointment request <span>↗</span>";
  }
}

function addMessage(text, type) {
  const message = document.createElement("div");
  message.className = `message ${type}`;
  message.textContent = text;
  $("#chat-messages").appendChild(message);
  $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight;
}

async function sendChat(message) {
  const text = message.trim();
  if (!text) return;
  addMessage(text, "user");
  $("#chat-input").value = "";
  try {
    const response = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text })
    });
    const result = await response.json();
    if (!response.ok) throw new Error("I’m having a small connection issue.");
    addMessage(result.reply, "bot");
    if (result.service_id) $("#service-select").value = String(result.service_id);
    if (result.next_action === "booking") {
      $("#booking").scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (result.next_action === "location") {
      $("#contact").scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (result.next_action === "services") {
      $("#services").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (error) {
    addMessage(error.message, "bot");
  }
}

function setupChat() {
  const panel = $("#chat-panel");
  const toggle = (open) => {
    state.chatOpen = open;
    panel.classList.toggle("open", open);
    panel.setAttribute("aria-hidden", String(!open));
    if (open) window.setTimeout(() => $("#chat-input").focus(), 250);
  };
  $("#chat-launcher").addEventListener("click", () => toggle(!state.chatOpen));
  $("#chat-close").addEventListener("click", () => toggle(false));
  $("#chat-form").addEventListener("submit", (event) => { event.preventDefault(); sendChat($("#chat-input").value); });
  $$(".chat-suggestions button").forEach((button) => button.addEventListener("click", () => sendChat(button.dataset.message)));
}

function setupNav() {
  const toggle = $(".menu-toggle");
  const links = $(".nav-links");
  toggle.addEventListener("click", () => {
    const open = links.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  $$(".nav-links a").forEach((link) => link.addEventListener("click", () => links.classList.remove("open")));
}

$("#booking-form").addEventListener("submit", submitBooking);
setupChat();
setupNav();
loadServices();