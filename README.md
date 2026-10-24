# StockSense: Small-Retail Reorder Planner & Rural Analytics

**StockSense** is an AI-powered, full-stack inventory analytics, automated reorder planning, and rural store management platform engineered specifically for local grocery, kirana, retail, and convenience stores.

The platform includes two major architectural pillars:
1. **Rural-Friendly Data Collection**: Touch-first mobile entry for basic Android phones, handwritten notebook photo OCR, bilingual voice transcription (Hindi/English), physical stock reconciliation, and offline-first queue synchronization with duplicate prevention.
2. **Secure Administrator Panel**: Hardened RBAC authentication (`admin` vs `shopkeeper`), bcrypt hashing, short-lived JWTs, brute-force lockout, last-active-admin safeguards, immutable audit logging, and online SQLite backup/restore management.

---

## 🌟 Architecture & Full-Stack Capabilities

StockSense is an end-to-end client-server application built with a **React 19 + Vite** frontend, a high-throughput **Python FastAPI** backend, and an ACID-compliant **SQLite (WAL mode)** database as the primary source of truth.

### Customer, Staff Purchases & Spreadsheet Workflow
- Customer barcode checkout records the customer, scanned product/barcode, quantity, rate, payment method, and scan source in SQLite while updating stock and sales analytics.
- Staff supplier purchases store invoice, supplier, quantity, purchase/selling rates, payment status, and staff name; they update inventory and optionally update product rates with an audit history.
- Upload `.xlsx` workbooks or `.csv` files from **Upload Data**. StockSense analyzes the data and reports row, rate, category, and item insights before refreshing the dashboard from SQLite. Use the downloadable product templates for the expected import columns.
- Download the customer, staff procurement, product/rate, and rate-history records together from the SQLite Hub as a multi-sheet `.xlsx` workbook.
- Stock notifications use each product's configured storage capacity and alert at 50%, 25%, 15%, and 10% remaining; use **Place order** or the **Reorder Planner** to create supplier purchase orders.

### System Architecture
- **Frontend**: React 19, Vite 8, Tailwind CSS v4, Recharts, Lucide React, Axios, ZXing browser barcode library, IndexedDB offline transaction queue.
- **Backend**: Python 3.12, FastAPI, SQLAlchemy ORM, Pandas, NumPy, Scikit-learn, bcrypt, PyJWT, OpenPyXL, Uvicorn.
- **Databases**: SQLite with Write-Ahead Logging (`WAL`) in `backend/stocksense.db` (inventory, sales, authentication, suppliers, rates, and audit logs), `backend/customers.db` (customers and barcode purchases), and `backend/users.db` (staff procurement purchases). Each file uses its own SQLite transactions; workflows that update inventory and a separate purchase database use compensating rollback if one side fails.
- **Offline Sync**: Client-generated unique UUIDs (`operation_id`) guaranteed idempotent batch processing with duplicate suppression.
- **AI / Speech / OCR Integration**: Bilingual Hinglish/Hindi/English NLP transcript parser, fuzzy catalog matcher (`SequenceMatcher`), and Google Gemini / heuristic OCR staged correction tables.

---

## 📱 PART A — Rural Data Collection Features

### 1. Simple Mobile-First Manual Data Entry
- Designed for shopkeepers using basic Android smartphones.
- Large touch-friendly action tiles:
  - **Record Daily Sale**: Product selector (by name, brand, or category), quantity, price, payment mode (Cash, UPI, Khata/Credit). Barcode scanning is completely optional.
  - **Add New Stock**: Instant incoming delivery recording with quantity, purchase price, and supplier.
  - **Update Physical Stock**: One-tap stock adjustments with reason tracking.
  - **Add Product**: Fast product creation without requiring barcode hardware.

### 2. Handwritten Notebook Photo to Structured Data
- Shopkeepers can photograph their handwritten sales register (`khata` or daily dairy).
- Staging table displays extracted date, product name, quantity, unit price, and notes alongside uncertainty flags.
- **Never auto-commits uncertain data**: Requires explicit user review and confirmation before committing to SQLite.
- Preserves full notebook import history with session IDs.

