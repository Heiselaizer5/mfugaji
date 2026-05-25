from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3, time, json, uvicorn
from datetime import datetime, timedelta, date
from pydantic import BaseModel
import os

app = FastAPI(title="Mfugaji Kwanza")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ========================
# CONFIG — set these env vars for Supabase
# ========================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "Admin@2025!")

# ========================
# DATABASE LAYER
# ========================
use_supabase = False
sb = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        use_supabase = True
        print("[OK] Using Supabase database")
    except Exception as e:
        print(f"[WARN] Supabase init error: {e}")

if not use_supabase:
    print("[OK] Using SQLite database (local)")

def get_db():
    conn = sqlite3.connect("farm_data.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def db_get_user_by_username(username):
    if use_supabase:
        result = sb.table("users").select("*").eq("username", username).execute()
        return result.data[0] if result.data else None
    conn = get_db()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def db_get_user_by_id(user_id):
    if use_supabase:
        result = sb.table("users").select("*").eq("id", user_id).execute()
        return result.data[0] if result.data else None
    conn = get_db()
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def db_insert_user(username, password, is_activated=0, security_question=None, security_answer=None):
    if use_supabase:
        data = {"username": username, "password": password, "is_activated": is_activated}
        if security_question and security_answer:
            data["security_question"] = security_question
            data["security_answer"] = security_answer
        result = sb.table("users").insert(data).execute()
        return result.data[0]["id"] if result.data else None
    conn = get_db()
    conn.execute("INSERT INTO users (username, password, is_activated, security_question, security_answer) VALUES (?, ?, ?, ?, ?)",
                 (username, password, is_activated, security_question, security_answer))
    conn.commit()
    cur = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
    user_id = cur.fetchone()["id"]
    conn.close()
    return user_id

def db_update_user(user_id, updates):
    if use_supabase:
        sb.table("users").update(updates).eq("id", user_id).execute()
        return
    conn = get_db()
    set_parts = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [user_id]
    conn.execute(f"UPDATE users SET {set_parts} WHERE id = ?", vals)
    conn.commit()
    conn.close()

def db_get_farm_dates(user_id):
    if use_supabase:
        result = sb.table("farm_dates").select("*").eq("user_id", user_id).execute()
        return result.data if result.data else []
    conn = get_db()
    rows = conn.execute("SELECT * FROM farm_dates WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_sales_records(user_id):
    if use_supabase:
        result = sb.table("sales_records").select("*").eq("user_id", user_id).execute()
        return result.data if result.data else []
    conn = get_db()
    rows = conn.execute("SELECT * FROM sales_records WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_upsert_farm_date(user_id, dk, entry):
    data = {
        "user_id": user_id, "date_key": dk,
        "chicks_qty": int(entry.get("chicks_qty", 0)),
        "chicks_cost": entry.get("chicks_cost", 0.0),
        "feed_cost": entry.get("feed_cost", 0.0),
        "med_cost": entry.get("med_cost", 0.0),
        "other_cost": entry.get("other_cost", 0.0),
        "mortality": int(entry.get("mortality", 0)),
        "has_inputs": 1 if entry.get("has_inputs") else 0,
        "has_sales": 1 if entry.get("has_sales") else 0,
    }
    if use_supabase:
        sb.table("farm_dates").upsert(data, on_conflict="user_id,date_key").execute()
        return
    conn = get_db()
    conn.execute("""
        INSERT INTO farm_dates (user_id, date_key, chicks_qty, chicks_cost, feed_cost, med_cost, other_cost, mortality, has_inputs, has_sales)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id, date_key) DO UPDATE SET
            chicks_qty=excluded.chicks_qty, chicks_cost=excluded.chicks_cost,
            feed_cost=excluded.feed_cost, med_cost=excluded.med_cost,
            other_cost=excluded.other_cost, mortality=excluded.mortality,
            has_inputs=excluded.has_inputs, has_sales=excluded.has_sales
    """, (user_id, dk, data["chicks_qty"], data["chicks_cost"], data["feed_cost"],
          data["med_cost"], data["other_cost"], data["mortality"],
          data["has_inputs"], data["has_sales"]))
    conn.commit()
    conn.close()

def db_delete_sales_records(user_id, dk):
    if use_supabase:
        sb.table("sales_records").delete().eq("user_id", user_id).eq("date_key", dk).execute()
        return
    conn = get_db()
    conn.execute("DELETE FROM sales_records WHERE user_id = ? AND date_key = ?", (user_id, dk))
    conn.commit()
    conn.close()

def db_insert_sale_record(user_id, dk, rec):
    data = {"user_id": user_id, "date_key": dk, "customer": rec["customer"],
            "qty": int(rec["qty"]), "price": rec["price"], "revenue": rec["revenue"]}
    if use_supabase:
        sb.table("sales_records").insert(data).execute()
        return
    conn = get_db()
    conn.execute("INSERT INTO sales_records (user_id, date_key, customer, qty, price, revenue) VALUES (?,?,?,?,?,?)",
                 (user_id, dk, rec["customer"], rec["qty"], rec["price"], rec["revenue"]))
    conn.commit()
    conn.close()

def db_get_reminders(user_id, include_done=False):
    if use_supabase:
        try:
            q = sb.table("reminders").select("*").eq("user_id", user_id).order("due_date")
            if not include_done:
                q = q.eq("is_done", 0)
            result = q.execute()
            return result.data if result.data else []
        except:
            return []
    conn = get_db()
    sql = "SELECT * FROM reminders WHERE user_id = ?"
    if not include_done:
        sql += " AND is_done = 0"
    sql += " ORDER BY due_date"
    rows = conn.execute(sql, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_insert_reminder(user_id, data):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "user_id": user_id,
        "title": data["title"],
        "description": data.get("description", ""),
        "reminder_type": data.get("reminder_type", "general"),
        "due_date": data.get("due_date", now_str[:10]),
        "frequency_days": int(data.get("frequency_days", 0)),
        "is_done": 0,
        "round_number": int(data.get("round_number", 0)),
        "created_at": now_str,
    }
    if use_supabase:
        try:
            result = sb.table("reminders").insert(record).execute()
            return result.data[0]["id"] if result.data else None
        except:
            return None
    conn = get_db()
    conn.execute("""INSERT INTO reminders (user_id, title, description, reminder_type, due_date, frequency_days, is_done, round_number, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (record["user_id"], record["title"], record["description"], record["reminder_type"],
                  record["due_date"], record["frequency_days"], record["is_done"],
                  record["round_number"], record["created_at"]))
    conn.commit()
    cur = conn.execute("SELECT last_insert_rowid()")
    rid = cur.fetchone()[0]
    conn.close()
    return rid

def db_update_reminder(reminder_id, updates):
    if use_supabase:
        try:
            sb.table("reminders").update(updates).eq("id", reminder_id).execute()
        except:
            pass
        return
    conn = get_db()
    set_parts = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [reminder_id]
    conn.execute(f"UPDATE reminders SET {set_parts} WHERE id = ?", vals)
    conn.commit()
    conn.close()

def db_delete_reminder(reminder_id):
    if use_supabase:
        try:
            sb.table("reminders").delete().eq("id", reminder_id).execute()
        except:
            pass
        return
    conn = get_db()
    conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def db_archive_round(user_id, round_number, summary_json):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if use_supabase:
        try:
            sb.table("rounds").insert({"user_id": user_id, "round_number": round_number, "archived_at": now_str, "summary_json": summary_json}).execute()
        except:
            pass
        return
    conn = get_db()
    conn.execute("INSERT INTO rounds (user_id, round_number, archived_at, summary_json) VALUES (?, ?, ?, ?)",
                 (user_id, round_number, now_str, summary_json))
    conn.commit()
    conn.close()

def db_get_rounds(user_id):
    if use_supabase:
        try:
            result = sb.table("rounds").select("*").eq("user_id", user_id).order("round_number", desc=True).execute()
            return result.data if result.data else []
        except:
            return []
    conn = get_db()
    rows = conn.execute("SELECT * FROM rounds WHERE user_id = ? ORDER BY round_number DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_round(user_id, round_number):
    if use_supabase:
        try:
            result = sb.table("rounds").select("*").eq("user_id", user_id).eq("round_number", round_number).execute()
            return result.data[0] if result.data else None
        except:
            return None
    conn = get_db()
    row = conn.execute("SELECT * FROM rounds WHERE user_id = ? AND round_number = ?", (user_id, round_number)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_delete_round(user_id, round_number):
    if use_supabase:
        try:
            sb.table("rounds").delete().eq("user_id", user_id).eq("round_number", round_number).execute()
        except:
            pass
        return
    conn = get_db()
    conn.execute("DELETE FROM rounds WHERE user_id = ? AND round_number = ?", (user_id, round_number))
    conn.commit()
    conn.close()

def db_clear_user_data(user_id):
    if use_supabase:
        sb.table("farm_dates").delete().eq("user_id", user_id).execute()
        sb.table("sales_records").delete().eq("user_id", user_id).execute()
        return
    conn = get_db()
    conn.execute("DELETE FROM farm_dates WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM sales_records WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def db_get_farm_data(user_id):
    frows = db_get_farm_dates(user_id)
    srows = db_get_sales_records(user_id)
    farm = {}
    for r in frows:
        dk = r["date_key"]
        farm[dk] = {
            "chicks_qty": r["chicks_qty"], "chicks_cost": r["chicks_cost"],
            "feed_cost": r["feed_cost"], "med_cost": r["med_cost"],
            "other_cost": r["other_cost"], "mortality": r["mortality"],
            "has_inputs": bool(r["has_inputs"]), "has_sales": bool(r["has_sales"]),
            "sales_records": []
        }
    for s in srows:
        dk = s["date_key"]
        if dk in farm:
            farm[dk]["sales_records"].append({
                "customer": s["customer"], "qty": s["qty"],
                "price": s["price"], "revenue": s["revenue"]
            })
    return farm

def check_subscription_expiry(user_id):
    user = db_get_user_by_id(user_id)
    if not user:
        return False
    is_activated = bool(user.get("is_activated", 0))
    subscription_end = user.get("subscription_end")
    if not is_activated:
        return False
    if subscription_end:
        try:
            expiry_date = datetime.strptime(subscription_end, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if now > expiry_date:
                db_update_user(user_id, {"is_activated": 0})
                return False
        except:
            pass
    return True

def activate_subscription(user_id, days=30):
    now = datetime.now()
    expiry = now + timedelta(days=days)
    db_update_user(user_id, {
        "is_activated": 1,
        "subscription_start": now.strftime("%Y-%m-%d %H:%M:%S"),
        "subscription_end": expiry.strftime("%Y-%m-%d %H:%M:%S")
    })
    return expiry

def get_subscription_info(user_id):
    user = db_get_user_by_id(user_id)
    if not user:
        return {"active": False, "days_left": 0, "end_text": ""}
    active = bool(user.get("is_activated", 0))
    end = user.get("subscription_end")
    days_left = 0
    end_text = ""
    if active and end:
        try:
            expiry = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            days_left = max(0, (expiry - now).days)
            if days_left <= 5:
                end_text = f"⚠️ Siku {days_left} zimesalia! / WARNING: {days_left} days left! Pay now!"
            elif days_left > 0:
                end_text = f"⏳ Malipo yanaisha siku {days_left} / Expires in {days_left} days"
        except:
            pass
    return {"active": active, "days_left": days_left, "end_text": end_text}

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_activated INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            subscription_start TEXT,
            subscription_end TEXT,
            security_question TEXT,
            security_answer TEXT
        );
        CREATE TABLE IF NOT EXISTS farm_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date_key TEXT NOT NULL,
            chicks_qty INTEGER DEFAULT 0,
            chicks_cost REAL DEFAULT 0.0,
            feed_cost REAL DEFAULT 0.0,
            med_cost REAL DEFAULT 0.0,
            other_cost REAL DEFAULT 0.0,
            mortality INTEGER DEFAULT 0,
            has_inputs INTEGER DEFAULT 0,
            has_sales INTEGER DEFAULT 0,
            UNIQUE(user_id, date_key)
        );
        CREATE TABLE IF NOT EXISTS sales_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date_key TEXT NOT NULL,
            customer TEXT NOT NULL,
            qty INTEGER NOT NULL,
            price REAL NOT NULL,
            revenue REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            archived_at TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            UNIQUE(user_id, round_number)
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            reminder_type TEXT DEFAULT 'general',
            due_date TEXT NOT NULL,
            frequency_days INTEGER DEFAULT 0,
            is_done INTEGER DEFAULT 0,
            round_number INTEGER DEFAULT 0,
            created_at TEXT
        );
    """)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    for col in ["subscription_start","subscription_end","security_question","security_answer","is_admin"]:
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
    conn.commit()
    
    # Create default admin if not exists
    existing = conn.execute("SELECT id FROM users WHERE is_admin = 1").fetchone()
    if not existing:
        conn.execute("INSERT OR IGNORE INTO users (username, password, is_activated, is_admin) VALUES (?, ?, 1, 1)",
                     (ADMIN_USERNAME, ADMIN_PASSWORD))
        conn.commit()
        print(f"[OK] Default admin created: {ADMIN_USERNAME}")
    
    conn.close()

init_db()

# ========================
# SESSION (simple token-based)
# ========================
sessions = {}

def make_token():
    import secrets
    return secrets.token_hex(32)

def get_user(req: Request):
    token = req.cookies.get("token")
    if token and token in sessions:
        return sessions[token]
    return None

# ========================
# TRANSLATIONS
# ========================
translations = {
    "Swahili": {
        "app_title": "MFUGAJI KWANZA",
        "subtitle": "Mfumo wa Kisasa wa Usimamizi wa Kuku",
        "login_header": "🔒 Ingia Kwenye Akaunti",
        "signup_header": "📝 Fungua Akaunti Mpya",
        "username": "Jina la Mtumiaji",
        "password": "Neno la Siri",
        "full_name": "Jina Lako Kamili",
        "login_btn": "🚀 Ingia Sasa",
        "signup_btn": "📝 Sajili na Uendelee Malipo",
        "no_account": "Hauna akaunti? Jisajili hapa",
        "have_account": "Umeshajisajili? Ingia hapa",
        "error_msg": "❌ Jina au neno la siri sio sahihi.",
        "error_fields": "❌ Tafadhali jaza sehemu zote!",
        "success_msg": "✅ Akaunti imefunguliwa! Tafadhali kamilisha malipo...",
        "login_success": "✅ Umefanikiwa kuingia!",
        "logout": "Ondoka",
        "welcome": "Usimamizi wa Kuku wa Nyama",
        "choice_inputs": "🛒 Maendeleo na Gharama",
        "choice_withdraw": "💰 Mauzo ya Kuku",
        "back_btn": "← Rudi Dashibodi",
        "input_header": "🐣 Maendeleo na Gharama",
        "sales_header": "💰 Mauzo ya Kuku",
        "label_chicks_qty": "Idadi ya Vifaranga",
        "label_chicks": "Gharama ya Vifaranga (TSH)",
        "label_feed": "Gharama ya Chakula (TSH)",
        "label_med": "Gharama ya Dawa (TSH)",
        "label_other": "Gharama Nyingine (TSH)",
        "label_mortality": "Idadi ya Vifo",
        "label_date": "Chagua Tarehe:",
        "finish_inputs_btn": "🏁 Hifadhi Gharama",
        "finish_sales_btn": "🏁 Hifadhi Mauzo",
        "label_qty": "Idadi ya Kuku",
        "label_customer": "Jina la Mteja",
        "label_price": "Bei kwa Kuku (TSH)",
        "summary_header": "Muhtasari wa Fedha",
        "total_expenses": "Jumla ya Matumizi:",
        "total_revenue": "Jumla ya Mapato:",
        "calc_profit_btn": "📈 Piga Hesabu ya Faida",
        "profit_msg": "🎉 Faida ya",
        "loss_msg": "⚠️ Hasara ya",
        "no_records": "❌ Hakuna kumbukumbu.",
        "total_chicks": "Jumla Vifaranga",
        "deaths": "Vifo",
        "remaining": "Waliopo",
        "chicks_summary": "🐥 Jumla: {}  |  ❌ Vifo: {}  |  ✅ Waliopo: {}",
        "current_round": "Awamu ya Sasa",
        "move_to_next_round": "Nenda Awamu Inayofuata",
        "round_history": "Kumbukumbu za Awamu",
        "no_rounds": "Hakuna awamu za awali.",
        "round_archived": "Awamu imehifadhiwa!",
        "round_deleted": "Awamu imefutwa!",
        "reminders_title": "⏰ Vikumbusho",
        "add_reminder": "➕ Ongeza Kikumbusho",
        "no_reminders": "Hakuna vikumbusho.",
        "reminder_type": "Aina",
        "reminder_title": "Jina",
        "reminder_date": "Tarehe",
        "reminder_frequency": "Mara",
        "reminder_once": "Mara Moja",
        "reminder_daily": "Kila Siku",
        "reminder_weekly": "Kila Siku 7",
        "reminder_biweekly": "Kila Siku 14",
        "reminder_monthly": "Kila Siku 30",
        "reminder_status": "Hali",
        "reminder_done": "✅ Imefanyika",
        "reminder_pending": "⏳ Inasubiri",
        "reminder_overdue": "❌ Imechelewa",
        "mark_done": "✅ Imefanyika",
        "delete_reminder": "❌ Futa",
        "reminder_chanjo": "💉 Chanjo",
        "reminder_dawa": "💊 Dawa",
        "reminder_chakula": "🌾 Chakula",
        "reminder_general": "📌 Nyingine",
        "save_reminder_btn": "💾 Hifadhi Kikumbusho",
        "reminder_today": "Leo",
        "choose_language": "🌐 Chagua Lugha",
        "forgot_pass": "Umesahau password?",
        "reset_pass_title": "🔑 Weka Password Mpya",
        "sec_question": "Swali la Usalama",
        "sec_answer": "Jibu la Usalama",
        "verify_question": "Jibu Swali la Usalama",
        "wrong_answer": "❌ Jibu si sahihi!",
        "questions": [
            "Jina la mama yako ni nani?",
            "Jina la mnyama wako wa kwanza?",
            "Rangi yako favorite?",
            "Mji uliozaliwa?",
            "Chakula chako favorite?",
            "Timu yako favorite?"
        ],
        "kumbu_dev": "Kumbukumbu za Maendeleo",
        "kumbu_sale": "Kumbukumbu za Mauzo",
        "edit_btn": "✏️ Hariri",
        "save_btn": "💾 Hifadhi",
        "cancel_btn": "❌ Ghairi",
        "edit_record": "✏️ Hariri Kumbukumbu",
        "edit_sale": "✏️ Hariri Mauzo",
        "save_success": "Imerekebishwa!",
        "empty_name": "❌ Tafadhali ingiza jina!",
    },
    "English": {
        "app_title": "MFUGAJI KWANZA",
        "subtitle": "Modern Poultry Management System",
        "login_header": "🔒 Account Login",
        "signup_header": "📝 Create New Account",
        "username": "Username",
        "password": "Password",
        "full_name": "Full Name",
        "login_btn": "🚀 Sign In",
        "signup_btn": "📝 Register & Pay",
        "no_account": "Don't have an account? Sign Up",
        "have_account": "Already have an account? Log In",
        "error_msg": "❌ Invalid Username or Password.",
        "error_fields": "❌ All fields are required.",
        "success_msg": "✅ Account Created! Please process payment...",
        "login_success": "✅ Login Successful!",
        "logout": "Logout",
        "welcome": "Broiler Batch Manager",
        "choice_inputs": "🛒 Development & Expenditure",
        "choice_withdraw": "💰 Broiler Sales",
        "back_btn": "← Back to Dashboard",
        "input_header": "🐣 Development & Expenditure",
        "sales_header": "💰 Broiler Sales",
        "label_chicks_qty": "Number of Chicks Introduced",
        "label_chicks": "Total Cost of Chicks (TSH)",
        "label_feed": "Total Cost of Feeds (TSH)",
        "label_med": "Total Cost of Medicine (TSH)",
        "label_other": "Total Other Expenses (TSH)",
        "label_mortality": "Mortality Count",
        "label_date": "Select Date:",
        "finish_inputs_btn": "🏁 Save Expenses",
        "finish_sales_btn": "🏁 Save Sale",
        "label_qty": "Number of Chickens",
        "label_customer": "Customer Name",
        "label_price": "Price per Chicken (TSH)",
        "summary_header": "Financial Summary",
        "total_expenses": "Total Expenses:",
        "total_revenue": "Total Revenue:",
        "calc_profit_btn": "📈 Calculate Net Profit",
        "profit_msg": "🎉 Net Profit of",
        "loss_msg": "⚠️ Net Loss of",
        "no_records": "❌ No records found.",
        "total_chicks": "Total Chicks",
        "deaths": "Deaths",
        "remaining": "Remaining",
        "chicks_summary": "🐥 Total: {}  |  ❌ Deaths: {}  |  ✅ Remaining: {}",
        "current_round": "Current Round",
        "move_to_next_round": "Move to Next Round",
        "round_history": "Round History",
        "no_rounds": "No previous rounds.",
        "round_archived": "Round archived!",
        "round_deleted": "Round deleted!",
        "reminders_title": "⏰ Reminders",
        "add_reminder": "➕ Add Reminder",
        "no_reminders": "No reminders.",
        "reminder_type": "Type",
        "reminder_title": "Title",
        "reminder_date": "Date",
        "reminder_frequency": "Frequency",
        "reminder_once": "Once",
        "reminder_daily": "Every Day",
        "reminder_weekly": "Every 7 Days",
        "reminder_biweekly": "Every 14 Days",
        "reminder_monthly": "Every 30 Days",
        "reminder_status": "Status",
        "reminder_done": "✅ Done",
        "reminder_pending": "⏳ Pending",
        "reminder_overdue": "❌ Overdue",
        "mark_done": "✅ Mark Done",
        "delete_reminder": "❌ Delete",
        "reminder_chanjo": "💉 Vaccine",
        "reminder_dawa": "💊 Medicine",
        "reminder_chakula": "🌾 Feed",
        "reminder_general": "📌 General",
        "save_reminder_btn": "💾 Save Reminder",
        "reminder_today": "Today",
        "choose_language": "🌐 Choose Language",
        "forgot_pass": "Forgot password?",
        "reset_pass_title": "🔑 Reset Password",
        "sec_question": "Security Question",
        "sec_answer": "Security Answer",
        "verify_question": "Answer Security Question",
        "wrong_answer": "❌ Wrong answer!",
        "questions": [
            "What is your mother's maiden name?",
            "What was the name of your first pet?",
            "What is your favorite color?",
            "What city were you born in?",
            "What is your favorite food?",
            "What is your favorite sports team?"
        ],
        "kumbu_dev": "Development Records",
        "kumbu_sale": "Sales Records",
        "edit_btn": "✏️ Edit",
        "save_btn": "💾 Save",
        "cancel_btn": "❌ Cancel",
        "edit_record": "✏️ Edit Record",
        "edit_sale": "✏️ Edit Sale",
        "save_success": "Updated successfully!",
        "empty_name": "❌ Please enter customer name!",
    }
}

# ========================
# API ROUTES
# ========================

@app.get("/api/lang/{lang}")
async def set_lang(lang: str):
    return {"lang": lang if lang in translations else "Swahili"}

@app.post("/api/login")
async def login(data: dict):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return {"error": "fields"}
    user = db_get_user_by_username(username)
    if user and user.get("password") == password:
        token = make_token()
        is_admin = bool(user.get("is_admin", 0))
        active = True if is_admin else check_subscription_expiry(user["id"])
        sub = get_subscription_info(user["id"])
        sessions[token] = {
            "user_id": user["id"],
            "username": username,
            "is_activated": active,
            "is_admin": is_admin,
            "sub_info": sub
        }
        if is_admin:
            return {"ok": True, "token": token, "user_id": user["id"], "username": username,
                    "is_activated": True, "is_admin": True, "sub_info": sub}
        farm = db_get_farm_data(user["id"])
        reminders = db_get_reminders(user["id"], include_done=False)
        return {"ok": True, "token": token, "user_id": user["id"], "username": username,
                "is_activated": active, "sub_info": sub,
                "farm": farm, "reminders": reminders}
    return {"error": "auth"}

@app.post("/api/signup")
async def signup(data: dict):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    sec_q = data.get("security_question", "")
    sec_a = data.get("security_answer", "").strip()
    if not username or not password:
        return {"error": "fields"}
    existing = db_get_user_by_username(username)
    if existing:
        return {"error": "exists"}
    try:
        user_id = db_insert_user(username, password, 0, sec_q, sec_a)
        token = make_token()
        sessions[token] = {
            "user_id": user_id,
            "username": username,
            "is_activated": False,
            "sub_info": {"active": False, "days_left": 0, "end_text": ""}
        }
        return {"ok": True, "token": token, "user_id": user_id, "username": username, "is_activated": False}
    except:
        return {"error": "exists"}

@app.post("/api/reset/verify")
async def reset_verify(data: dict):
    username = data.get("username", "").strip()
    if not username:
        return {"error": "fields"}
    user = db_get_user_by_username(username)
    if user and user.get("security_question"):
        return {"ok": True, "question": user["security_question"], "user_id": user["id"]}
    return {"error": "not_found"}

@app.post("/api/reset/answer")
async def reset_answer(data: dict):
    user_id = data.get("user_id")
    answer = data.get("answer", "").strip()
    user = db_get_user_by_id(user_id)
    if user and user.get("security_answer", "").strip() == answer:
        return {"ok": True}
    return {"error": "wrong"}

@app.post("/api/reset/password")
async def reset_password(data: dict):
    user_id = data.get("user_id")
    password = data.get("password", "")
    if not password:
        return {"error": "fields"}
    db_update_user(user_id, {"password": password})
    return {"ok": True}

@app.post("/api/subscription/activate")
async def activate(data: dict):
    user_id = data.get("user_id")
    if not user_id:
        return {"error": "no_user"}
    expiry = activate_subscription(user_id, days=30)
    sub = get_subscription_info(user_id)
    return {"ok": True, "sub_info": sub}

@app.get("/api/data/{token}")
async def get_data(token: str):
    if token not in sessions:
        return {"error": "auth"}
    sess = sessions[token]
    user_id = sess["user_id"]
    farm = db_get_farm_data(user_id)
    reminders = db_get_reminders(user_id, include_done=False)
    sub = get_subscription_info(user_id)
    return {"farm": farm, "reminders": reminders, "sub_info": sub,
            "is_activated": sub["active"], "round_history": db_get_rounds(user_id)}

@app.post("/api/save")
async def save_data(data: dict):
    token = data.get("token")
    if token not in sessions:
        return {"error": "auth"}
    user_id = sessions[token]["user_id"]
    farm = data.get("farm", {})
    for dk, entry in farm.items():
        db_upsert_farm_date(user_id, dk, entry)
        db_delete_sales_records(user_id, dk)
        for rec in entry.get("sales_records", []):
            db_insert_sale_record(user_id, dk, rec)
    return {"ok": True}

@app.post("/api/reminder/add")
async def add_reminder(data: dict):
    token = data.get("token")
    if token not in sessions:
        return {"error": "auth"}
    user_id = sessions[token]["user_id"]
    rid = db_insert_reminder(user_id, data)
    return {"ok": True, "id": rid}

@app.post("/api/reminder/update")
async def update_reminder(data: dict):
    db_update_reminder(data["id"], data["updates"])
    return {"ok": True}

@app.post("/api/reminder/delete")
async def delete_reminder(data: dict):
    db_delete_reminder(data["id"])
    return {"ok": True}

@app.post("/api/round/archive")
async def archive_round(data: dict):
    token = data.get("token")
    if token not in sessions:
        return {"error": "auth"}
    user_id = sessions[token]["user_id"]
    import json
    summary_json = json.dumps(data["farm"])
    rounds = db_get_rounds(user_id)
    next_round = max([r["round_number"] for r in rounds], default=0) + 1
    db_archive_round(user_id, next_round, summary_json)
    db_clear_user_data(user_id)
    return {"ok": True, "next_round": next_round + 1}

@app.post("/api/round/delete")
async def delete_round(data: dict):
    db_delete_round(data["user_id"], data["round_number"])
    return {"ok": True}

@app.get("/api/round/{token}/{round_number}")
async def view_round(token: str, round_number: int):
    if token not in sessions:
        return {"error": "auth"}
    user_id = sessions[token]["user_id"]
    rnd = db_get_round(user_id, round_number)
    if not rnd:
        return {"error": "not_found"}
    import json
    farm = json.loads(rnd["summary_json"])
    return {"round": rnd, "farm": farm}

@app.get("/api/admin/users/{token}")
async def admin_get_users(token: str):
    if token not in sessions or not sessions[token].get("is_admin"):
        return {"error": "auth"}
    if use_supabase:
        result = sb.table("users").select("id,username,is_activated,is_admin,subscription_end").execute()
        return {"users": result.data}
    conn = get_db()
    rows = conn.execute("SELECT id, username, is_activated, is_admin, subscription_end FROM users").fetchall()
    conn.close()
    return {"users": [dict(r) for r in rows]}

@app.get("/api/admin/user_data/{token}/{user_id}")
async def admin_get_user_data(token: str, user_id: int):
    if token not in sessions or not sessions[token].get("is_admin"):
        return {"error": "auth"}
    farm = db_get_farm_data(user_id)
    reminders = db_get_reminders(user_id, include_done=False)
    user = db_get_user_by_id(user_id)
    return {"farm": farm, "reminders": reminders, "username": user["username"] if user else "Unknown"}

@app.get("/api/admin/activate/{token}/{user_id}")
async def admin_activate_user(token: str, user_id: int):
    if token not in sessions or not sessions[token].get("is_admin"):
        return {"error": "auth"}
    expiry = activate_subscription(user_id, days=30)
    return {"ok": True}

@app.get("/api/admin/delete_user/{token}/{user_id}")
async def admin_delete_user(token: str, user_id: int):
    if token not in sessions or not sessions[token].get("is_admin"):
        return {"error": "auth"}
    if use_supabase:
        sb.table("farm_dates").delete().eq("user_id", user_id).execute()
        sb.table("sales_records").delete().eq("user_id", user_id).execute()
        sb.table("reminders").delete().eq("user_id", user_id).execute()
        sb.table("rounds").delete().eq("user_id", user_id).execute()
        sb.table("users").delete().eq("id", user_id).execute()
    else:
        conn = get_db()
        conn.execute("DELETE FROM farm_dates WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM sales_records WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM rounds WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    return {"ok": True}

# ========================
# MAIN HTML PAGE (SPA)
# ========================
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mfugaji Kwanza</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Tahoma, sans-serif;
    background: linear-gradient(135deg, #0a0a1a, #1a1a2e);
    color: #fff; min-height: 100vh;
}
.container { max-width: 900px; margin: 0 auto; padding: 16px; }
.header { text-align: center; padding: 20px 0 10px; }
.header h1 { color: #FFF; font-size: 28px; font-weight: 900; text-shadow: 3px 3px 6px rgba(0,0,0,0.8); }
.header .sub { color: #00E676; font-size: 12px; font-weight: 600; letter-spacing: 1px; }
.lang-bar { display: flex; justify-content: flex-end; gap: 6px; margin-bottom: 10px; }
.lang-bar button {
    padding: 4px 12px; border-radius: 4px; border: 1px solid #3a3a5a;
    background: #1a1a2e; color: #AAA; font-size: 11px; font-weight: 600; cursor: pointer;
}
.lang-bar button.active { background: #00E676; color: #000; border-color: #00E676; }
.card {
    background: linear-gradient(145deg, #1a1a2e, #16213e);
    border: 1px solid #2a2a4a; border-radius: 16px; padding: 24px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4); margin-bottom: 14px;
}
.card-glow { border: 1px solid #00E676; box-shadow: 0 0 20px rgba(0,230,118,0.1); }
.btn {
    display: inline-block; width: 100%; padding: 12px 20px; margin: 6px 0;
    background: linear-gradient(135deg, #00E676, #00c853); color: #000;
    border: none; border-radius: 12px; font-size: 15px; font-weight: 700;
    cursor: pointer; transition: all 0.2s; text-align: center;
}
.btn:hover { transform: translateY(-2px); box-shadow: 0 6px 25px rgba(0,230,118,0.4); }
.btn-sm { padding: 8px 14px; font-size: 12px; width: auto; display: inline-block; }
.btn-danger { background: linear-gradient(135deg, #FF5252, #d32f2f); }
.btn-gold { background: linear-gradient(135deg, #FFD700, #FFA500); }
.btn-outline { background: transparent; border: 1px solid #3a3a5a; color: #FFF; }
input, select, textarea {
    width: 100%; padding: 10px 14px; margin: 4px 0 10px;
    background: #0a0a1a; border: 1px solid #3a3a5a; border-radius: 10px;
    color: #FFF; font-size: 14px; outline: none;
}
input:focus, select:focus { border-color: #00E676; box-shadow: 0 0 0 2px rgba(0,230,118,0.15); }
label { color: #AAA; font-size: 12px; font-weight: 600; display: block; margin-top: 6px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.text-center { text-align: center; }
.text-gold { color: #FFD700; }
.text-green { color: #00E676; }
.text-red { color: #FF5252; }
.text-muted { color: #888; font-size: 12px; }
.mt-2 { margin-top: 8px; }
.mt-4 { margin-top: 16px; }
.mb-2 { margin-bottom: 8px; }
.mb-4 { margin-bottom: 16px; }
.hidden { display: none !important; }
.flex { display: flex; }
.flex-between { display: flex; justify-content: space-between; align-items: center; }
.flex-gap { gap: 8px; }
.badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 11px; font-weight: 700;
}
.badge-green { background: #00E67620; color: #00E676; border: 1px solid #00E67640; }
.badge-red { background: #FF525220; color: #FF5252; border: 1px solid #FF525240; }
.badge-gold { background: #FFD70020; color: #FFD700; border: 1px solid #FFD70040; }
.badge-blue { background: #38bdf820; color: #38bdf8; border: 1px solid #38bdf840; }
.alert {
    padding: 12px 16px; border-radius: 12px; margin-bottom: 8px;
    border-left: 5px solid; font-size: 13px;
}
.alert-error { background: #2a0a0a; border-color: #FF5252; color: #FF5252; }
.alert-warning { background: #2a2a0a; border-color: #FFD700; color: #FFD700; }
.alert-info { background: #0a1a2e; border-color: #38bdf8; color: #38bdf8; }
.stat-box {
    background: linear-gradient(135deg, #0a1628, #111827); border-radius: 12px;
    padding: 14px; text-align: center; border: 1px solid #2a2a4a;
}
.stat-box .num { font-size: 22px; font-weight: 800; }
.stat-box .label { font-size: 10px; color: #789; font-weight: 600; }
.tab-bar { display: flex; gap: 4px; margin-bottom: 14px; }
.tab-bar button {
    flex: 1; padding: 8px; border: 1px solid #2a2a4a; background: #1a1a2e;
    color: #AAA; border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 600;
}
.tab-bar button.active { background: #00E676; color: #000; border-color: #00E676; }
@media (max-width: 600px) {
    .grid-2, .grid-3 { grid-template-columns: 1fr; }
    .container { padding: 8px; }
}
</style>
</head>
<body>
<div class="container" id="app"></div>
<script>
// ===== STATE =====
let state = {
    token: localStorage.getItem('token') || '',
    user_id: localStorage.getItem('user_id') || '',
    username: localStorage.getItem('username') || '',
    is_activated: localStorage.getItem('is_activated') === 'true',
    is_admin: localStorage.getItem('is_admin') === 'true',
    lang: localStorage.getItem('lang') || 'Swahili',
    view: 'dashboard',
    farm: {},
    reminders: [],
    rounds: [],
    edit_date: null,
    edit_sale_key: null,
    edit_reminder: null,
    edit_dev_date: null,
    sub_info: { active: false, days_left: 0, end_text: '' },
    admin_users: [],
    admin_view_user: null,
    round_history_open: false,
    viewing_round: null,
};

function t(key) {
    const dict = {
        "Swahili": {
            "login_header": "🔒 Ingia Kwenye Akaunti", "signup_header": "📝 Fungua Akaunti Mpya",
            "username": "Jina la Mtumiaji", "password": "Neno la Siri",
            "login_btn": "🚀 Ingia Sasa", "signup_btn": "📝 Sajili na Uendelee Malipo",
            "no_account": "Hauna akaunti? Jisajili hapa", "have_account": "Umeshajisajili? Ingia hapa",
            "error_msg": "❌ Jina au neno la siri sio sahihi.", "error_fields": "❌ Tafadhali jaza sehemu zote!",
            "success_msg": "✅ Akaunti imefunguliwa! Tafadhali kamilisha malipo...",
            "login_success": "✅ Umefanikiwa kuingia!", "logout": "Ondoka",
            "welcome": "Usimamizi wa Kuku wa Nyama",
            "choice_inputs": "🛒 Maendeleo na Gharama", "choice_withdraw": "💰 Mauzo ya Kuku",
            "desc_inputs": "Sajili gharama, idadi ya vifaranga, chakula na vifo.",
            "desc_withdraw": "Sajili mauzo na wateja.",
            "back_btn": "← Rudi Dashibodi", "input_header": "🐣 Maendeleo na Gharama",
            "sales_header": "💰 Mauzo ya Kuku",
            "label_chicks_qty": "Idadi ya Vifaranga", "label_chicks": "Gharama ya Vifaranga (TSH)",
            "label_feed": "Gharama ya Chakula (TSH)", "label_med": "Gharama ya Dawa (TSH)",
            "label_other": "Gharama Nyingine (TSH)", "label_mortality": "Idadi ya Vifo",
            "label_date": "Chagua Tarehe:", "finish_inputs_btn": "🏁 Hifadhi Gharama",
            "finish_sales_btn": "🏁 Hifadhi Mauzo", "label_qty": "Idadi ya Kuku",
            "label_customer": "Jina la Mteja", "label_price": "Bei kwa Kuku (TSH)",
            "summary_header": "Muhtasari wa Fedha", "total_expenses": "Jumla ya Matumizi:",
            "total_revenue": "Jumla ya Mapato:", "calc_profit_btn": "📈 Piga Hesabu ya Faida",
            "profit_msg": "🎉 Faida ya", "loss_msg": "⚠️ Hasara ya",
            "no_records": "❌ Hakuna kumbukumbu.",
            "total_chicks": "Jumla Vifaranga", "deaths": "Vifo", "remaining": "Waliopo",
            "current_round": "Awamu ya Sasa", "move_to_next_round": "Nenda Awamu Inayofuata",
            "round_history": "Kumbukumbu za Awamu", "no_rounds": "Hakuna awamu za awali.",
            "round_archived": "Awamu imehifadhiwa!", "round_deleted": "Awamu imefutwa!",
            "reminders_title": "⏰ Vikumbusho", "add_reminder": "➕ Ongeza Kikumbusho",
            "no_reminders": "Hakuna vikumbusho.", "reminder_type": "Aina",
            "reminder_title": "Jina", "reminder_date": "Tarehe", "reminder_frequency": "Mara",
            "reminder_once": "Mara Moja", "reminder_daily": "Kila Siku",
            "reminder_weekly": "Kila Siku 7", "reminder_biweekly": "Kila Siku 14",
            "reminder_monthly": "Kila Siku 30", "reminder_status": "Hali",
            "reminder_done": "✅ Imefanyika", "reminder_pending": "⏳ Inasubiri",
            "reminder_overdue": "❌ Imechelewa", "mark_done": "✅ Imefanyika",
            "delete_reminder": "❌ Futa",
            "reminder_chanjo": "💉 Chanjo", "reminder_dawa": "💊 Dawa",
            "reminder_chakula": "🌾 Chakula", "reminder_general": "📌 Nyingine",
            "save_reminder_btn": "💾 Hifadhi Kikumbusho",
            "reminder_today": "Leo", "choose_language": "🌐 Chagua Lugha",
            "forgot_pass": "Umesahau password?", "sec_question": "Swali la Usalama",
            "sec_answer": "Jibu la Usalama", "verify_question": "Jibu Swali la Usalama",
            "wrong_answer": "❌ Jibu si sahihi!",
            "questions": ["Jina la mama yako?","Jina la mnyama wako wa kwanza?","Rangi yako favorite?","Mji uliozaliwa?","Chakula chako favorite?","Timu yako favorite?"],
            "kumbu_dev": "Kumbukumbu za Maendeleo", "kumbu_sale": "Kumbukumbu za Mauzo",
            "edit_btn": "✏️ Hariri", "save_btn": "💾 Hifadhi", "cancel_btn": "❌ Ghairi",
            "save_success": "Imerekebishwa!", "empty_name": "❌ Tafadhali ingiza jina!",
            "view_all": "👁 Angalia Zote",
        },
        "English": {
            "login_header": "🔒 Account Login", "signup_header": "📝 Create New Account",
            "username": "Username", "password": "Password",
            "login_btn": "🚀 Sign In", "signup_btn": "📝 Register & Pay",
            "no_account": "Don't have an account? Sign Up", "have_account": "Already have an account? Log In",
            "error_msg": "❌ Invalid Username or Password.", "error_fields": "❌ All fields are required.",
            "success_msg": "✅ Account Created! Please process payment...",
            "login_success": "✅ Login Successful!", "logout": "Logout",
            "welcome": "Broiler Batch Manager",
            "choice_inputs": "🛒 Development & Expenditure", "choice_withdraw": "💰 Broiler Sales",
            "desc_inputs": "Record expenses, chicks, feed, medicine and deaths.",
            "desc_withdraw": "Record customer sales.",
            "back_btn": "← Back to Dashboard", "input_header": "🐣 Development & Expenditure",
            "sales_header": "💰 Broiler Sales",
            "label_chicks_qty": "Number of Chicks", "label_chicks": "Total Cost of Chicks (TSH)",
            "label_feed": "Total Cost of Feeds (TSH)", "label_med": "Total Cost of Medicine (TSH)",
            "label_other": "Total Other Expenses (TSH)", "label_mortality": "Mortality Count",
            "label_date": "Select Date:", "finish_inputs_btn": "🏁 Save Expenses",
            "finish_sales_btn": "🏁 Save Sale", "label_qty": "Number of Chickens",
            "label_customer": "Customer Name", "label_price": "Price per Chicken (TSH)",
            "summary_header": "Financial Summary", "total_expenses": "Total Expenses:",
            "total_revenue": "Total Revenue:", "calc_profit_btn": "📈 Calculate Net Profit",
            "profit_msg": "🎉 Net Profit of", "loss_msg": "⚠️ Net Loss of",
            "no_records": "❌ No records found.",
            "total_chicks": "Total Chicks", "deaths": "Deaths", "remaining": "Remaining",
            "current_round": "Current Round", "move_to_next_round": "Move to Next Round",
            "round_history": "Round History", "no_rounds": "No previous rounds.",
            "round_archived": "Round archived!", "round_deleted": "Round deleted!",
            "reminders_title": "⏰ Reminders", "add_reminder": "➕ Add Reminder",
            "no_reminders": "No reminders.",
            "reminder_type": "Type", "reminder_title": "Title", "reminder_date": "Date", "reminder_frequency": "Frequency",
            "reminder_once": "Once", "reminder_daily": "Every Day", "reminder_weekly": "Every 7 Days",
            "reminder_biweekly": "Every 14 Days", "reminder_monthly": "Every 30 Days",
            "reminder_status": "Status", "reminder_done": "✅ Done", "reminder_pending": "⏳ Pending",
            "reminder_overdue": "❌ Overdue", "mark_done": "✅ Mark Done", "delete_reminder": "❌ Delete",
            "reminder_chanjo": "💉 Vaccine", "reminder_dawa": "💊 Medicine", "reminder_chakula": "🌾 Feed",
            "reminder_general": "📌 General", "save_reminder_btn": "💾 Save Reminder",
            "reminder_today": "Today", "choose_language": "🌐 Choose Language",
            "forgot_pass": "Forgot password?", "sec_question": "Security Question",
            "sec_answer": "Security Answer", "verify_question": "Answer Security Question",
            "wrong_answer": "❌ Wrong answer!",
            "questions": ["Mother's maiden name?","First pet name?","Favorite color?","Birth city?","Favorite food?","Favorite sports team?"],
            "kumbu_dev": "Development Records", "kumbu_sale": "Sales Records",
            "edit_btn": "✏️ Edit", "save_btn": "💾 Save", "cancel_btn": "❌ Cancel",
            "save_success": "Updated successfully!", "empty_name": "❌ Please enter customer name!",
            "view_all": "👁 View All",
        }
    };
    const d = dict[state.lang] || dict["Swahili"];
    return d[key] || key;
}

function setLang(lang) {
    state.lang = lang;
    localStorage.setItem('lang', lang);
    render();
}

function $(id) { return document.getElementById(id); }

async function api(method, url, data) {
    try {
        const opts = { method, headers: { 'Content-Type': 'application/json' } };
        if (data) opts.body = JSON.stringify(data);
        const res = await fetch(url, opts);
        return await res.json();
    } catch(e) {
        return { error: 'network' };
    }
}

// ===== VIEWS =====

function LoginView() {
    let html = '<div class="card" style="max-width:420px;margin:60px auto;">';
    html += '<div class="text-center mb-4"><span style="font-size:48px;">🔒</span>';
    html += `<h2 style="color:#00E676;margin:8px 0;">${t('login_header')}</h2></div>`;
    html += `<label>👤 ${t('username')}</label><input id="login_user" placeholder="Mfano: juma_2026">`;
    html += `<label>🔑 ${t('password')}</label><input id="login_pass" type="password" placeholder="Enter password">`;
    html += `<button class="btn mt-2" onclick="doLogin()">${t('login_btn')}</button>`;
    html += `<div id="login_err" class="text-red mt-2 text-center"></div>`;
    html += `<div class="text-center mt-4"><span class="text-muted">${t('no_account')}</span></div>`;
    html += `<button class="btn btn-outline mt-2" onclick="showSignup()">${t('signup_btn')}</button>`;
    html += `<div class="text-center mt-2"><button class="btn btn-outline btn-sm" onclick="showReset()">${t('forgot_pass')}</button></div>`;
    html += '</div>';
    return html;
}

function doLogin() {
    const user = $('login_user').value.trim();
    const pass = $('login_pass').value;
    if (!user || !pass) { $('login_err').textContent = t('error_fields'); return; }
    api('POST', '/api/login', { username: user, password: pass }).then(d => {
        if (d.ok) {
            state.token = d.token; state.user_id = d.user_id; state.username = d.username;
            state.is_activated = d.is_activated;
            state.is_admin = d.is_admin || false;
            state.farm = d.farm || {};
            state.reminders = d.reminders || []; state.sub_info = d.sub_info || { active: false };
            localStorage.setItem('token', d.token); localStorage.setItem('user_id', d.user_id);
            localStorage.setItem('username', d.username); localStorage.setItem('is_activated', d.is_activated);
            localStorage.setItem('is_admin', d.is_admin ? 'true' : 'false');
            state.view = d.is_admin ? 'admin' : 'dashboard';
            render();
        } else {
            $('login_err').textContent = t('error_msg');
        }
    });
}

function showSignup() { state.view = 'signup'; render(); }
function showReset() { state.view = 'reset'; render(); }

function SignupView() {
    let html = '<div class="card" style="max-width:420px;margin:60px auto;">';
    html += '<div class="text-center mb-4"><span style="font-size:48px;">📝</span>';
    html += `<h2 style="color:#00E676;margin:8px 0;">${t('signup_header')}</h2></div>`;
    html += `<label>👤 ${t('username')}</label><input id="reg_user" placeholder="Mfano: juma_2026">`;
    html += `<label>🔑 ${t('password')}</label><input id="reg_pass" type="password">`;
    html += `<label>${t('sec_question')}</label><select id="reg_secq">`;
    const questions = t('questions');
    for (let q of (Array.isArray(questions) ? questions : [])) {
        html += `<option value="${q}">${q}</option>`;
    }
    html += '</select>';
    html += `<label>${t('sec_answer')}</label><input id="reg_seca" placeholder="${t('sec_answer')}">`;
    html += `<button class="btn mt-2" onclick="doSignup()">${t('signup_btn')}</button>`;
    html += `<div id="signup_err" class="text-red mt-2 text-center"></div>`;
    html += `<div class="text-center mt-4"><span class="text-muted">${t('have_account')}</span></div>`;
    html += `<button class="btn btn-outline mt-2" onclick="showLogin()">Login</button>`;
    html += '</div>';
    return html;
}

function showLogin() { state.view = 'login'; render(); }

function doSignup() {
    const user = $('reg_user').value.trim();
    const pass = $('reg_pass').value;
    const secq = $('reg_secq').value;
    const seca = $('reg_seca').value.trim();
    if (!user || !pass) { $('signup_err').textContent = t('error_fields'); return; }
    api('POST', '/api/signup', { username: user, password: pass, security_question: secq, security_answer: seca }).then(d => {
        if (d.ok) {
            state.token = d.token; state.user_id = d.user_id; state.username = d.username;
            state.is_activated = false; state.farm = {};
            localStorage.setItem('token', d.token); localStorage.setItem('user_id', d.user_id);
            localStorage.setItem('username', d.username); localStorage.setItem('is_activated', 'false');
            state.view = 'payment'; render();
        } else if (d.error === 'exists') {
            $('signup_err').textContent = '❌ Jina la mtumiaji tayari lipo / Username already exists.';
        } else {
            $('signup_err').textContent = t('error_fields');
        }
    });
}

function ResetView() {
    let html = '<div class="card" style="max-width:420px;margin:60px auto;">';
    html += '<div class="text-center mb-4"><span style="font-size:48px;">🔑</span>';
    html += `<h2 style="color:#FFD700;margin:8px 0;">${t('forgot_pass')}</h2></div>`;
    html += `<label>👤 ${t('username')}</label><input id="reset_user" placeholder="Mfano: juma">`;
    html += `<button class="btn btn-gold mt-2" onclick="doResetVerify()">${t('verify_question')}</button>`;
    html += `<div id="reset_err" class="text-red mt-2 text-center"></div>`;
    html += `<div id="reset_question" class="hidden card mt-4"></div>`;
    html += `<button class="btn btn-outline mt-2" onclick="showLogin()">← Back</button>`;
    html += '</div>';
    return html;
}

let resetUserId = null;

function doResetVerify() {
    const user = $('reset_user').value.trim();
    if (!user) { $('reset_err').textContent = t('error_fields'); return; }
    api('POST', '/api/reset/verify', { username: user }).then(d => {
        if (d.ok) {
            resetUserId = d.user_id;
            $('reset_question').classList.remove('hidden');
            $('reset_question').innerHTML = `
                <p style="color:#FFF;font-weight:600;margin-bottom:8px;">${d.question}</p>
                <input id="reset_answer" placeholder="${t('sec_answer')}">
                <button class="btn btn-sm mt-2" onclick="doResetAnswer()">${t('verify_question')}</button>
                <div id="reset_ans_err" class="text-red mt-2"></div>
                <div id="reset_newpass" class="hidden mt-4">
                    <label>${t('password')} (Mpya)</label><input id="reset_pass1" type="password">
                    <label>Rudia Password</label><input id="reset_pass2" type="password">
                    <button class="btn btn-sm" onclick="doResetPassword()">${t('save_btn')}</button>
                </div>
            `;
        } else {
            $('reset_err').textContent = '❌ Username not found or no security question set.';
        }
    });
}

function doResetAnswer() {
    const ans = $('reset_answer').value.trim();
    api('POST', '/api/reset/answer', { user_id: resetUserId, answer: ans }).then(d => {
        if (d.ok) {
            $('reset_newpass').classList.remove('hidden');
        } else {
            $('reset_ans_err').textContent = t('wrong_answer');
        }
    });
}

function doResetPassword() {
    const p1 = $('reset_pass1').value;
    const p2 = $('reset_pass2').value;
    if (!p1 || !p2) return;
    if (p1 !== p2) { $('reset_ans_err').textContent = '❌ Passwords do not match!'; return; }
    api('POST', '/api/reset/password', { user_id: resetUserId, password: p1 }).then(d => {
        if (d.ok) {
            alert('✅ Password reset! Please login.');
            showLogin();
        }
    });
}

function PaymentView() {
    let html = '<div class="text-center mb-4"><span style="font-size:36px;">🐔</span>';
    html += '<h2 style="color:#FFF;margin:4px 0;">Mfugaji Kwanza</h2>';
    html += '<p class="text-muted">Broiler Manager</p></div>';
    html += '<div class="grid-2">';
    html += '<div class="card text-center"><span style="font-size:40px;">📋</span>';
    html += '<h3 style="color:#38bdf8;">Monthly Pass</h3>';
    html += '<div style="font-size:32px;font-weight:900;color:#FFD700;">TSH 10,000</div>';
    html += '<p class="text-muted">/ mwezi</p>';
    html += '<p style="color:#CCC;font-size:13px;">✅ All features unlocked</p></div>';
    html += '<div class="card text-center">';
    html += '<h3 style="color:#FFF;">🔓 Unlock App</h3>';
    html += `<p class="text-muted">${t('success_msg')}</p>`;
    html += '<a href="https://selar.co/9o12h598n9" target="_blank">';
    html += '<button class="btn btn-gold" style="font-size:22px;padding:20px;">💥 BOFYA HAPA KUFANYA MALIPO</button></a>';
    html += '<div class="text-muted mt-4" style="text-align:left;font-size:12px;line-height:1.8;">1. Bonyeza kitufe cha dhahabu<br>2. Kwenye Selar, bonyeza "Continue to Payment"<br>3. Chagua Tigo Pesa / Airtel / Halo / Card<br>4. Weka namba → "Pay Now"<br>5. Thibitisha PIN simu yako<br>6. Utarudishwa kiotomatiki</div>';
    html += `<button class="btn btn-outline mt-4" onclick="checkPayment()">🔄 Nimeisha lipa / I've paid</button>`;
    html += '</div></div>';
    return html;
}

function checkPayment() {
    api('POST', '/api/subscription/activate', { user_id: state.user_id }).then(d => {
        if (d.ok) {
            state.is_activated = true; state.sub_info = d.sub_info;
            localStorage.setItem('is_activated', 'true');
            state.view = 'dashboard'; render();
        }
    });
}

function DashboardView() {
    const farm = state.farm;
    const reminders = state.reminders || [];
    const today = new Date().toISOString().slice(0,10);
    const overdue = reminders.filter(r => r.due_date < today);
    const dueToday = reminders.filter(r => r.due_date === today);
    const upcoming = reminders.filter(r => r.due_date > today);
    
    let html = '';
    
    // alerts
    if (overdue.length) {
        for (let r of overdue) {
            html += `<div class="alert alert-error">🚨 <strong>${r.title}</strong> — ${t('reminder_overdue')} (${r.due_date})</div>`;
        }
    }
    if (dueToday.length) {
        for (let r of dueToday) {
            html += `<div class="alert alert-warning">⏰ <strong>${r.title}</strong> — ${t('reminder_today')} (${r.due_date})</div>`;
        }
    }
    if (upcoming.length) {
        for (let r of upcoming.slice(0,3)) {
            html += `<div class="alert alert-info">📌 <strong>${r.title}</strong> — ${r.due_date}</div>`;
        }
    }
    
    // sub info
    if (state.sub_info.end_text) {
        const isUrgent = state.sub_info.days_left <= 5;
        html += `<div class="alert ${isUrgent ? 'alert-error' : 'alert-warning'}">${state.sub_info.end_text}</div>`;
    }
    
    // header
    html += `<div class="flex-between mb-4"><div><h2 style="color:#FFF;">${t('welcome')}</h2></div>`;
    html += `<div><button class="btn btn-sm btn-outline" onclick="logout()">${t('logout')}</button></div></div>`;
    
    // round + stats
    let totalChicks = 0, totalMorts = 0, totalCosts = 0, totalRev = 0;
    for (let dk in farm) {
        const e = farm[dk];
        totalChicks += e.chicks_qty || 0;
        totalMorts += e.mortality || 0;
        totalCosts += (e.chicks_cost||0) + (e.feed_cost||0) + (e.med_cost||0) + (e.other_cost||0);
        for (let s of (e.sales_records||[])) totalRev += s.revenue || 0;
    }
    
    html += '<div class="grid-3 mb-4">';
    html += `<div class="stat-box"><div class="num text-blue">${totalChicks}</div><div class="label">${t('total_chicks')}</div></div>`;
    html += `<div class="stat-box"><div class="num text-red">${totalMorts}</div><div class="label">${t('deaths')}</div></div>`;
    html += `<div class="stat-box"><div class="num text-green">${totalChicks - totalMorts}</div><div class="label">${t('remaining')}</div></div>`;
    html += '</div>';
    
    // action buttons
    html += '<div class="grid-2 mb-4">';
    html += `<div class="card text-center"><span style="font-size:40px;">🐣</span>`;
    html += `<p style="font-weight:700;color:#38bdf8;">${t('choice_inputs')}</p>`;
    html += `<p class="text-muted">${t('desc_inputs')}</p>`;
    html += `<button class="btn" onclick="goInputs()">${t('choice_inputs')}</button></div>`;
    html += `<div class="card text-center"><span style="font-size:40px;">💰</span>`;
    html += `<p style="font-weight:700;color:#00E676;">${t('choice_withdraw')}</p>`;
    html += `<p class="text-muted">${t('desc_withdraw')}</p>`;
    html += `<button class="btn" onclick="goSales()">${t('choice_withdraw')}</button></div>`;
    html += '</div>';
    
    // financial summary
    const net = totalRev - totalCosts;
    html += '<div class="card">';
    html += `<h3 style="color:#00E676;">📊 ${t('summary_header')}</h3>`;
    html += `<div class="flex-between mt-2"><span class="text-muted">${t('total_expenses')}</span><span class="text-red" style="font-weight:800;font-size:20px;">${totalCosts.toLocaleString()} TSH</span></div>`;
    html += `<div class="flex-between mt-2"><span class="text-muted">${t('total_revenue')}</span><span class="text-green" style="font-weight:800;font-size:20px;">${totalRev.toLocaleString()} TSH</span></div>`;
    html += `<div class="flex-between mt-2" style="border-top:1px solid #2a2a4a;padding-top:10px;"><span class="text-muted" style="font-weight:700;">${net >= 0 ? t('profit_msg') : t('loss_msg')}</span><span style="font-weight:900;font-size:24px;color:${net>=0?'#00E676':'#FF5252'};">${Math.abs(net).toLocaleString()} TSH</span></div>`;
    html += '</div>';
    
    // reminders section
    html += '<div class="card mt-4">';
    html += `<h3 style="color:#FFD700;">⏰ ${t('reminders_title')}</h3>`;
    if (reminders.length) {
        for (let r of reminders.slice(0,5)) {
            const cls = r.due_date < today ? 'badge-red' : r.due_date === today ? 'badge-gold' : 'badge-blue';
            const lbl = r.due_date < today ? t('reminder_overdue') : r.due_date === today ? t('reminder_today') : r.due_date;
            html += `<div class="flex-between mt-2" style="padding:8px 10px;background:#12121a;border-radius:8px;">
                <span style="font-size:13px;">${r.title}</span>
                <span class="badge ${cls}">${lbl}</span>
            </div>`;
        }
    } else {
        html += `<p class="text-muted text-center mt-2">${t('no_reminders')}</p>`;
    }
    html += `<button class="btn btn-sm btn-outline mt-2" onclick="goReminders()">${t('add_reminder')}</button>`;
    html += '</div>';
    
    // === ROUND SECTION ===
    const rounds = state.rounds || [];
    const currentRound = rounds.length ? Math.max(...rounds.map(r => r.round_number)) + 1 : 1;
    
    html += '<div class="flex-between mt-4 mb-2">';
    html += `<div><span style="color:#888;font-size:12px;">${t('current_round')}</span> <span style="color:#00E676;font-size:22px;font-weight:800;margin-left:8px;">${currentRound}</span></div>`;
    html += `<button class="btn btn-sm btn-gold" onclick="archiveRound()" style="width:auto;">🔄 ${t('move_to_next_round')}</button>`;
    html += '</div>';
    
    // round history toggle
    const isOpen = state.round_history_open;
    html += '<div class="card" style="padding:14px;">';
    html += `<div class="flex-between" onclick="toggleRoundHist()" style="cursor:pointer;">
        <span style="color:#FFD700;font-weight:700;font-size:15px;">📦 ${t('round_history')} (${rounds.length})</span>
        <span style="color:#888;">${isOpen ? '▲' : '▼'}</span>
    </div>`;
    
    if (isOpen) {
        if (rounds.length) {
            for (let r of rounds) {
                const rn = r.round_number;
                const rdate = r.archived_at ? r.archived_at.slice(0,10) : '';
                html += `<div class="flex-between mt-2" style="padding:10px;background:#12121a;border-radius:8px;">
                    <div><span style="font-weight:600;color:#FFD700;">📦 ${rn}</span> <span class="text-muted">📅 ${rdate}</span></div>
                    <div>
                    <button class="btn btn-sm btn-outline" onclick="event.stopPropagation();viewRound(${rn})">👁 ${t('edit_btn')}</button>
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();delRound(${rn})">🗑️</button>
                    </div>
                </div>`;
            }
        } else {
            html += `<p class="text-muted text-center mt-2">${t('no_rounds')}</p>`;
        }
    }
    html += '</div>';
    
    // records buttons
    html += '<div class="grid-2 mt-4">';
    html += `<button class="btn btn-outline" onclick="goKumbuDev()">🐣 ${t('kumbu_dev')}</button>`;
    html += `<button class="btn btn-outline" onclick="goKumbuSale()">💰 ${t('kumbu_sale')}</button>`;
    html += '</div>';
    
    return html;
}

function toggleRoundHist() {
    state.round_history_open = !state.round_history_open;
    render();
}

function archiveRound() {
    if (!Object.keys(state.farm).length) { alert('No data to archive.'); return; }
    api('POST', '/api/round/archive', { token: state.token, farm: state.farm }).then(d => {
        if (d.ok) {
            state.farm = {};
            state.view = 'dashboard';
            api('GET', '/api/data/' + state.token).then(r => {
                if (r.farm) state.farm = r.farm;
                if (r.reminders) state.reminders = r.reminders;
                state.rounds = r.round_history || [];
                render();
            });
        }
    });
}

function viewRound(rn) {
    api('GET', '/api/round/' + state.token + '/' + rn).then(d => {
        if (d.error) return;
        state.viewing_round = d;
        state.view = 'view_round';
        render();
    });
}

function delRound(rn) {
    if (!confirm('Delete round ' + rn + '?')) return;
    api('POST', '/api/round/delete', { user_id: state.user_id, round_number: rn }).then(d => {
        if (d.ok) {
            api('GET', '/api/data/' + state.token).then(r => {
                state.rounds = r.round_history || [];
                render();
            });
        }
    });
}

function RoundView() {
    const data = state.viewing_round;
    if (!data) return '<p class="text-muted text-center">Loading...</p>';
    const farm = JSON.parse(data.farm || typeof data.farm === 'object' ? data.farm : {});
    const rnd = data.round || {};
    
    let html = `<button class="btn btn-outline btn-sm" onclick="state.view='dashboard';render()">← ${t('back_btn')}</button>`;
    html += `<div class="text-center mt-4"><span style="font-size:40px;">📦</span>`;
    html += `<h2 style="color:#FFD700;">📦 Round ${rnd.round_number}</h2>`;
    html += `<p class="text-muted">📅 ${rnd.archived_at ? rnd.archived_at.slice(0,10) : ''}</p></div>`;
    
    let totalChicks = 0, totalMorts = 0, totalCosts = 0, totalRev = 0;
    for (let dk in farm) {
        const e = farm[dk];
        totalChicks += e.chicks_qty || 0;
        totalMorts += e.mortality || 0;
        totalCosts += (e.chicks_cost||0)+(e.feed_cost||0)+(e.med_cost||0)+(e.other_cost||0);
        for (let s of (e.sales_records||[])) totalRev += s.revenue || 0;
    }
    const net = totalRev - totalCosts;
    html += '<div class="grid-3 mt-2">';
    html += `<div class="stat-box"><div class="num text-blue">${totalChicks}</div><div class="label">Total Chicks</div></div>`;
    html += `<div class="stat-box"><div class="num text-red">${totalMorts}</div><div class="label">Deaths</div></div>`;
    html += `<div class="stat-box"><div class="num text-green">${totalChicks-totalMorts}</div><div class="label">Remaining</div></div>`;
    html += '</div>';
    html += `<div class="card mt-2"><div class="flex-between"><span class="text-muted">Expenses</span><span class="text-red">${totalCosts.toLocaleString()} TSH</span></div>`;
    html += `<div class="flex-between"><span class="text-muted">Revenue</span><span class="text-green">${totalRev.toLocaleString()} TSH</span></div>`;
    html += `<div class="flex-between" style="border-top:1px solid #2a2a4a;padding-top:8px;margin-top:8px;"><span style="font-weight:700;">Net</span><span style="font-weight:900;color:${net>=0?'#00E676':'#FF5252'};">${Math.abs(net).toLocaleString()} TSH</span></div></div>`;
    
    for (let dk of Object.keys(farm).sort().reverse()) {
        const e = farm[dk];
        const dayCost = (e.chicks_cost||0)+(e.feed_cost||0)+(e.med_cost||0)+(e.other_cost||0);
        html += `<div class="card mt-2" style="padding:14px;"><div class="flex-between"><span style="font-weight:700;">📅 ${dk}</span>`;
        if (e.sales_records && e.sales_records.length) {
            let drev = e.sales_records.reduce((a,s) => a+(s.revenue||0), 0);
            html += `<span class="badge badge-gold">💰 ${drev.toLocaleString()} TSH</span>`;
        }
        html += '</div>';
        html += `<div class="grid-2 mt-2" style="font-size:13px;">
            <span class="text-muted">Chicks</span><span>${e.chicks_qty||0} 🐥</span>
            <span class="text-muted">Deaths</span><span class="text-red">${e.mortality||0}</span>
            <span class="text-muted">Cost</span><span>${dayCost.toLocaleString()} TSH</span>
        </div></div>`;
    }
    return html;
}

function goInputs() { state.view = 'inputs'; render(); }
function goSales() { state.view = 'sales'; render(); }
function goReminders() { state.view = 'reminders'; render(); }
function goKumbuDev() { state.view = 'kumbu_dev'; render(); }
function goKumbuSale() { state.view = 'kumbu_sale'; render(); }
function goProfit() { state.view = 'profit'; render(); }

function logout() {
    state.token = ''; state.user_id = ''; state.username = ''; state.is_activated = false;
    state.farm = {}; state.reminders = []; state.view = 'login';
    localStorage.removeItem('token'); localStorage.removeItem('user_id');
    localStorage.removeItem('username'); localStorage.removeItem('is_activated');
    render();
}

// ===== ADMIN VIEWS =====
function AdminView() {
    let html = `<div class="flex-between mb-4"><h2 style="color:#FFD700;">🛡️ Admin Panel</h2>`;
    html += `<div><span class="badge badge-gold">${state.username}</span> <button class="btn btn-sm btn-outline" onclick="logout()">Logout</button></div></div>`;
    
    // Fetch users only once
    if (!state.admin_users.length) {
        api('GET', '/api/admin/users/' + state.token).then(d => {
            if (d.users) state.admin_users = d.users;
            render();
        });
        html += '<div class="card"><p class="text-muted text-center">Loading users...</p></div>';
    } else {
        html += '<div class="card"><h3 style="color:#38bdf8;">👥 All Users</h3>';
        for (let u of state.admin_users) {
            const isAdmin = u.is_admin == 1 || u.is_admin === true || u.is_admin === '1';
            const isActive = u.is_activated == 1 || u.is_activated === true;
            html += `<div class="flex-between mt-2" style="padding:10px 14px;background:#12121a;border-radius:10px;">
                <div><span style="font-weight:600;">${u.username}</span>
                ${isAdmin ? '<span class="badge badge-gold" style="margin-left:6px;">Admin</span>' : ''}
                <span class="badge ${isActive ? 'badge-green' : 'badge-red'}" style="margin-left:6px;">
                    ${isActive ? 'Active' : 'Inactive'}</span>
                </div>
                <div>`;
            if (!isAdmin) {
                html += `<button class="btn btn-sm btn-outline" onclick="adminViewUser(${u.id})">👁</button>`;
                if (!isActive) {
                    html += `<button class="btn btn-sm btn-gold" onclick="adminActivate(${u.id})" style="margin-left:4px;">🔓</button>`;
                }
                html += `<button class="btn btn-sm btn-danger" onclick="adminDeleteUser(${u.id})" style="margin-left:4px;">🗑️</button>`;
            }
            html += `</div></div>`;
        }
        html += '</div>';
        html += '<button class="btn btn-outline mt-4" onclick="state.view=\'dashboard\';state.admin_users=[];render()">📊 Back to Dashboard</button>';
    }
    return html;
}

function adminViewUser(userId) {
    state.admin_view_user = userId;
    state.view = 'admin_user';
    render();
}

function adminActivate(userId) {
    api('GET', '/api/admin/activate/' + state.token + '/' + userId).then(d => {
        if (d.ok) {
            state.admin_users = [];
            state.view = 'admin'; render();
        }
    });
}

function adminDeleteUser(userId) {
    if (!confirm('Delete this user and all their data?')) return;
    api('GET', '/api/admin/delete_user/' + state.token + '/' + userId).then(d => {
        if (d.ok) {
            state.admin_users = [];
            state.view = 'admin'; render();
        }
    });
}

function AdminUserView() {
    let html = `<button class="btn btn-outline btn-sm" onclick="state.view='admin';state.admin_users=[];render()">← Back to Admin</button>`;
    const uid = state.admin_view_user;
    if (!uid) { state.view = 'admin'; state.admin_users = []; render(); return; }
    
    html += '<div id="admin_user_data" class="mt-4"><p class="text-muted text-center">Loading...</p></div>';
    
    api('GET', '/api/admin/user_data/' + state.token + '/' + uid).then(d => {
        if (d.error) return;
        const u = document.getElementById('admin_user_data');
        if (!u) return;
        let farm = d.farm || {};
        let reminders = d.reminders || [];
        let totalChicks = 0, totalMorts = 0, totalCosts = 0, totalRev = 0;
        for (let dk in farm) {
            const e = farm[dk];
            totalChicks += e.chicks_qty || 0;
            totalMorts += e.mortality || 0;
            totalCosts += (e.chicks_cost||0)+(e.feed_cost||0)+(e.med_cost||0)+(e.other_cost||0);
            for (let s of (e.sales_records||[])) totalRev += s.revenue || 0;
        }
        const today = new Date().toISOString().slice(0,10);
        let rh = `<div class="card mt-4"><h3 style="color:#00E676;">👤 ${d.username}</h3>`;
        rh += `<div class="grid-3 mt-2">
            <div class="stat-box"><div class="num text-blue">${totalChicks}</div><div class="label">Total Chicks</div></div>
            <div class="stat-box"><div class="num text-red">${totalMorts}</div><div class="label">Deaths</div></div>
            <div class="stat-box"><div class="num text-green">${totalChicks-totalMorts}</div><div class="label">Remaining</div></div>
        </div>`;
        const net = totalRev - totalCosts;
        rh += `<div class="flex-between mt-2"><span class="text-muted">Expenses</span><span class="text-red">${totalCosts.toLocaleString()} TSH</span></div>`;
        rh += `<div class="flex-between"><span class="text-muted">Revenue</span><span class="text-green">${totalRev.toLocaleString()} TSH</span></div>`;
        rh += `<div class="flex-between" style="border-top:1px solid #2a2a4a;padding-top:8px;margin-top:8px;"><span style="font-weight:700;">Net</span><span style="font-weight:900;color:${net>=0?'#00E676':'#FF5252'};">${Math.abs(net).toLocaleString()} TSH</span></div>`;
        rh += '</div>';
        if (reminders.length) {
            rh += '<div class="card mt-2"><h4 style="color:#FFD700;">⏰ Reminders</h4>';
            for (let r of reminders) {
                const cls = r.due_date < today ? 'badge-red' : r.due_date === today ? 'badge-gold' : 'badge-blue';
                rh += `<div class="flex-between mt-2" style="padding:8px;background:#12121a;border-radius:8px;"><span>${r.title}</span><span class="badge ${cls}">${r.due_date}</span></div>`;
            }
            rh += '</div>';
        }
        u.innerHTML = rh;
    });
    
    return html;
}

// ===== RENDER =====
function render() {
    const app = $('app');
    let html = '';
    
    // lang bar
    html += '<div class="lang-bar">';
    html += `<button class="${state.lang==='Swahili'?'active':''}" onclick="setLang('Swahili')">🇹🇿 Sw</button>`;
    html += `<button class="${state.lang==='English'?'active':''}" onclick="setLang('English')">🇬🇧 En</button>`;
    html += '</div>';
    
    // header
    html += '<div class="header"><h1>MFUGAJI KWANZA</h1><div class="sub">Modern Poultry Management System</div></div>';
    
    // view
    if (!state.token) {
        if (state.view === 'signup') html += SignupView();
        else if (state.view === 'reset') html += ResetView();
        else { state.view = 'login'; html += LoginView(); }
    } else if (state.is_admin && state.view === 'admin') {
        html += AdminView();
    } else if (state.is_admin && state.view === 'admin_user') {
        html += AdminUserView();
    } else if (!state.is_admin && !state.is_activated && state.view !== 'payment') {
        state.view = 'payment';
        html += PaymentView();
    } else if (state.view === 'payment') {
        html += PaymentView();
    } else if (state.view === 'dashboard') {
        html += DashboardView();
    } else if (state.view === 'inputs') {
        html += InputsView();
    } else if (state.view === 'sales') {
        html += SalesView();
    } else if (state.view === 'reminders') {
        html += RemindersView();
    } else if (state.view === 'kumbu_dev') {
        html += KumbuDevView();
    } else if (state.view === 'kumbu_sale') {
        html += KumbuSaleView();
    } else if (state.view === 'profit') {
        html += ProfitView();
    } else if (state.view === 'view_round') {
        html += RoundView();
    } else {
        state.view = state.is_admin ? 'admin' : 'dashboard';
        html += state.is_admin ? AdminView() : DashboardView();
    }
    
    app.innerHTML = html;
}

// Basic views to get started
function InputsView() {
    const today = new Date().toISOString().slice(0,10);
    let html = `<button class="btn btn-outline btn-sm" onclick="goDashboard()">${t('back_btn')}</button>`;
    html += '<div class="card mt-4">';
    html += `<h3 style="color:#38bdf8;">${t('input_header')}</h3>`;
    html += `<label>${t('label_date')}</label><input type="date" id="inp_date" value="${today}">`;
    html += `<label>${t('label_chicks_qty')}</label><input type="number" id="inp_qty" value="0" min="0">`;
    html += `<label>${t('label_chicks')}</label><input type="number" id="inp_chicks" value="0" min="0">`;
    html += `<label>${t('label_feed')}</label><input type="number" id="inp_feed" value="0" min="0">`;
    html += `<label>${t('label_med')}</label><input type="number" id="inp_med" value="0" min="0">`;
    html += `<label>${t('label_other')}</label><input type="number" id="inp_other" value="0" min="0">`;
    html += `<label>${t('label_mortality')}</label><input type="number" id="inp_mort" value="0" min="0">`;
    html += `<button class="btn mt-2" onclick="saveInputs()">${t('finish_inputs_btn')}</button>`;
    html += '</div>';
    return html;
}

function saveInputs() {
    const dk = $('inp_date').value;
    const entry = {
        chicks_qty: parseInt($('inp_qty').value) || 0,
        chicks_cost: parseFloat($('inp_chicks').value) || 0,
        feed_cost: parseFloat($('inp_feed').value) || 0,
        med_cost: parseFloat($('inp_med').value) || 0,
        other_cost: parseFloat($('inp_other').value) || 0,
        mortality: parseInt($('inp_mort').value) || 0,
        has_inputs: true, has_sales: false, sales_records: []
    };
    state.farm[dk] = entry;
    api('POST', '/api/save', { token: state.token, farm: { [dk]: entry } }).then(d => {
        if (d.ok) { state.view = 'dashboard'; render(); }
    });
}

function SalesView() {
    const today = new Date().toISOString().slice(0,10);
    let html = `<button class="btn btn-outline btn-sm" onclick="goDashboard()">${t('back_btn')}</button>`;
    html += '<div class="card mt-4">';
    html += `<h3 style="color:#00E676;">${t('sales_header')}</h3>`;
    html += `<label>${t('label_date')}</label><input type="date" id="sale_date" value="${today}">`;
    html += `<label>${t('label_customer')}</label><input id="sale_cust" placeholder="Jina la mteja">`;
    html += `<label>${t('label_qty')}</label><input type="number" id="sale_qty" value="1" min="1">`;
    html += `<label>${t('label_price')}</label><input type="number" id="sale_price" value="6500" min="0">`;
    html += `<button class="btn mt-2" onclick="saveSale()">${t('finish_sales_btn')}</button>`;
    html += '</div>';
    return html;
}

function saveSale() {
    const dk = $('sale_date').value;
    const cust = $('sale_cust').value.trim();
    if (!cust) { alert(t('empty_name')); return; }
    const qty = parseInt($('sale_qty').value) || 1;
    const price = parseFloat($('sale_price').value) || 0;
    const revenue = qty * price;
    if (!state.farm[dk]) state.farm[dk] = { chicks_qty:0, chicks_cost:0, feed_cost:0, med_cost:0, other_cost:0, mortality:0, has_inputs:false, has_sales:true, sales_records:[] };
    state.farm[dk].has_sales = true;
    state.farm[dk].sales_records.push({ customer: cust, qty, price, revenue });
    api('POST', '/api/save', { token: state.token, farm: state.farm }).then(d => {
        if (d.ok) { state.view = 'dashboard'; render(); }
    });
}

function RemindersView() {
    let html = `<button class="btn btn-outline btn-sm" onclick="goDashboard()">${t('back_btn')}</button>`;
    html += '<div class="card mt-4">';
    html += `<h3 style="color:#FFD700;">⏰ ${t('reminders_title')}</h3>`;
    
    // list existing
    const reminders = state.reminders || [];
    const today = new Date().toISOString().slice(0,10);
    if (reminders.length) {
        for (let r of reminders) {
            const cls = r.due_date < today ? 'badge-red' : r.due_date === today ? 'badge-gold' : 'badge-blue';
            const lbl = r.due_date < today ? t('reminder_overdue') : r.due_date === today ? t('reminder_today') : r.due_date;
            html += `<div class="flex-between mt-2" style="padding:10px;background:#12121a;border-radius:8px;">
                <div><span style="font-size:13px;font-weight:600;">${r.title}</span><br><span class="text-muted">${r.due_date}</span></div>
                <div><span class="badge ${cls}">${lbl}</span>
                <button class="btn btn-sm btn-outline" onclick="delReminder(${r.id})" style="margin-left:6px;">✕</button></div>
            </div>`;
        }
    } else {
        html += `<p class="text-muted text-center">${t('no_reminders')}</p>`;
    }
    
    // add new
    const todayStr = new Date().toISOString().slice(0,10);
    html += '<hr style="border-color:#2a2a4a;margin:16px 0;">';
    html += `<h4 style="color:#FFF;">${t('add_reminder')}</h4>`;
    html += `<input id="rem_title" placeholder="${t('reminder_title')}">`;
    html += `<label>${t('reminder_date')}</label><input type="date" id="rem_date" value="${todayStr}">`;
    html += `<label>${t('reminder_type')}</label><select id="rem_type">
        <option value="chanjo">${t('reminder_chanjo')}</option>
        <option value="dawa">${t('reminder_dawa')}</option>
        <option value="chakula">${t('reminder_chakula')}</option>
        <option value="general">${t('reminder_general')}</option>
    </select>`;
    html += `<button class="btn mt-2" onclick="addReminder()">${t('save_reminder_btn')}</button>`;
    html += '</div>';
    return html;
}

function addReminder() {
    const title = $('rem_title').value.trim();
    if (!title) return;
    const data = {
        token: state.token,
        title,
        due_date: $('rem_date').value,
        reminder_type: $('rem_type').value,
        frequency_days: 0,
        round_number: 1,
        description: ''
    };
    api('POST', '/api/reminder/add', data).then(d => {
        if (d.ok) {
            api('GET', '/api/data/' + state.token).then(r => {
                if (r.farm) state.farm = r.farm;
                if (r.reminders) state.reminders = r.reminders;
                state.view = 'dashboard'; render();
            });
        }
    });
}

function delReminder(id) {
    api('POST', '/api/reminder/delete', { id }).then(d => {
        api('GET', '/api/data/' + state.token).then(r => {
            if (r.reminders) state.reminders = r.reminders;
            render();
        });
    });
}

function KumbuDevView() {
    let html = `<button class="btn btn-outline btn-sm" onclick="goDashboard()">${t('back_btn')}</button>`;
    html += `<h3 class="mt-4" style="color:#38bdf8;">🐣 ${t('kumbu_dev')}</h3>`;
    const dates = Object.keys(state.farm).filter(d => state.farm[d].has_inputs).sort().reverse();
    if (!dates.length) {
        html += `<div class="card text-center mt-2"><p class="text-muted">${t('no_records')}</p></div>`;
        return html;
    }
    for (let dk of dates) {
        const e = state.farm[dk];
        html += `<div class="card mt-2" style="padding:16px;">
            <div class="flex-between"><span style="font-weight:700;">📅 ${dk}</span>
            <span class="badge badge-green">🐥 ${e.chicks_qty||0}</span></div>
            <div class="grid-2 mt-2" style="font-size:13px;">
                <span class="text-muted">${t('label_chicks')}</span><span>${(e.chicks_cost||0).toLocaleString()} TSH</span>
                <span class="text-muted">${t('label_feed')}</span><span>${(e.feed_cost||0).toLocaleString()} TSH</span>
                <span class="text-muted">${t('label_med')}</span><span>${(e.med_cost||0).toLocaleString()} TSH</span>
                <span class="text-muted">${t('label_other')}</span><span>${(e.other_cost||0).toLocaleString()} TSH</span>
                <span class="text-muted">${t('label_mortality')}</span><span class="text-red">${e.mortality||0}</span>
            </div>
        </div>`;
    }
    return html;
}

function KumbuSaleView() {
    let html = `<button class="btn btn-outline btn-sm" onclick="goDashboard()">${t('back_btn')}</button>`;
    html += `<h3 class="mt-4" style="color:#00E676;">💰 ${t('kumbu_sale')}</h3>`;
    const dates = Object.keys(state.farm).filter(d => state.farm[d].has_sales).sort().reverse();
    if (!dates.length) {
        html += `<div class="card text-center mt-2"><p class="text-muted">${t('no_records')}</p></div>`;
        return html;
    }
    for (let dk of dates) {
        const records = state.farm[dk].sales_records || [];
        if (!records.length) continue;
        let dayRev = records.reduce((a,r) => a + (r.revenue||0), 0);
        html += `<div class="card mt-2" style="padding:16px;">
            <div class="flex-between"><span style="font-weight:700;">📅 ${dk}</span>
            <span class="badge badge-gold">💰 ${dayRev.toLocaleString()} TSH</span></div>`;
        for (let r of records) {
            html += `<div class="flex-between mt-2" style="padding:8px;background:#12121a;border-radius:8px;">
                <span>👤 ${r.customer}</span>
                <span>🐔 ${r.qty} × ${(r.price||0).toLocaleString()} = <strong class="text-green">${(r.revenue||0).toLocaleString()} TSH</strong></span>
            </div>`;
        }
        html += '</div>';
    }
    return html;
}

function ProfitView() {
    let totalChicks = 0, totalMorts = 0, totalCosts = 0, totalRev = 0;
    let totalFeed = 0, totalMed = 0, totalOther = 0, totalChickCost = 0;
    for (let dk in state.farm) {
        const e = state.farm[dk];
        totalChicks += e.chicks_qty || 0;
        totalMorts += e.mortality || 0;
        totalChickCost += e.chicks_cost || 0;
        totalFeed += e.feed_cost || 0;
        totalMed += e.med_cost || 0;
        totalOther += e.other_cost || 0;
        for (let s of (e.sales_records||[])) totalRev += s.revenue || 0;
    }
    totalCosts = totalChickCost + totalFeed + totalMed + totalOther;
    let net = totalRev - totalCosts;
    let html = `<button class="btn btn-outline btn-sm" onclick="goDashboard()">${t('back_btn')}</button>`;
    html += `<div class="card mt-4 text-center" style="border:2px solid ${net>=0?'#00E676':'#FF5252'};">`;
    html += `<span style="font-size:48px;">${net>=0?'🎉':'⚠️'}</span>`;
    html += `<h2 style="color:${net>=0?'#00E676':'#FF5252'};font-size:36px;font-weight:900;">${net>=0?t('profit_msg'):t('loss_msg')} ${Math.abs(net).toLocaleString()} TSH</h2>`;
    html += `<div class="grid-2 mt-4" style="text-align:left;font-size:14px;">
        <span class="text-muted">🐥 ${t('total_chicks')}</span><span class="text-right" style="text-align:right;font-weight:700;">${totalChicks}</span>
        <span class="text-muted">❌ ${t('deaths')}</span><span class="text-right" style="text-align:right;font-weight:700;color:#FF5252;">${totalMorts}</span>
        <span class="text-muted">🌾 ${t('label_feed')}</span><span class="text-right" style="text-align:right;">${totalFeed.toLocaleString()} TSH</span>
        <span class="text-muted">💊 ${t('label_med')}</span><span class="text-right" style="text-align:right;">${totalMed.toLocaleString()} TSH</span>
        <span class="text-muted">🔧 ${t('label_other')}</span><span class="text-right" style="text-align:right;">${totalOther.toLocaleString()} TSH</span>
        <span class="text-muted" style="font-weight:700;">💰 ${t('total_expenses')}</span><span class="text-right" style="text-align:right;font-weight:800;color:#FF5252;">${totalCosts.toLocaleString()} TSH</span>
        <span class="text-muted" style="font-weight:700;">📦 ${t('total_revenue')}</span><span class="text-right" style="text-align:right;font-weight:800;color:#00E676;">${totalRev.toLocaleString()} TSH</span>
    </div></div>`;
    return html;
}

function goDashboard() { state.view = 'dashboard'; state.admin_users = []; render(); }

// ===== INIT =====
if (state.token) {
    api('GET', '/api/data/' + state.token).then(d => {
        if (d.error) { state.token = ''; render(); return; }
        state.farm = d.farm || {};
        state.reminders = d.reminders || [];
        state.sub_info = d.sub_info || { active: false };
        state.is_activated = d.is_activated || false;
        state.rounds = d.round_history || [];
        render();
    });
} else {
    render();
}
</script>
</body>
</html>
"""

@app.get("/{path:path}")
async def serve_spa(request: Request, path: str):
    if path.startswith("api/"):
        return {"error": "not_found"}
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=HTML_PAGE)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
