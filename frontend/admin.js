const sessionKey = "mitalli_admin_access_key";
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function key() {
  return sessionStorage.getItem(sessionKey);
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3500);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Admin-Key": key(), ...(options.headers || {}) }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Request failed");
  return body;
}

function renderStats(summary) {
  const stats = [
    ["Total requests", summary.total_appointments],
    ["New / pending", summary.pending],
    ["Contacted", summary.contacted],
    ["Confirmed", summary.confirmed],
    ["Completed", summary.completed],
    ["Total leads", summary.total_leads]
  ];
  $("#stat-grid").innerHTML = stats.map(([label, value]) =>
    `<div class="stat-card"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function formatSlot(appointment) {
  const date = appointment.appointment_date
    ? new Date(`${appointment.appointment_date}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
    : "Date not set";
  return `${date}<span class="subtle">${appointment.preferred_time ? ` · ${appointment.preferred_time}` : " · Time not set"}</span>`;
}

function renderAppointments(items) {
  const body = $("#appointments-body");
  if (!items.length) {
    body.innerHTML = '<tr><td class="empty-row" colspan="5">No appointment requests yet.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => `
    <tr>
      <td><span class="customer-name">${escapeHtml(item.customer_name)}</span><span class="customer-phone">${escapeHtml(item.phone)}</span></td>
      <td>${escapeHtml(item.service)}</td>
      <td>${formatSlot(item)}</td>
      <td class="message-cell">${escapeHtml(item.message || "—")}</td>
      <td><select class="status-select" data-appointment-id="${item.id}">
        ${["pending", "contacted", "confirmed", "completed", "cancelled"].map((status) =>
          `<option value="${status}" ${status === item.status ? "selected" : ""}>${status}</option>`).join("")}
      </select></td>
    </tr>`).join("");
  document.querySelectorAll(".status-select").forEach((select) => {
    select.addEventListener("change", async () => {
      try {
        await request(`/api/admin/appointments/${select.dataset.appointmentId}`, {
          method: "PATCH", body: JSON.stringify({ status: select.value })
        });
        showToast("Appointment status updated.");
        await loadDashboard();
      } catch (error) {
        showToast(error.message);
      }
    });
  });
}

function renderLeads(items) {
  const body = $("#leads-body");
  if (!items.length) {
    body.innerHTML = '<tr><td class="empty-row" colspan="5">No leads yet.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => `
    <tr>
      <td><span class="customer-name">${escapeHtml(item.name || "Unknown")}</span><span class="customer-phone">${escapeHtml(item.phone || "No phone")}</span></td>
      <td>${escapeHtml(item.service_interest || "General enquiry")}</td>
      <td class="subtle">${escapeHtml(item.source)}</td>
      <td class="message-cell">${escapeHtml(item.message || "—")}</td>
      <td class="subtle">${escapeHtml(item.status)}</td>
    </tr>`).join("");
}

async function loadDashboard() {
  try {
    const [summary, appointments, leads] = await Promise.all([
      request("/api/admin/summary"),
      request("/api/admin/appointments"),
      request("/api/admin/leads")
    ]);
    renderStats(summary);
    renderAppointments(appointments);
    renderLeads(leads);
  } catch (error) {
    if (error.message.includes("authentication")) logout();
    showToast(error.message);
  }
}

function showDashboard() {
  $("#login-view").hidden = true;
  $("#dashboard-view").hidden = false;
  loadDashboard();
}

function logout() {
  sessionStorage.removeItem(sessionKey);
  $("#dashboard-view").hidden = true;
  $("#login-view").hidden = false;
  $("#access-key").value = "";
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#access-key");
  const error = $("#login-error");
  error.textContent = "";
  try {
    await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_key: input.value })
    }).then(async (response) => {
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Login failed");
      return body;
    });
    sessionStorage.setItem(sessionKey, input.value);
    showDashboard();
  } catch (loginError) {
    error.textContent = loginError.message;
  }
});

$("#refresh-button").addEventListener("click", loadDashboard);
$("#logout-button").addEventListener("click", logout);
if (key()) showDashboard();