/* ==========================================================
   Labour Management System — Admin Dashboard Script
   Author: Syed Sadab Alam | Version: 2.0
   Adds interactivity, animation, and dashboard logic
   ========================================================== */

// Ensure DOM fully loaded before running
document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Admin.js loaded successfully.");

  /* =============================
     1️⃣ SIDEBAR TOGGLE (Mobile)
  ============================= */
  const sidebarToggle = document.getElementById("sidebarToggle");
  const sidebar = document.querySelector(".sidebar");
  const mainContent = document.querySelector(".main-content");

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      sidebar.classList.toggle("collapsed");
      mainContent.classList.toggle("expanded");
    });
  }

 /* =============================
   2️⃣ AUTO HIGHLIGHT ACTIVE LINK (FIXED)
============================= */
const currentPath = window.location.pathname.replace(/\/+$/, ""); // remove trailing /

  document.querySelectorAll(".sidebar .nav-link").forEach(link => {
    const href = link.getAttribute("href");
    if (!href) return;

    const cleanHref = href.replace(/\/+$/, "");

    // Exact match OR sub-route match
    if (
      currentPath === cleanHref ||
      (currentPath.startsWith(cleanHref + "/") && cleanHref !== "")
    ) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });


  /* =============================
     3️⃣ AUTO HIDE ALERTS
  ============================= */
  const alerts = document.querySelectorAll(".alert");
  if (alerts.length) {
    setTimeout(() => {
      alerts.forEach(alert => alert.classList.add("fade"));
      setTimeout(() => alerts.forEach(alert => alert.remove()), 800);
    }, 4000);
  }

  /* =============================
     4️⃣ SMOOTH CARD LOAD ANIMATION
  ============================= */
  const cards = document.querySelectorAll(".card");
  cards.forEach((card, index) => {
    card.style.opacity = "0";
    card.style.transform = "translateY(15px)";
    setTimeout(() => {
      card.style.transition = "all 0.5s ease";
      card.style.opacity = "1";
      card.style.transform = "translateY(0)";
    }, 100 * index);
  });

  /* =============================
     5️⃣ CONFIRM DELETE MODALS
  ============================= */
  document.querySelectorAll(".btn-delete").forEach(btn => {
    btn.addEventListener("click", e => {
      const confirmDelete = confirm("Are you sure you want to delete this record?");
      if (!confirmDelete) e.preventDefault();
    });
  });

  /* =============================
     6️⃣ SMOOTH SCROLL TO TOP
  ============================= */
  const scrollBtn = document.createElement("button");
  scrollBtn.innerHTML = '<i class="fa-solid fa-arrow-up"></i>';
  scrollBtn.className = "scroll-top-btn";
  document.body.appendChild(scrollBtn);

  window.addEventListener("scroll", () => {
    scrollBtn.style.display = window.scrollY > 200 ? "flex" : "none";
  });

  scrollBtn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  /* =============================
     7️⃣ TABLE SEARCH FILTER (Optional)
  ============================= */
  const searchInputs = document.querySelectorAll("[data-search]");
  searchInputs.forEach(input => {
    input.addEventListener("input", () => {
      const targetId = input.getAttribute("data-search");
      const table = document.getElementById(targetId);
      const rows = table.querySelectorAll("tbody tr");
      const filter = input.value.toLowerCase();

      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? "" : "none";
      });
    });
  });
});

// small hover elevation for KPI cards
document.querySelectorAll('.kpi').forEach(k=>{
  k.addEventListener('mouseenter', ()=> k.style.transform='translateY(-6px)');
  k.addEventListener('mouseleave', ()=> k.style.transform='translateY(0)');
});