### 3. Supplier Bill & Invoice Import
- Supports photos, scanned bills, CSV, and XLSX invoices.
- Fuzzy matching matches supplier product descriptions to internal inventory.
- Automatically creates stock-in movements, updates purchase price, creates lot records, and refreshes reorder recommendations.

### 4. Voice-Based Data Entry (Hindi + English)
- Microphone button for speech input in Hindi, English, and Hinglish.
- Example: `"Aaj das biscuit packet bike aur paanch litre tel aaya"`
- Built-in NLP parser breaks speech into structured draft transactions (e.g. `SALE: 10 Biscuits`, `STOCK_IN: 5 Oil`).
- Displays editable draft review before saving. Graceful fallback to manual entry if browser speech recognition is unavailable offline.

### 5. Physical Stock Counting & Reconciliation
- Shopkeeper selects a product and enters the actual counted physical stock.
- Instant variance analysis: compares system stock vs actual count, calculating shortages, surpluses, and financial impact.
- On confirmation, records previous quantity, counted quantity, variance, timestamp, and audit reason in the inventory movement ledger without deleting historical records.

### 6. Rural Shopkeeper Mode
- Bilingual interface: One-tap toggle between **Hindi (हिंदी)** and **English**.
- **Daily Closing Checklist**: Summary of total sales, total items sold, and top-selling product of the day.
- **"What should I order tomorrow?"**: Immediate, simplified purchase guidance.

### 7. Offline-First Synchronization
- Local IndexedDB/localStorage queue buffers transactions during internet disruptions.
- Each operation receives a client-side unique UUID (`operation_id`).
- Automatic synchronization when network connectivity returns (`online` event listener).
- Strict idempotency: Server checks `operation_id`; retried or re-sent transactions are recognized as `DUPLICATE` and never double-deduct stock or double-record sales.

---

## 🔒 PART B — Secure Administrator Panel

### 8. Authentication & Authorization
- Protected `/admin` console with server-side authorization on every route.
- Direct **bcrypt password hashing** with salt rounds.
- Short-lived JWT access tokens with revocation support via server-side session tracking (`user_sessions`).
- Optional secure HttpOnly cookies for browser protection.
- Brute-force rate limiting: 5 failed attempts automatically locks account for 15 minutes.
- Generic authentication errors prevent account enumeration.

### 9. User Roles & Role-Based Access Control (RBAC)
- **Administrator (`admin`)**: Full system access, user creation, role assignment, deactivation, password resets, audit log inspection, and database backup/restore.
- **Shopkeeper (`shopkeeper`)**: Restricted to daily store operations, sales, deliveries, counts, forecasts, and reports. Strictly forbidden (HTTP 403) from accessing admin endpoints.
- **Last Active Administrator Safeguard**: The system blocks any attempt to deactivate or demote the last remaining active administrator account.

### 10. Default System Credentials
When the database is initialized, default accounts may be provisioned. Set unique credentials immediately and never use demo credentials in production.

### 11. Immutable Audit Logging
- Immutable-by-normal-application audit table (`audit_logs_v2`).
- Logs actor ID, actor username, action code, entity type, entity ID, client IP, timestamp, and human-readable summary.
- Captures login events, user creation/deactivation, stock counts, manual sales, deliveries, and backups.

### 12. Database Backup, Health & Controlled Restore
- **Online Backup**: Consistent snapshots created using `sqlite3.Connection.backup` while the database remains online.
- **Integrity Checks**: Automated `PRAGMA integrity_check`, WAL size monitoring, and table row counts.
- **Pre-Restore Snapshot**: Restoring a backup automatically creates a safety snapshot of current data before applying the restore.
- Requires explicit administrator confirmation typing `CONFIRM_RESTORE`.

---

## 🚀 Quick Start Guide (Windows)

### Prerequisites
- Python 3.11 or 3.12
- Node.js 18+ and npm
- Windows PowerShell

