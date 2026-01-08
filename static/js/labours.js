/* =========================================================
   Labour Monthly Summary - CLEAN FINAL VERSION
   ========================================================= */

const API_BASE = document.body.dataset.apiBase;


let CURRENT_LABOUR_ID = null;

/* ---------- DOM READY ---------- */
document.addEventListener("DOMContentLoaded", function () {

  // Click on labour name
  document.querySelectorAll(".labour-link").forEach(el => {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      CURRENT_LABOUR_ID = this.dataset.labourId;
      openModalWithCurrentMonth();
    });
  });

  // Month selector change
  const monthInput = document.getElementById("month-selector");
  if (monthInput) {
    monthInput.addEventListener("change", function () {
      if (!CURRENT_LABOUR_ID) return;
      loadLabourSummary(CURRENT_LABOUR_ID, this.value);
    });
  }

});


/* ---------- OPEN MODAL ---------- */
function openModalWithCurrentMonth() {
  const today = new Date();
  const monthStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;

  const monthInput = document.getElementById("month-selector");
  monthInput.value = monthStr;

  loadLabourSummary(CURRENT_LABOUR_ID, monthStr);

  new bootstrap.Modal(
    document.getElementById("labourSummaryModal")
  ).show();
}


/* ---------- LOAD DATA ---------- */
function loadLabourSummary(labourId, month) {

  fetch(`/${API_BASE}/api/labour/${labourId}/monthly-summary?month=${month}`)


    .then(res => {
      if (!res.ok) throw new Error("API error");
      return res.json();
    })
    .then(data => {
      fillModal(data);
      renderCalendar(data.calendar, month);
    })
    .catch(err => {
      console.error(err);
      alert("Failed to load labour summary");
    });
}


/* ---------- FILL MODAL ---------- */
function fillModal(data) {

  setText("ls-name", data.labour.name);
  setText("ls-phone", data.labour.phone);
  setText("ls-site", data.labour.site);

  setText("as-day", data.attendance_summary.day_shifts);
  setText("as-night", data.attendance_summary.night_shifts);
  setText("as-total", data.attendance_summary.total_shifts);
  setText("as-absent", data.attendance_summary.absent_days);

  setText("ps-wage", data.payment_summary.daily_wage);
  setText("ps-earned", data.payment_summary.earned_pay);
  setText("ps-advance", data.payment_summary.advance_paid);
  setText("ps-expense", data.payment_summary.mess_canteen);
  setText("ps-net", data.payment_summary.net_payable);
}


/* ---------- CALENDAR (CORRECTLY ALIGNED) ---------- */
function renderCalendar(calendarData, monthStr) {

  const container = document.getElementById("attendance-calendar");
  container.innerHTML = "";

  const [year, month] = monthStr.split("-").map(Number);
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDay = new Date(year, month - 1, 1).getDay(); // 0 = Sunday

  const statusMap = {};
  calendarData.forEach(d => {
    statusMap[d.date] = d.status;
  });

  // Weekday header
  const weekdays = document.createElement("div");
  weekdays.className = "calendar-weekdays";
  ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].forEach(w => {
    const s = document.createElement("span");
    s.innerText = w;
    weekdays.appendChild(s);
  });
  container.appendChild(weekdays);

  // Grid
  const grid = document.createElement("div");
  grid.className = "calendar-grid";

  // Empty cells
  for (let i = 0; i < firstDay; i++) {
    const empty = document.createElement("div");
    empty.className = "calendar-empty";
    grid.appendChild(empty);
  }

  // Days
  for (let day = 1; day <= daysInMonth; day++) {
    const cell = document.createElement("div");
    const dateStr = `${year}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
    cell.innerText = day;

    if (statusMap[dateStr] === "PRESENT") {
      cell.className = "calendar-day present";
    } else {
      cell.className = "calendar-day absent";
    }

    grid.appendChild(cell);
  }

  container.appendChild(grid);
}


/* ---------- UTILS ---------- */
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.innerText = value ?? "-";
}
