/* ===============================
   SAFE PRODUCTION MIGRATION
   Adds multi-company support
   NO DROPS, NO MODIFIES
   =============================== */

/* -------- NEW TABLES -------- */

CREATE TABLE IF NOT EXISTS plans (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(50) NOT NULL,
  price INT NOT NULL,
  max_labours INT NOT NULL,
  max_sites INT NOT NULL,
  export_level ENUM('monthly','all') NOT NULL,
  allow_audit TINYINT(1) DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS companies (
  id INT NOT NULL AUTO_INCREMENT,
  company_name VARCHAR(150) NOT NULL,
  plan_id INT NOT NULL,
  plan_expires_at DATE DEFAULT NULL,
  is_active TINYINT(1) DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY plan_id (plan_id)
);

/* -------- ADD company_id COLUMNS -------- */

ALTER TABLE attendance
  ADD COLUMN company_id INT DEFAULT NULL,
  ADD COLUMN morning_shift_flag TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE audit_log
  ADD COLUMN company_id INT DEFAULT NULL;

ALTER TABLE audit_log_archive
  ADD COLUMN company_id INT DEFAULT NULL;

ALTER TABLE labour_monthly_expenses
  ADD COLUMN company_id INT DEFAULT NULL;

ALTER TABLE labours
  ADD COLUMN company_id INT DEFAULT NULL;

ALTER TABLE payments
  ADD COLUMN company_id INT DEFAULT NULL;

ALTER TABLE sites
  ADD COLUMN company_id INT DEFAULT NULL;

ALTER TABLE users
  ADD COLUMN company_id INT DEFAULT NULL;