### 1. Clone & Set Up Virtual Environment
```powershell
cd "e:\New folder\ksr"

# Set up Python virtual environment
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# Install frontend dependencies
npm install
```

### 2. Environment Configuration
Create a `.env` file in the project root:
```ini
STOCKSENSE_DB_PATH=backend/stocksense.db
STOCKSENSE_CUSTOMER_DB_PATH=backend/customers.db
STOCKSENSE_USER_DB_PATH=backend/users.db
JWT_SECRET_KEY=<generate-a-unique-random-secret>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=120
AS_OF_DATE=2026-09-30
SERVICE_LEVEL_Z=1.65

# Optional: Google Gemini API key for external AI extraction
GEMINI_API_KEY=
```

On startup, existing customer and staff purchase rows in `stocksense.db` are copied into their dedicated databases. The legacy tables are removed only after the migrated rows are verified. Backup creation snapshots all three databases, and each database can be restored from its corresponding backup.

### 3. Initialize SQLite Database
```powershell
# Populate database with authentic kirana products, lots, sales, and accounts
backend\.venv\Scripts\python.exe backend\app\seed_data.py
```

### 4. Run the Application
Open two PowerShell terminals:

**Terminal 1 — FastAPI Backend:**
```powershell
backend\.venv\Scripts\uvicorn.exe backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — React Vite Frontend:**
```powershell
npm run dev
```

Open your browser at:
- **Frontend Application**: `http://localhost:5173`
- **Interactive API Docs (Swagger UI)**: `http://127.0.0.1:8000/docs`
- **Shopkeeper Mode**: Click `Shopkeeper Mode (Rural)` on the sidebar or topbar
- **Secure Admin Panel**: Click `Secure Admin Panel` or the profile avatar and sign in with your configured administrator account.

---

## 🧪 Running Automated Tests

StockSense includes an extensive regression test suite covering rural workflows, offline synchronization, forecast mathematics, and admin security.

### 1. Run Complete Pytest Suite
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```
*Expected: 28 passed tests across 4 test modules.*

### 2. Run End-to-End Acceptance Verification
```powershell
backend\.venv\Scripts\python.exe test_e2e_workflow.py
```
*Executes all 17 acceptance steps including barcode scanning, atomic sales, forecast backtesting, voice parsing, stock count reconciliation, offline sync duplicate rejection, admin RBAC, and online backup creation.*

### 3. Build Frontend for Production
```powershell
npm run build
```

---

## 🌐 Hardware & Offline Operational Requirements

1. **Camera Permissions**: The browser barcode scanner and photo import require HTTPS (or `localhost`/`127.0.0.1` during local testing). In production, serve over HTTPS with a valid SSL/TLS certificate to enable camera access on mobile devices.
2. **Microphone Access**: Speech recognition requires microphone access in Chrome, Edge, or Android Webview.
3. **Offline Limitations**:
   - Local sales, stock adjustments, physical counts, and daily checklists function **100% offline** and queue in the browser.
   - When the network returns, clicking the offline sync button or reconnecting flushes the queue to FastAPI.
   - External Google Gemini AI extraction and live browser Web Speech recognition may require internet connectivity; deterministic heuristic parsing and manual correction workflows are provided as local fallbacks.

---

## 📦 Backup and Disaster Recovery Procedure

### Creating a Manual Backup via CLI
```powershell
# Backups are stored in backend/backups/
backend\.venv\Scripts\python.exe -c "from backend.app.database import SessionLocal; from backend.app.services.backup import create_database_backup; db = SessionLocal(); print(create_database_backup(db, note='CLI manual backup'))"
```

### Creating & Restoring Backups in Admin Console
1. Navigate to **Secure Admin Panel** -> **Database Backup & Health**.
2. Click **Create Live Backup** to generate an immediate verified SQLite backup.
3. To restore: select any listed backup and click **Restore Backup**. Confirm the dialog by typing `CONFIRM_RESTORE`. An automatic safety snapshot will be taken before the restore is executed.
# hariharan-s
#   h a r i h a r a n - s  
 