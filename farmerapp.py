import streamlit as st
import sqlite3
import time
from datetime import datetime, timedelta, date
import os

# --- Database Layer: Supports Supabase (cloud) and SQLite (local fallback) ---
use_supabase = False
sb = None
try:
    supabase_url = st.secrets.get("supabase", {}).get("url", os.environ.get("SUPABASE_URL", ""))
    supabase_key = st.secrets.get("supabase", {}).get("key", os.environ.get("SUPABASE_KEY", ""))
    if supabase_url and supabase_key:
        from supabase import create_client
        sb = create_client(supabase_url, supabase_key)
        use_supabase = True
except:
    pass

def get_db():
    conn = sqlite3.connect("farm_data.db")
    conn.row_factory = sqlite3.Row
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
    query = "*"
    if use_supabase:
        try:
            q = sb.table("reminders").select(query).eq("user_id", user_id).order("due_date")
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

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_activated INTEGER DEFAULT 0,
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
    if "subscription_start" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN subscription_start TEXT")
    if "subscription_end" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN subscription_end TEXT")
    if "security_question" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN security_question TEXT")
    if "security_answer" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN security_answer TEXT")
    conn.commit()
    conn.close()

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

def get_remaining_days(user_id):
    user = db_get_user_by_id(user_id)
    if not user:
        return 0
    subscription_end = user.get("subscription_end")
    if not subscription_end:
        return 0
    try:
        expiry = datetime.strptime(subscription_end, "%Y-%m-%d %H:%M:%S")
        remaining = (expiry - datetime.now()).days
        return max(0, remaining)
    except:
        return 0

def activate_subscription(user_id, days=30):
    now = datetime.now()
    expiry = now + timedelta(days=days)
    db_update_user(user_id, {
        "is_activated": 1,
        "subscription_start": now.strftime("%Y-%m-%d %H:%M:%S"),
        "subscription_end": expiry.strftime("%Y-%m-%d %H:%M:%S")
    })
    return expiry

def load_data():
    if "current_user_id" not in st.session_state:
        return
    uid = st.session_state.current_user_id
    if uid is None:
        return
    frows = db_get_farm_dates(uid)
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
    srows = db_get_sales_records(uid)
    for s in srows:
        dk = s["date_key"]
        if dk in farm:
            farm[dk]["sales_records"].append({
                "customer": s["customer"], "qty": s["qty"],
                "price": s["price"], "revenue": s["revenue"]
            })
    st.session_state.farm_database = farm

def save_data():
    if "current_user_id" not in st.session_state or st.session_state.current_user_id is None:
        return
    uid = st.session_state.current_user_id
    for dk, entry in st.session_state.farm_database.items():
        db_upsert_farm_date(uid, dk, entry)
        db_delete_sales_records(uid, dk)
        for rec in entry.get("sales_records", []):
            db_insert_sale_record(uid, dk, rec)

def load_rounds():
    if "current_user_id" not in st.session_state or st.session_state.current_user_id is None:
        return
    uid = st.session_state.current_user_id
    rows = db_get_rounds(uid)
    st.session_state.rounds_list = rows
    if rows:
        st.session_state.current_round = max(r["round_number"] for r in rows) + 1
    else:
        st.session_state.current_round = 1



# --- Page Configuration ---
st.set_page_config(
    page_title="Mfugaji Kwanza - Broiler Manager",
    page_icon="&#x1f414;",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'Get Help': None,
        'Report a Bug': None,
        'About': None
    }
)

# --- Initialize Session States ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "is_activated" not in st.session_state:
    st.session_state.is_activated = False
if "language" not in st.session_state:
    st.session_state.language = "Swahili"
if "sub_view" not in st.session_state:
    st.session_state.sub_view = "dashboard"
if "auth_screen" not in st.session_state:
    st.session_state.auth_screen = "login"  
if "profit_calculated" not in st.session_state:
    st.session_state.profit_calculated = False
if "edit_dev_date" not in st.session_state:
    st.session_state.edit_dev_date = None
if "edit_sale_key" not in st.session_state:
    st.session_state.edit_sale_key = None
if "current_user_id" not in st.session_state:
    st.session_state.current_user_id = None
if "current_username" not in st.session_state:
    st.session_state.current_username = None
if "farm_database" not in st.session_state:
    st.session_state.farm_database = {}
if "current_round" not in st.session_state:
    st.session_state.current_round = 1
if "rounds_list" not in st.session_state:
    st.session_state.rounds_list = []
if "viewing_round" not in st.session_state:
    st.session_state.viewing_round = None
if "confirm_delete_round" not in st.session_state:
    st.session_state.confirm_delete_round = None
if "round_history_expanded" not in st.session_state:
    st.session_state.round_history_expanded = False
if "expanded_round" not in st.session_state:
    st.session_state.expanded_round = None
if "edit_reminder_id" not in st.session_state:
    st.session_state.edit_reminder_id = None

init_db()

# ==========================================
# MFUMO WA KIOTOMATIKI WA USOMAJI WA MALIPO KUTOKA SELAR
# ==========================================
query_params = st.query_params
if "status" in query_params and "token" in query_params:
    if query_params["status"] == "success" and query_params["token"] == "Erasto_HEIS5_Boss_2026":
        if st.session_state.current_user_id:
            expiry = activate_subscription(st.session_state.current_user_id, days=30)
            st.session_state.is_activated = True
            st.query_params.clear()

def init_date_entry(target_date_str):
    if target_date_str not in st.session_state.farm_database:
        st.session_state.farm_database[target_date_str] = {
            "chicks_qty": 0,       # Idadi ya vifaranga/kuku walioingizwa bandani
            "chicks_cost": 0.0, 
            "feed_cost": 0.0, 
            "med_cost": 0.0, 
            "other_cost": 0.0,
            "mortality": 0, 
            "sales_records": [],   # Orodha ya mauzo ya wateja: [{"customer": "Name", "qty": X, "price": Y, "revenue": Z}]
            "has_inputs": False, 
            "has_sales": False
        }

broiler_bg_url = "https://images.unsplash.com/photo-1548550023-2bdb3c5beed7?q=80&w=1600&auto=format&fit=crop"

# --- Kamusi ya Lugha ---
translations = {
    "English": {
        "title": "MFUGAJI KWANZA", "subtitle": "Modern Poultry Management System",
        "login_header": "&#x1f512; Account Login", "signup_header": "&#x1f4dd; Create New Account",
        "username": "Username", "password": "Password", "full_name": "Full Name",
        "login_btn": "Sign In Securely &#x1f680;", "signup_btn": "Register & Proceed to Payment &#x1f4dd;",
        "go_to_signup": "Don't have an account? Sign Up here", "go_to_login": "Already have an account? Log In here",
        "error_msg": "&#x274c; Invalid Username or Password.", "error_fields": "&#x274c; All fields are required.",
        "success_msg": "&#x1f389; Account Created! Please process activation payment...", "login_success": "&#x1f389; Login Successful!",
        "welcome": "Broiler Batch Manager", "instruction": "Select an option below to manage development or sales.",
        "choice_inputs": "&#x1f6d2; Development & Expenditure", "choice_withdraw": "&#x1f4b0; Broiler Sales (Customers)",
        "desc_inputs": "Record expenses for chicks, feeds, medications, and batch entry.", "desc_withdraw": "Record customer names, chickens bought, and sales revenue.",
        "back_btn": "&#x2190; Back to Dashboard", "input_header": "&#x1f423; Development & Expenditure",
        "sales_header": "&#x1f4b0; Broiler Sales", 
        "label_chicks_qty": "Number of Chicks Introduced Today",
        "label_chicks": "Total Cost of Chicks (TSH)",
        "label_feed": "Total Cost of Feeds (TSH)", "label_med": "Total Cost of Medicine (TSH)",
        "label_other": "Total Cost of Other Expenses (TSH)", "label_mortality": "Mortality Count",
        "label_date": "Select Date:", "finish_inputs_btn": "&#x1f3c1; Save Expenses & Batch Details",
        "finish_sales_btn": "&#x1f3c1; Save & Record Customer Purchase", "label_qty": "Number of Chickens Bought",
        "label_customer": "Customer Name", "label_price": "Price per Chicken (TSH)",
        "summary_header": "&#x1f4ca; Financial Summary",
        "total_expenses": "Total Expenses:", "total_revenue": "Total Revenue:",
        "calc_profit_btn": "&#x1f4c8; Calculate Net Profit", "profit_msg": "&#x1f389; Net Profit:", "loss_msg": "&#x26a0;&#xfe0f; Net Loss:",
        "no_records": "&#x274c; No records found.",
        "kumbu_dev_title": "&#x1f423; Development Records",
        "kumbu_dev_desc": "View and edit development & expense records",
        "kumbu_sale_title": "&#x1f4b0; Sales Records",
        "kumbu_sale_desc": "View and edit customer sales records",
        "open_kumbu_dev": "&#x1f423; Open Records",
        "open_kumbu_sale": "&#x1f4b0; Open Records",
        "back_dashboard": "&#x2190; Back to Dashboard",
        "edit_btn": "&#x270f;&#xfe0f; Edit",
        "no_dev_records": "No development records yet.",
        "no_dev_hint": "Go to dashboard and click 'Development & Expenditure' to start recording.",
        "no_sale_records": "No sales records yet.",
        "no_sale_hint": "Go to dashboard and click 'Broiler Sales' to start recording.",
        "total_chicks": "Total Chicks Entered",
        "deaths": "Deaths",
        "remaining": "Remaining",
        "chicks_summary": "&#x1f425; Total Chicks: {}  |  &#x274c; Deaths: {}  |  &#x2705; Remaining: {}",
        "profit_chicks": "&#x1f425; Total Chicks: {} Entered  |  &#x274c; Deaths: {}  |  &#x2705; Remaining: {}",
        "edit_record_title": "&#x270f;&#xfe0f; Edit Record: {}",
        "edit_sale_title": "&#x270f;&#xfe0f; Edit Sale: {}",
        "save_btn": "&#x1f4be; Save",
        "cancel_btn": "&#x274c; Cancel",
        "save_success": "Updated successfully!",
        "save_success_sale": "Sale for",
        "record_header": "&#x1f4cb; Farm Records",
        "empty_name": "&#x274c; Please enter customer name!",
        "chicks_input_label": "Number of Chicks",
        "chicks_cost_label": "Chicks Cost (TSH)",
        "feed_cost_label": "Feed Cost (TSH)",
        "med_cost_label": "Medicine Cost (TSH)",
        "other_cost_label": "Other Costs (TSH)",
        "mortality_label": "Mortality Count",
        "day_qty_badge": "{} Chickens",
        "day_sales_total": "&#x1f4e6; Total Revenue: {:,.0f} TSH",
        "record_back": "&#x2190; Back to Dashboard",
        "logout": "Logout (Ondoka)",
        "customer_placeholder": "E.g. Juma, Mama Maria, etc.",
        "chickens": "Chickens",
        "choose_language": "&#x1f310; Choose Language",
        "pass_placeholder": "Enter your password",
        "selar_howto": "1. Click \"BOFYA HAPA KUFANYA MALIPO\"\n2. On Selar, click \"Continue to Payment\"\n3. Choose: Tigo Pesa / Airtel / Halo / Card\n4. Enter phone -> click \"Pay Now\"\n5. Confirm with PIN on your phone\n6. You'll be redirected back automatically\n7. Account activates automatically",
        "current_round": "Current Round",
        "move_to_next_round": "Move to Next Round",
        "round_history": "Round History",
        "round_label": "Round {}",
        "no_rounds": "No previous rounds yet.",
        "no_rounds_hint": "Click 'Move to Next Round' to archive the current batch.",
        "view_round": "View",
        "delete_round": "Delete",
        "confirm_delete_round": "Are you sure?",
        "round_archived": "Round archived! Starting new round...",
        "round_deleted": "Round deleted!",
        "viewing_round_title": "Viewing Round {}",
        "viewing_back": "Back to Dashboard",
        "archived_at": "Archived on",
        "forgot_pass": "Forgot password?",
        "reset_pass_title": "&#x1f511; Reset Password",
        "reset_pass_btn": "&#x2705; Reset Password",
        "reset_success": "&#x1f389; Password reset successful! Login with your new password.",
        "reset_user_not_found": "&#x274c; Username not found!",
        "reset_pass_mismatch": "&#x274c; Passwords do not match!",
        "reset_pass_empty": "&#x274c; Please fill all fields!",
        "back_to_login": "&#x2190; Back to Login",
        "sec_question": "Security Question",
        "sec_answer": "Security Answer",
        "sec_question_hint": "Choose a question only you know the answer to",
        "sec_answer_hint": "Your secret answer (case sensitive)",
        "verify_question": "Answer Security Question",
        "verify_question_hint": "Answer the question you set during signup",
        "wrong_answer": "&#x274c; Wrong answer! Try again.",
        "questions": [
            "What is your mother's maiden name?",
            "What was the name of your first pet?",
            "What is your favorite color?",
            "What city were you born in?",
            "What is your favorite food?",
            "What is your favorite sports team?"
        ],
        "reminders_title": "&#x1f4cb; Reminders & Schedule",
        "add_reminder": "&#x2795; Add Reminder",
        "view_all_reminders": "&#x1f441; View All",
        "no_reminders": "No reminders yet.",
        "no_reminders_hint": "Click 'Add Reminder' to create one.",
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
        "reminder_done": "&#x2705; Done",
        "reminder_pending": "&#x23f3; Pending",
        "reminder_overdue": "&#x274c; Overdue",
        "mark_done": "&#x2705; Mark Done",
        "delete_reminder": "&#x274c; Delete",
        "reminder_saved": "Reminder saved!",
        "reminder_deleted": "Reminder deleted!",
        "reminder_updated": "Reminder updated!",
        "reminder_type_chanjo": "&#x1f489; Vaccine",
        "reminder_type_dawa": "&#x1f48a; Medicine",
        "reminder_type_chakula": "&#x1f33e; Feed",
        "reminder_type_general": "&#x1f4cc; General",
        "save_reminder_btn": "&#x1f4be; Save Reminder",
        "reminder_subtitle": "Manage vaccination, medicine, feed & general reminders",
        "back_to_reminders": "&#x2190; Back to Reminders",
        "reminder_desc": "Description (optional)",
        "reminder_desc_placeholder": "E.g. Give with water in the morning",
        "reminder_round": "Round",
        "reminders_due_soon": "Due Soon",
        "reminders_overdue_text": "Overdue",
        "reminders_upcoming": "Upcoming",
        "reminders_done_text": "Completed",
        "reminder_snooze": "&#x23f0; Snooze 1 Day",
        "reminder_edit": "&#x270f; Edit",
        "reminder_today": "Today",
        "reminder_tomorrow": "Tomorrow",
        "reminder_header": "&#x1f4cb; All Reminders",
    },
    "Swahili": {
        "title": "MFUGAJI KWANZA", "subtitle": "Mfumo wa Kisasa wa Usimamizi wa Kuku",
        "login_header": "&#x1f512; Ingia Kwenye Akaunti", "signup_header": "&#x1f4dd; Fungua Akaunti Mpya",
        "username": "Jina la Mtumiaji", "password": "Neno la Siri (Password)", "full_name": "Jina Lako Kamili",
        "login_btn": "Ingia Sasa &#x1f680;", "signup_btn": "Sajili na Uendelee kwenye Malipo &#x1f4dd;",
        "go_to_signup": "Hauna akaunti bado? Jisajili hapa", "go_to_login": "Umeshajisajili? Ingia hapa",
        "error_msg": "&#x274c; Jina au neno la siri sio sahihi.", "error_fields": "&#x274c; Sehemu zote zinatakiwa kujazwa.",
        "success_msg": "&#x1f389; Akaunti imefunguliwa! Tafadhali kamilisha malipo...", "login_success": "&#x1f389; Umefanikiwa kuingia!",
        "welcome": "Usimamizi wa Kuku wa Nyama (Broiler)", "instruction": "Chagua hatua hapa chini kusajili gharama au mauzo.",
        "choice_inputs": "&#x1f6d2; Maendeleo na Gharama za Vifaranga", "choice_withdraw": "&#x1f4b0; Mauzo ya Kuku (Wateja)",
        "desc_inputs": "Sajili gharama, idadi ya vifaranga walioingia, chakula na vifo.", "desc_withdraw": "Sajili majina ya wateja, idadi ya kuku walionunua na pesa waliyolipa.",
        "back_btn": "&#x2190; Rudi Kwenye Dashibodi", "input_header": "&#x1f423; Maendeleo na Gharama za Vifaranga",
        "sales_header": "&#x1f4b0; Mauzo ya Kuku (Broiler Sales)", 
        "label_chicks_qty": "Idadi ya Vifaranga Walioingia Siku Hii",
        "label_chicks": "Gharama ya Kununua Vifaranga (TSH)",
        "label_feed": "Gharama ya Chakula (TSH)", "label_med": "Gharama ya Chanjo na Dawa (TSH)",
        "label_other": "Gharama Nyinginezo (TSH)", "label_mortality": "Idadi ya Waliokufa (Vifo vya Leo)",
        "label_date": "Chagua Tarehe:", "finish_inputs_btn": "&#x1f3c1; Hifadhi Matumizi na Data za Vifaranga",
        "finish_sales_btn": "&#x1f3c1; Hifadhi Mauzo ya Mteja Huyu", "label_qty": "Idadi ya Kuku Alionunua Mteja",
        "label_customer": "Jina la Mteja", "label_price": "Bei kwa Kila Kuku (TSH)",
        "summary_header": "&#x1f4ca; Muhtasari wa Mapato na Faida",
        "total_expenses": "Jumla ya Matumizi:", "total_revenue": "Jumla ya Mapato:",
        "calc_profit_btn": "&#x1f4c8; Piga Hesabu ya Net Profit", "profit_msg": "&#x1f389; Shamba limeingiza FAIDA ya", "loss_msg": "&#x26a0;&#xfe0f; Shamba limeingiza HASARA ya",
        "no_records": "&#x274c; Hakuna kumbukumbu tarehe hii.",
        "kumbu_dev_title": "&#x1f423; Kumbukumbu ya Maendeleo",
        "kumbu_dev_desc": "Angalia na hariri rekodi za maendeleo na gharama",
        "kumbu_sale_title": "&#x1f4b0; Kumbukumbu ya Mauzo",
        "kumbu_sale_desc": "Angalia na hariri rekodi za mauzo na wateja",
        "open_kumbu_dev": "&#x1f423; Fungua Kumbukumbu",
        "open_kumbu_sale": "&#x1f4b0; Fungua Kumbukumbu",
        "back_dashboard": "&#x2190; Rudi Kwenye Dashibodi",
        "edit_btn": "&#x270f;&#xfe0f; Badilisha",
        "no_dev_records": "Hakuna kumbukumbu za maendeleo bado.",
        "no_dev_hint": "Rudi kwenye dashibodi na bonyeza 'Maendeleo na Gharama' kuanza kurekodi.",
        "no_sale_records": "Hakuna kumbukumbu za mauzo bado.",
        "no_sale_hint": "Rudi kwenye dashibodi na bonyeza 'Mauzo ya Kuku' kuanza kurekodi.",
        "total_chicks": "Jumla Vifaranga",
        "deaths": "Vifo",
        "remaining": "Waliopo",
        "chicks_summary": "&#x1f425; Jumla Vifaranga: {}  |  &#x274c; Vifo: {}  |  &#x2705; Waliopo: {}",
        "profit_chicks": "&#x1f425; Jumla ya Vifaranga Walioingia: {}  |  &#x274c; Vifo: {}  |  &#x2705; Vifaranga Waliopo: {}",
        "edit_record_title": "&#x270f;&#xfe0f; Hariri Kumbukumbu: {}",
        "edit_sale_title": "&#x270f;&#xfe0f; Hariri Mauzo: {}",
        "save_btn": "&#x1f4be; Hifadhi",
        "cancel_btn": "&#x274c; Ghairi",
        "save_success": "Imerekebishwa!",
        "save_success_sale": "Mauzo ya",
        "record_header": "&#x1f4cb; Kumbukumbu za Shamba",
        "empty_name": "&#x274c; Tafadhali ingiza Jina la Mteja!",
        "chicks_input_label": "Idadi ya Vifaranga",
        "chicks_cost_label": "Gharama ya Vifaranga (TSH)",
        "feed_cost_label": "Gharama ya Chakula (TSH)",
        "med_cost_label": "Gharama ya Dawa (TSH)",
        "other_cost_label": "Nyinginezo (TSH)",
        "mortality_label": "Idadi ya Vifo",
        "day_qty_badge": "{} Kuku",
        "day_sales_total": "&#x1f4e6; Jumla ya Mapato: {:,.0f} TSH",
        "record_back": "&#x2190; Rudi Kwenye Dashibodi",
        "logout": "Logout (Ondoka)",
        "customer_placeholder": "Mfano: Juma, Mama Maria, n.k.",
        "chickens": "Kuku",
        "choose_language": "&#x1f310; Chagua Lugha",
        "pass_placeholder": "Weka neno la siri hapa",
        "selar_howto": "1. Bonyeza \"BOFYA HAPA KUFANYA MALIPO\"\n2. Kwenye Selar, bonyeza \"Continue to Payment\"\n3. Chagua: Tigo Pesa / Airtel / Halo / Card\n4. Weka namba -> bonyeza \"Pay Now\"\n5. Thibitisha kwa PIN simu yako\n6. Utarudishwa kwenye app moja kwa moja\n7. Akaunti itafunguka kiotomatiki",
        "current_round": "Awamu ya Sasa",
        "move_to_next_round": "Nenda Awamu Inayofuata",
        "round_history": "Kumbukumbu za Awamu",
        "round_label": "Awamu {}",
        "no_rounds": "Hakuna awamu za awali bado.",
        "no_rounds_hint": "Bonyeza 'Nenda Awamu Inayofuata' kuhifadhi awamu hii.",
        "view_round": "Angalia",
        "delete_round": "Futa",
        "confirm_delete_round": "Una uhakika?",
        "round_archived": "Awamu imehifadhiwa! Kuanza awamu mpya...",
        "round_deleted": "Awamu imefutwa!",
        "viewing_round_title": "Kuangalia Awamu {}",
        "viewing_back": "Rudi Kwenye Dashibodi",
        "archived_at": "Ilihifadhiwa tarehe",
        "forgot_pass": "Umesahau password?",
        "reset_pass_title": "&#x1f511; Weka Password Mpya",
        "reset_pass_btn": "&#x2705; Badilisha Password",
        "reset_success": "&#x1f389; Password imebadilishwa! Ingia na password mpya.",
        "reset_user_not_found": "&#x274c; Jina la mtumiaji halikupatikana!",
        "reset_pass_mismatch": "&#x274c; Password hazifanani!",
        "reset_pass_empty": "&#x274c; Tafadhali jaza sehemu zote!",
        "back_to_login": "&#x2190; Rudi Kwenye Kuingia",
        "sec_question": "Swali la Usalama",
        "sec_answer": "Jibu la Usalama",
        "sec_question_hint": "Chagua swali ambalo wewe pekee ndio unajua jibu lake",
        "sec_answer_hint": "Jibu lako la siri (andika sawa sawa)",
        "verify_question": "Jibu Swali la Usalama",
        "verify_question_hint": "Jibu swali uliloweka wakati wa kujiandikisha",
        "wrong_answer": "&#x274c; Jibu si sahihi! Jaribu tena.",
        "questions": [
            "Jina la mama yako ni nani?",
            "Jina la mnyama wako wa kwanza ni nani?",
            "Rangi yako favorite ni gani?",
            "Mji uliozaliwa ni gani?",
            "Chakula chako favorite ni kipi?",
            "Timu yako favorite ya michezo ni gani?"
        ],
        "reminders_title": "&#x1f4cb; Vikumbusho na Ratiba",
        "add_reminder": "&#x2795; Ongeza Kikumbusho",
        "view_all_reminders": "&#x1f441; Angalia Zote",
        "no_reminders": "Hakuna vikumbusho bado.",
        "no_reminders_hint": "Bonyeza 'Ongeza Kikumbusho' kuunda kipya.",
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
        "reminder_done": "&#x2705; Imefanyika",
        "reminder_pending": "&#x23f3; Inasubiri",
        "reminder_overdue": "&#x274c; Imechelewa",
        "mark_done": "&#x2705; Imefanyika",
        "delete_reminder": "&#x274c; Futa",
        "reminder_saved": "Kikumbusho kimehifadhiwa!",
        "reminder_deleted": "Kikumbusho kimefutwa!",
        "reminder_updated": "Kikumbusho kimebadilishwa!",
        "reminder_type_chanjo": "&#x1f489; Chanjo",
        "reminder_type_dawa": "&#x1f48a; Dawa",
        "reminder_type_chakula": "&#x1f33e; Chakula",
        "reminder_type_general": "&#x1f4cc; Nyingine",
        "save_reminder_btn": "&#x1f4be; Hifadhi Kikumbusho",
        "reminder_subtitle": "Dhibiti vikumbusho vya chanjo, dawa, chakula na mengine",
        "back_to_reminders": "&#x2190; Rudi Kwenye Vikumbusho",
        "reminder_desc": "Maelezo (si lazima)",
        "reminder_desc_placeholder": "Mfano: Changanya na maji asubuhi",
        "reminder_round": "Awamu",
        "reminders_due_soon": "Inakaribia",
        "reminders_overdue_text": "Imechelewa",
        "reminders_upcoming": "Inayofuata",
        "reminders_done_text": "Imekamilika",
        "reminder_snooze": "&#x23f0; Nikumbushe Kesho",
        "reminder_edit": "&#x270f; Badilisha",
        "reminder_today": "Leo",
        "reminder_tomorrow": "Kesho",
        "reminder_header": "&#x1f4cb; Vikumbusho Vyote",
    }
}

lang = st.session_state.language
t = translations[lang]

# --- CSS Styling ---
st.markdown(f"""
    <style>
    .stApp {{ background-image: url("{broiler_bg_url}"); background-size: cover; background-position: center; background-repeat: no-repeat; background-attachment: fixed; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.78); z-index: 0; }}
    [data-testid="stHeader"] {{ display: none !important; }}
    .stApp header {{ display: none !important; }}
    #MainMenu {{ visibility: hidden !important; }}
    footer {{ visibility: hidden !important; }}
    [data-testid="stToolbar"] {{ display: none !important; }}
    [data-testid="stDecoration"] {{ display: none !important; }}
    .eczjsme18 {{ display: none !important; }}
    .main .block-container {{ z-index: 1; padding-top: 1.2rem !important; max-width: 100% !important; padding-left: 1.5rem !important; padding-right: 1.5rem !important; }}
    .reportview-container {{ margin: 0 !important; padding: 0 !important; border: none !important; }}
    .reportview-container .main {{ padding: 0 !important; }}
    #root > div:first-child {{ border: none !important; }}
    .brand-title {{ color: #FFFFFF; font-family: 'Arial Black', sans-serif; font-weight: 900; font-size: 36px; text-shadow: 3px 3px 6px rgba(0,0,0,0.8); text-align: center; letter-spacing:2px; }}
    .brand-subtitle {{ font-size: 13px; color: #00E676; display: block; margin-top: -5px; font-weight: 600; letter-spacing:1px; }}
    
    /* Auth & Dashboard Cards */
    .auth-card, [data-testid="stForm"], .stForm {{ background: linear-gradient(145deg,#1a1a2e,#16213e) !important; border: 1px solid #2a2a4a !important; border-radius: 20px !important; padding: 32px !important; box-shadow: 0 8px 32px rgba(0,0,0,0.4) !important; }}
    .dashboard-card {{ background: linear-gradient(145deg,#1a1a2e,#16213e) !important; border: 1px solid #2a2a4a !important; border-radius: 20px !important; padding: 28px !important; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.4); transition: transform 0.2s; }}
    
    label[data-testid="stWidgetLabel"] p {{ color: #DDD !important; font-weight: 600 !important; font-size: 14px !important; }}
    input, input[type="text"], input[type="password"], input[type="number"], input[type="date"], input[type="email"], input[type="tel"], input[type="url"], input[type="search"], textarea, select, .stTextInput, .stNumberInput, .stDateInput, .stTextArea, [data-testid="stTextInput"], [data-testid="stNumberInput"], [data-testid="stDateInput"] {{ background-color: #0a0a1a !important; color: #FFF !important; border: 1px solid #3a3a5a !important; border-radius: 12px !important; padding: 12px 16px !important; font-weight: 500 !important; font-size: 15px !important; }}
    input:focus, input[type="text"]:focus, input[type="password"]:focus, input[type="number"]:focus {{ border-color: #00E676 !important; box-shadow: 0 0 0 2px rgba(0,230,118,0.15) !important; }}
    [data-baseweb="input"] input, [data-baseweb="input"] textarea {{ background-color: #0a0a1a !important; color: #FFF !important; }}
    .st-bb, .st-bc, .st-bd, .st-be, .st-bf, .st-bg {{ background-color: #0a0a1a !important; color: #FFF !important; }}
    ::placeholder {{ color: #666 !important; font-size: 13px !important; }}
    
    div.stButton > button {{ background: linear-gradient(135deg,#00E676,#00c853) !important; color: #000 !important; border-radius: 14px !important; border: none !important; padding: 14px 24px !important; font-weight: 800 !important; font-size: 16px !important; width: 100%; transition: all 0.2s; box-shadow: 0 4px 15px rgba(0,230,118,0.3) !important; letter-spacing: 0.5px !important; }}
    div.stButton > button:hover {{ transform: translateY(-2px) !important; box-shadow: 0 6px 25px rgba(0,230,118,0.6) !important; }}
    div.stButton > button:active {{ transform: translateY(0px) !important; }}
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg,#00E676,#00c853) !important; box-shadow: 0 4px 20px rgba(0,230,118,0.5) !important; }}
    div.stButton > button[kind="primary"]:hover {{ box-shadow: 0 6px 30px rgba(0,230,118,0.8) !important; }}
    
    .auth-switch {{ color: #888; text-align: center; margin-top: 16px; font-size: 14px; }}
    .auth-switch a {{ color: #00E676; text-decoration: none; font-weight: 600; cursor: pointer; }}
    .auth-switch a:hover {{ color: #00FF5E; text-decoration: underline; }}
    </style>
    """, unsafe_allow_html=True)

# --- Top Header ---
col_title, col_lang = st.columns([4, 1.3])
with col_title:
    st.markdown(f'<div class="brand-title">MFUGAJI KWANZA <span class="brand-subtitle">{t["subtitle"]}</span></div>', unsafe_allow_html=True)
with col_lang:
    st.markdown(f'<div style="text-align:right; margin-bottom:2px;"><span style="color:#AAA; font-size:11px; font-weight:600;">{t["choose_language"]}</span></div>', unsafe_allow_html=True)
    lang_sw = st.session_state.language == "Swahili"
    st.markdown("""<style>button[kind="primary"],button[kind="secondary"]{padding:2px 6px!important;font-size:11px!important;border-radius:4px!important;min-height:0!important;line-height:1!important;}</style>""", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("&#x1f1f9;&#x1f1ff; Sw", key="lang_sw", use_container_width=True, type="primary" if lang_sw else "secondary"):
            if st.session_state.language != "Swahili":
                st.session_state.language = "Swahili"
                st.rerun()
    with col_b:
        if st.button("&#x1f1ec;&#x1f1e7; En", key="lang_en", use_container_width=True, type="primary" if not lang_sw else "secondary"):
            if st.session_state.language != "English":
                st.session_state.language = "English"
                st.rerun()

# ==========================================
# SEHEMU YA 1: AUTHENTICATION FLOW
# ==========================================
if not st.session_state.logged_in:
    _, center_auth, _ = st.columns([1, 1.8, 1])
    with center_auth:
        if st.session_state.auth_screen == "login":
            st.markdown("""<div class="auth-card">""", unsafe_allow_html=True)
            with st.form(key="login_secure_form"):
                st.markdown(f"""<div style="text-align:center; margin-bottom:20px;">
                    <span style="font-size:48px;">&#x1f512;</span>
                    <h3 style="color:#00E676; margin:8px 0 2px 0; font-size:24px; font-weight:800;">{t["login_header"]}</h3>
                </div>""", unsafe_allow_html=True)
                user_input = st.text_input("&#x1f464; " + t["username"], placeholder="Mfano: juma, mama_maria")
                pass_input = st.text_input("&#x1f511; " + t["password"], type="password", placeholder=t["pass_placeholder"])
                if st.form_submit_button("&#x1f680; " + t["login_btn"]):
                    username_clean = user_input.strip()
                    user = db_get_user_by_username(username_clean)
                    if user and user.get("password") == pass_input:
                        user_id = user["id"]
                        subscription_active = check_subscription_expiry(user_id)
                        
                        st.session_state.current_user_id = user_id
                        st.session_state.current_username = username_clean
                        st.session_state.logged_in = True
                        st.session_state.is_activated = subscription_active
                        load_data()
                        load_rounds()
                        
                        if subscription_active:
                            st.success(t["login_success"])
                        else:
                            st.warning("&#x23f0; Muda wa malipo umekwisha! Tafadhali lipia tena. / Subscription expired! Please pay again.")
                        time.sleep(1.0)
                        st.rerun()
                    else:
                        st.error(t["error_msg"])
            st.markdown("</div>", unsafe_allow_html=True)
            if st.button(t["forgot_pass"], key="btn_forgot_pass", use_container_width=True):
                st.session_state.auth_screen = "reset_password"
                st.rerun()
            if st.button("&#x1f4dd; "+t["go_to_signup"], key="go_to_signup_btn", use_container_width=True):
                st.session_state.auth_screen = "signup"
                st.rerun()

        elif st.session_state.auth_screen == "signup":
            st.markdown("""<div class="auth-card">""", unsafe_allow_html=True)
            with st.form(key="signup_secure_form"):
                st.markdown(f"""<div style="text-align:center; margin-bottom:20px;">
                    <span style="font-size:48px;">&#x1f4dd;</span>
                    <h3 style="color:#00E676; margin:8px 0 2px 0; font-size:24px; font-weight:800;">{t["signup_header"]}</h3>
                </div>""", unsafe_allow_html=True)
                reg_name = st.text_input("&#x1f464; " + t["full_name"], placeholder="Mfano: Juma Mohamedi")
                reg_user = st.text_input("&#x1f465; " + t["username"], placeholder="Mfano: juma_2026")
                reg_pass = st.text_input("&#x1f511; " + t["password"], type="password", placeholder=t["pass_placeholder"])
                sec_q = st.selectbox("&#x1f512; " + t["sec_question"], t["questions"], placeholder=t["sec_question_hint"])
                sec_a = st.text_input("&#x1f511; " + t["sec_answer"], placeholder=t["sec_answer_hint"])
                if st.form_submit_button("&#x2705; " + t["signup_btn"]):
                    username_clean = reg_user.strip()
                    if reg_name and username_clean and reg_pass and sec_q and sec_a:
                        try:
                            existing = db_get_user_by_username(username_clean)
                            if existing:
                                st.error("&#x274c; Jina la mtumiaji tayari lipo / Username already exists.")
                            else:
                                user_id = db_insert_user(username_clean, reg_pass, 0, sec_q, sec_a.strip())
                                st.session_state.current_user_id = user_id
                                st.session_state.current_username = username_clean
                                st.session_state.logged_in = True
                                st.session_state.is_activated = False
                                load_data()
                                load_rounds()
                                st.success(t["success_msg"])
                                time.sleep(1.5)
                                st.rerun()
                        except Exception as e:
                            st.error("&#x274c; Jina la mtumiaji tayari lipo / Username already exists.")
                    else:
                        st.error(t["error_fields"])
            st.markdown("</div>", unsafe_allow_html=True)
            if st.button("&#x1f511; "+t["go_to_login"], key="go_to_login_btn", use_container_width=True):
                st.session_state.auth_screen = "login"
                st.rerun()

        elif st.session_state.auth_screen == "reset_password":
            if "rp_step" not in st.session_state:
                st.session_state.rp_step = "verify_user"
            if st.session_state.rp_step == "verify_user":
                st.markdown("""<div class="auth-card">""", unsafe_allow_html=True)
                st.markdown(f"""<div style="text-align:center; margin-bottom:20px;">
                    <span style="font-size:48px;">&#x1f50d;</span>
                    <h3 style="color:#FFD700; margin:8px 0 2px 0; font-size:24px; font-weight:800;">{t["reset_pass_title"]}</h3>
                </div>""", unsafe_allow_html=True)
                rp_user = st.text_input("&#x1f464; " + t["username"], placeholder="Mfano: juma, mama_maria", key="rp_user")
                if st.button("&#x1f50d; " + t["verify_question"], type="primary", use_container_width=True):
                    u = rp_user.strip()
                    if u:
                        user = db_get_user_by_username(u)
                        if user and user.get("security_question"):
                            st.session_state.rp_user_id = user["id"]
                            st.session_state.rp_question = user["security_question"]
                            st.session_state.rp_answer = user["security_answer"]
                            st.session_state.rp_step = "verify_answer"
                            st.rerun()
                        else:
                            st.error(t["reset_user_not_found"])
                    else:
                        st.error(t["reset_pass_empty"])
                st.markdown("</div>", unsafe_allow_html=True)
                if st.button("&#x2190; "+t["back_to_login"], key="btn_back_to_login", use_container_width=True):
                    st.session_state.rp_step = "verify_user"
                    st.session_state.pop("rp_user_id", None)
                    st.session_state.pop("rp_question", None)
                    st.session_state.pop("rp_answer", None)
                    st.session_state.auth_screen = "login"
                    st.rerun()
            elif st.session_state.rp_step == "verify_answer":
                st.markdown("""<div class="auth-card">""", unsafe_allow_html=True)
                st.markdown(f"""<div style="text-align:center; margin-bottom:20px;">
                    <span style="font-size:48px;">&#x1f511;</span>
                    <h3 style="color:#FFD700; margin:8px 0 2px 0; font-size:24px; font-weight:800;">{t["verify_question"]}</h3>
                </div>""", unsafe_allow_html=True)
                st.markdown(f'<p style="color:#FFF; font-size:16px; font-weight:600; text-align:center; margin-bottom:12px;">{st.session_state.rp_question}</p>', unsafe_allow_html=True)
                rp_answer_input = st.text_input("&#x1f511; " + t["sec_answer"], placeholder=t["sec_answer_hint"], key="rp_answer_input")
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    if st.button("&#x2190; " + t["back_to_login"], use_container_width=True):
                        st.session_state.rp_step = "verify_user"
                        st.session_state.pop("rp_user_id", None)
                        st.session_state.pop("rp_question", None)
                        st.session_state.pop("rp_answer", None)
                        st.session_state.auth_screen = "login"
                        st.rerun()
                with col_a2:
                    if st.button("&#x2705; " + t["verify_question"], type="primary", use_container_width=True):
                        if rp_answer_input.strip() == st.session_state.rp_answer:
                            st.session_state.rp_step = "new_password"
                            st.rerun()
                        else:
                            st.error(t["wrong_answer"])
                st.markdown("</div>", unsafe_allow_html=True)
            elif st.session_state.rp_step == "new_password":
                st.markdown("""<div class="auth-card">""", unsafe_allow_html=True)
                st.markdown(f"""<div style="text-align:center; margin-bottom:20px;">
                    <span style="font-size:48px;">&#x1f511;</span>
                    <h3 style="color:#00E676; margin:8px 0 2px 0; font-size:24px; font-weight:800;">{t["reset_pass_title"]}</h3>
                </div>""", unsafe_allow_html=True)
                rp_pass1 = st.text_input("&#x1f511; " + t["password"] + " (Mpya)", type="password", placeholder=t["pass_placeholder"], key="rp_pass1")
                rp_pass2 = st.text_input("&#x1f511; " + "Rudia Password Mpya", type="password", placeholder="Andika tena password", key="rp_pass2")
                if st.button("&#x2705; " + t["reset_pass_btn"], type="primary", use_container_width=True):
                    p1 = rp_pass1.strip()
                    p2 = rp_pass2.strip()
                    if p1 and p2:
                        if p1 == p2:
                            db_update_user(st.session_state.rp_user_id, {"password": p1})
                            st.success(t["reset_success"])
                            time.sleep(1.5)
                            st.session_state.rp_step = "verify_user"
                            st.session_state.pop("rp_user_id", None)
                            st.session_state.pop("rp_question", None)
                            st.session_state.pop("rp_answer", None)
                            st.session_state.auth_screen = "login"
                            st.rerun()
                        else:
                            st.error(t["reset_pass_mismatch"])
                    else:
                        st.error(t["reset_pass_empty"])
                st.markdown("</div>", unsafe_allow_html=True)
                if st.button("&#x2190; "+t["back_to_login"], key="btn_back_login2", use_container_width=True):
                    st.session_state.rp_step = "verify_user"
                    st.session_state.pop("rp_user_id", None)
                    st.session_state.pop("rp_question", None)
                    st.session_state.pop("rp_answer", None)
                    st.session_state.auth_screen = "login"
                    st.rerun()

# ==========================================
# SEHEMU YA 2: BANGO LA MALIPO KUPITIA SELAR
# ==========================================
elif st.session_state.logged_in and not st.session_state.is_activated:
    st.markdown("""
    <div style="text-align:center; margin: 10px 0 20px 0;">
        <span style="font-size:36px;">&#x1f414;</span>
        <h2 style="color:#FFF; margin:4px 0 0 0; font-weight:800; font-size:28px;">Mfugaji Kwanza</h2>
        <p style="color:#888; font-size:14px; margin:0;">Broiler Manager</p>
    </div>
    """, unsafe_allow_html=True)

    col_plan, col_pay = st.columns([1.2, 1.8])

    with col_plan:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#0d1b2a,#1b2838); border-radius:16px; padding:24px; border:1px solid #1e3a5f; box-shadow:0 4px 24px rgba(0,0,0,0.3); height:100%;">
            <div style="font-size:40px; text-align:center; margin-bottom:4px;">&#x1f4cb;</div>
            <h3 style="color:#38bdf8; text-align:center; font-weight:800; font-size:20px; margin:4px 0 12px 0;">Monthly Pass</h3>
            <div style="text-align:center; margin-bottom:16px;">
                <span style="font-size:36px; font-weight:900; color:#FFD700;">TSH 10,000</span>
                <span style="color:#888; font-size:14px; display:block;">/ mwezi mmoja</span>
            </div>
            <div style="border-top:1px solid #1e3a5f; padding-top:12px;">
                <p style="color:#CCC; font-size:13px; margin:6px 0;">&#x2705; Udhibiti wa kuku wote</p>
                <p style="color:#CCC; font-size:13px; margin:6px 0;">&#x2705; Kumbukumbu za maendeleo</p>
                <p style="color:#CCC; font-size:13px; margin:6px 0;">&#x2705; Kumbukumbu za mauzo</p>
                <p style="color:#CCC; font-size:13px; margin:6px 0;">&#x2705; Faida na hasara kwa wakati halisi</p>
                <p style="color:#CCC; font-size:13px; margin:6px 0;">&#x2705; Msaada wa lugha mbili (Sw/En)</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_pay:
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#0a1628,#111827); border-radius:16px; padding:24px; border:1px solid #1e3a5f; box-shadow:0 4px 24px rgba(0,0,0,0.3); height:100%;">
            <h3 style="color:#FFF; text-align:center; font-weight:700; font-size:18px; margin:0 0 16px 0;">&#x1f513; {t['success_msg'].split('!')[0] if '!' in t['success_msg'] else t['success_msg']}</h3>
        </div>
        """, unsafe_allow_html=True)

        # Hatua ya 1: Glowing pay button
        st.markdown("""
        <style>
        @keyframes glowPulse {
            0% { box-shadow: 0 0 8px #FFD700, 0 0 16px #FFD700, 0 0 24px #FFD700; }
            50% { box-shadow: 0 0 16px #FFD700, 0 0 32px #FFD700, 0 0 48px #FFD700; }
            100% { box-shadow: 0 0 8px #FFD700, 0 0 16px #FFD700, 0 0 24px #FFD700; }
        }
        div.stLinkButton a {
            background:linear-gradient(135deg, #FFD700, #FFA500) !important;
            color:#000 !important; font-size:26px !important; font-weight:900 !important;
            border:none !important; border-radius:16px !important; padding:22px 16px !important;
            animation:glowPulse 2s ease-in-out infinite !important;
            text-shadow:0 1px 2px rgba(255,255,255,0.3) !important;
            letter-spacing:1px !important;
            transition:transform 0.2s !important;
            text-decoration:none !important;
        }
        div.stLinkButton a:hover { transform:scale(1.02) !important; }
        div.stLinkButton a:active { transform:scale(0.98) !important; }
        div.stLinkButton a p { font-size:26px !important; font-weight:900 !important; }
        </style>
        """, unsafe_allow_html=True)
        st.link_button("&#x1f4a5; BOFYA HAPA KUFANYA MALIPO", url="https://selar.co/9o12h598n9", use_container_width=True)

        st.markdown(f"""
        <div style="margin:16px 0; padding:14px; background:#0a0a1a; border-radius:12px; border:1px solid #2a2a1a;">
            <p style="color:#FFD700; font-size:14px; font-weight:700; margin:0 0 8px 0;">&#x1f4d6; Mwongozo / Guide:</p>
            <p style="color:#DDD; font-size:13px; line-height:1.8; margin:0; white-space:pre-line;">{t['selar_howto']}</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin:20px 0 12px 0;">
            <span style="background:#FFD700; color:#000; border-radius:50%; width:24px; height:24px; display:inline-flex; align-items:center; justify-content:center; font-weight:800; font-size:13px; flex-shrink:0;">2</span>
            <span style="color:#CCC; font-size:14px; font-weight:600;">Maliza malipo kule Selar / Complete payment on Selar</span>
        </div>
        <div style="margin-left:34px; margin-bottom:16px;">
            <span style="background:#0a1a0a; border:1px solid #1a3a1a; border-radius:8px; padding:6px 12px; font-size:12px; color:#00E676; display:inline-block;">Tigo Pesa</span>
            <span style="background:#0a0a1a; border:1px solid #1a1a3a; border-radius:8px; padding:6px 12px; font-size:12px; color:#888; display:inline-block; margin-left:6px;">Airtel Money</span>
            <span style="background:#1a0a0a; border:1px solid #3a1a1a; border-radius:8px; padding:6px 12px; font-size:12px; color:#F88; display:inline-block; margin-left:6px;">Halopesa</span>
            <span style="background:#0a0a1a; border:1px solid #1a1a3a; border-radius:8px; padding:6px 12px; font-size:12px; color:#888; display:inline-block; margin-left:6px;">&#x1f4b3; Card</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
            <span style="background:#00E676; color:#000; border-radius:50%; width:24px; height:24px; display:inline-flex; align-items:center; justify-content:center; font-weight:800; font-size:13px; flex-shrink:0;">3</span>
            <span style="color:#CCC; font-size:14px; font-weight:600;">Subiri uelekezwe kwenye app / Wait to be redirected back</span>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#0a1a0a,#102810); border-radius:12px; padding:16px; border:1px solid #1a3a1a; margin-bottom:16px;">
            <p style="color:#00E676; font-size:13px; font-weight:700; margin:0 0 6px 0;">&#x2705; Baada ya malipo kukamilika / After payment completes:</p>
            <p style="color:#CCC; font-size:12px; margin:2px 0;">
            Selar itakuelekeza tena kwenye app hii moja kwa moja na akaunti yako itafunguliwa kiotomatiki.
            <br>Selar will redirect you back to this app automatically and your account will be activated immediately.
            </p>
            <p style="color:#FFD700; font-size:12px; margin:8px 0 0 0;">
            &#x26a0;&#xfe0f; Ikiwa huelekezwi, bonyeza kitufe cha dhahabu juu tena na kamilisha malipo.
            <br>If not redirected, click the gold button above again to complete payment.
            </p>
        </div>
        """, unsafe_allow_html=True)

# ==========================================
# SEHEMU YA 3: DASHBOARD & TRANSACTIONS
# ==========================================
else:
    if st.session_state.current_user_id:
        subscription_active = check_subscription_expiry(st.session_state.current_user_id)
        if not subscription_active:
            st.session_state.is_activated = False
            st.warning("&#x23f0; Muda wa malipo umekwisha! Tafadhali lipia tena. / Subscription expired! Please pay again.")
            time.sleep(1)
            st.rerun()
    
    if st.query_params:
        st.query_params.clear()
    
    user_sub = db_get_user_by_id(st.session_state.current_user_id)
    
    subscription_end_text = ""
    if user_sub and user_sub.get("subscription_end"):
        try:
            expiry_date = datetime.strptime(user_sub["subscription_end"], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            days_remaining = (expiry_date - now).days
            if days_remaining > 0:
                if days_remaining <= 5:
                    subscription_end_text = f"&#9888;&#65039; TAHADHARI: Siku {days_remaining} zimesalia! Lipia sasa! / WARNING: {days_remaining} days left! Pay now!"
                else:
                    subscription_end_text = f"&#128337; Malipo yanaisha kwa siku {days_remaining} / Subscription expires in {days_remaining} days"
            elif days_remaining == 0:
                subscription_end_text = "&#9888; Malipo yanaisha leo! / Subscription expires today!"
        except:
            pass
    
    if subscription_end_text:
        bg = "background:linear-gradient(135deg,#2a0a0a,#3a1010)" if days_remaining <= 5 else "background:linear-gradient(135deg,#1a1a0a,#2a2a1a)"
        bd = "border-left:5px solid #FF5252" if days_remaining <= 5 else "border-left:5px solid #FFD700"
        clr = "#FF5252" if days_remaining <= 5 else "#FFD700"
        st.markdown(f"""
        <div style="{bg}; border-radius:12px; padding:12px; margin-bottom:8px; {bd};">
            <p style="color:{clr}; margin:0; font-size:14px; font-weight:700;">{subscription_end_text}</p>
        </div>
        """, unsafe_allow_html=True)
        if days_remaining <= 5:
            st.link_button("&#x1f4a5; LIPIA SASA / PAY NOW", url="https://selar.co/9o12h598n9", use_container_width=True)
        
    # Hesabu Jumla ya Maisha ya Shamba (Lifetime Summary)
    lifetime_costs = 0.0
    lifetime_revenue = 0.0
    for date_key in st.session_state.farm_database:
        entry = st.session_state.farm_database[date_key]
        lifetime_costs += entry.get("chicks_cost", 0) + entry.get("feed_cost", 0) + entry.get("med_cost", 0) + entry.get("other_cost", 0)
        for record in entry["sales_records"]:
            lifetime_revenue += record["revenue"]

    if st.session_state.sub_view == "dashboard":
        st.markdown(f"""<div style="text-align:center; margin-bottom:20px;">
            <h2 style="color:#FFF; margin:0; font-size:30px; font-weight:800;">{t["welcome"]}</h2>
        </div>""", unsafe_allow_html=True)

        col_round, col_next = st.columns([1, 1])
        with col_round:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0a1628,#111827); border-radius:12px; padding:12px 20px; margin-bottom:18px; border:1px solid #2a2a4a;">
                <span style="color:#888; font-size:12px;">{t['current_round']}</span>
                <span style="color:#00E676; font-size:22px; font-weight:800; margin-left:8px;">{st.session_state.current_round}</span>
            </div>
            """, unsafe_allow_html=True)
        with col_next:
            if st.button("&#x1f504; " + t["move_to_next_round"], use_container_width=True):
                if st.session_state.farm_database:
                    import json
                    save_data()
                    summary_json = json.dumps(st.session_state.farm_database)
                    db_archive_round(st.session_state.current_user_id, st.session_state.current_round, summary_json)
                    db_clear_user_data(st.session_state.current_user_id)
                    st.session_state.farm_database = {}
                    st.session_state.current_round += 1
                    load_rounds()
                    st.success(t["round_archived"])
                    time.sleep(1.0)
                    st.rerun()
                else:
                    st.warning("No data to archive. Hakuna data ya kuhifadhi.")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0a1a2e,#0f2840); border:1px solid #1a3a5a; border-radius:20px; padding:24px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,0.4); min-height:170px; display:flex; flex-direction:column; justify-content:center;">
                <div style="font-size:44px; margin-bottom:6px;">&#x1f423;</div>
                <div style="color:#38bdf8; font-size:18px; font-weight:700;">{t["choice_inputs"]}</div>
                <p style="color:#789; font-size:12px; margin-top:4px;">{t["desc_inputs"]}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("&#x1f423; "+t["choice_inputs"], key="go_to_inputs", use_container_width=True):
                st.session_state.sub_view = "inputs"
                st.session_state.profit_calculated = False
                st.rerun()
        with col2:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0a2a0a,#103a10); border:1px solid #205a20; border-radius:20px; padding:24px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,0.4); min-height:170px; display:flex; flex-direction:column; justify-content:center;">
                <div style="font-size:44px; margin-bottom:6px;">&#x1f4b0;</div>
                <div style="color:#00E676; font-size:18px; font-weight:700;">{t["choice_withdraw"]}</div>
                <p style="color:#789; font-size:12px; margin-top:4px;">{t["desc_withdraw"]}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("&#x1f4b0; "+t["choice_withdraw"], key="go_to_sales", use_container_width=True):
                st.session_state.sub_view = "withdraw"
                st.session_state.profit_calculated = False
                st.rerun()

        st.markdown("<hr style='border-color:#2a2a3a; margin:20px 0;'>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#0a1628,#111827); border-radius:18px; padding:20px 24px; border-left:6px solid #00E676; box-shadow:0 8px 24px rgba(0,0,0,0.3);">
            <h3 style="color:#00E676; margin:0 0 12px 0; font-weight:800; font-size:20px;">&#x1f4ca; {t['summary_header']}</h3>
            <div style="display:flex; gap:30px; flex-wrap:wrap;">
                <div style="flex:1; min-width:180px;">
                    <span style="color:#AAA; font-size:13px;">{t['total_expenses']}</span>
                    <div style="color:#FF5252; font-size:24px; font-weight:800;">{lifetime_costs:,.0f} TSH</div>
                </div>
                <div style="flex:1; min-width:180px;">
                    <span style="color:#AAA; font-size:13px;">{t['total_revenue']}</span>
                    <div style="color:#00E676; font-size:24px; font-weight:800;">{lifetime_revenue:,.0f} TSH</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        total_chicks = sum(v.get("chicks_qty", 0) for v in st.session_state.farm_database.values())
        total_morts = sum(v.get("mortality", 0) for v in st.session_state.farm_database.values())
        net_chicks = total_chicks - total_morts

        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("&#x1f4c8; " + t["calc_profit_btn"], use_container_width=True):
                st.session_state.sub_view = "profit_page"
                st.rerun()
        st.markdown("<hr style='border-color:#2a2a3a; margin:20px 0;'>", unsafe_allow_html=True)
        st.markdown(f"""<div style="text-align:center; margin-bottom:16px;">
            <span style="color:#38bdf8; font-size:22px; font-weight:800;">&#x1f4cb; {t['record_header']}</span>
        </div>""", unsafe_allow_html=True)

        col_hist1, col_hist2 = st.columns(2)
        with col_hist1:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0a1a2e,#0f2840); border:1px solid #1a3a5a; border-radius:20px; padding:24px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,0.4); min-height:160px; display:flex; flex-direction:column; justify-content:center;">
                <div style="font-size:40px; margin-bottom:6px;">&#x1f423;</div>
                <div style="color:#38bdf8; font-size:17px; font-weight:700;">{t['kumbu_dev_title']}</div>
                <p style="color:#789; font-size:12px; margin-top:4px;">{t['kumbu_dev_desc']}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("&#x1f423; "+t["open_kumbu_dev"], key="go_to_kumbu_dev", use_container_width=True):
                st.session_state.sub_view = "kumbukumbu_maendeleo"
                st.session_state.edit_dev_date = None
                st.rerun()

        with col_hist2:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0a2a0a,#103a10); border:1px solid #205a20; border-radius:20px; padding:24px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,0.4); min-height:160px; display:flex; flex-direction:column; justify-content:center;">
                <div style="font-size:40px; margin-bottom:6px;">&#x1f4b0;</div>
                <div style="color:#00E676; font-size:17px; font-weight:700;">{t['kumbu_sale_title']}</div>
                <p style="color:#789; font-size:12px; margin-top:4px;">{t['kumbu_sale_desc']}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("&#x1f4b0; "+t["open_kumbu_sale"], key="go_to_kumbu_sale", use_container_width=True):
                st.session_state.sub_view = "kumbukumbu_mauzo"
                st.session_state.edit_sale_key = None
                st.rerun()

        # --- Reminders Section ---
        reminders = db_get_reminders(st.session_state.current_user_id, include_done=False)
        today_str = date.today().strftime("%Y-%m-%d")
        overdue = [r for r in reminders if r["due_date"] < today_str]
        due_soon = [r for r in reminders if r["due_date"] == today_str]
        upcoming = [r for r in reminders if r["due_date"] > today_str][:5]

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1a1a2e,#16213e); border:1px solid #2a2a4a; border-radius:20px; padding:20px 24px; box-shadow:0 8px 32px rgba(0,0,0,0.4); margin-top:16px;">
            <span style="font-size:24px;">&#x23f0;</span>
            <span style="color:#FFD700; font-size:17px; font-weight:700; margin-left:8px;">{t['reminders_title']}</span>
        </div>
        """, unsafe_allow_html=True)

        has_any = bool(overdue) or bool(due_soon) or bool(upcoming)

        if overdue:
            for r in overdue[:3]:
                icon = {"chanjo": "&#x1f489;", "dawa": "&#x1f48a;", "chakula": "&#x1f33e;"}.get(r["reminder_type"], "&#x1f4cc;")
                st.markdown(f"""<div style="background:linear-gradient(135deg,#2a0a0a,#3a1010); border-left:5px solid #FF5252; border-radius:10px; padding:10px 14px; margin-bottom:6px;"><div style="display:flex; justify-content:space-between; align-items:center;"><span style="color:#FFF; font-size:13px; font-weight:600;">{icon} {r['title']}</span><span style="color:#FF5252; font-size:11px; font-weight:700;">&#x274c; {t['reminders_overdue_text']} ({r['due_date']})</span></div></div>""", unsafe_allow_html=True)

        if due_soon:
            for r in due_soon[:3]:
                icon = {"chanjo": "&#x1f489;", "dawa": "&#x1f48a;", "chakula": "&#x1f33e;"}.get(r["reminder_type"], "&#x1f4cc;")
                st.markdown(f"""<div style="background:linear-gradient(135deg,#2a2a0a,#3a3a10); border-left:5px solid #FFD700; border-radius:10px; padding:10px 14px; margin-bottom:6px;"><div style="display:flex; justify-content:space-between; align-items:center;"><span style="color:#FFF; font-size:13px; font-weight:600;">{icon} {r['title']}</span><span style="color:#FFD700; font-size:11px; font-weight:700;">&#x23f0; {t['reminder_today']}</span></div></div>""", unsafe_allow_html=True)

        for r in upcoming:
            icon = {"chanjo": "&#x1f489;", "dawa": "&#x1f48a;", "chakula": "&#x1f33e;"}.get(r["reminder_type"], "&#x1f4cc;")
            st.markdown(f"""<div style="background:#12121a; border-left:5px solid #38bdf8; border-radius:10px; padding:10px 14px; margin-bottom:6px;"><div style="display:flex; justify-content:space-between; align-items:center;"><span style="color:#FFF; font-size:13px; font-weight:600;">{icon} {r['title']}</span><span style="color:#38bdf8; font-size:11px; font-weight:700;">&#x1f4c5; {r['due_date']}</span></div></div>""", unsafe_allow_html=True)

        if not has_any:
            st.markdown(f"""<div style="padding:16px; text-align:center; border:2px dashed #2a2a4a; border-radius:12px;"><p style="color:#AAA; font-size:14px; margin:0 0 4px 0;">{t['no_reminders']}</p><p style="color:#666; font-size:12px; margin:0;">{t['no_reminders_hint']}</p></div>""", unsafe_allow_html=True)

        col_rem1, col_rem2 = st.columns(2)
        with col_rem1:
            if st.button(t["add_reminder"], key="add_reminder_btn", use_container_width=True):
                st.session_state.sub_view = "reminders_add"
                st.rerun()
        with col_rem2:
            if st.button(t["view_all_reminders"], key="view_reminders_btn", use_container_width=True):
                st.session_state.sub_view = "reminders_all"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        # --- Rounds History ---
        arrow = "&#x25bc;" if st.session_state.round_history_expanded else "&#x25b6;"
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1a1a2e,#16213e); border:1px solid #2a2a4a; border-radius:20px; padding:24px; box-shadow:0 8px 32px rgba(0,0,0,0.4); margin-top:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; cursor:pointer;">
                <div>
                    <span style="font-size:28px;">&#x1f4e6;</span>
                    <span style="color:#FFD700; font-size:17px; font-weight:700; margin-left:8px;">{t['round_history']}</span>
                </div>
                <span style="color:#888; font-size:13px;">{arrow}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"{'&#x25bc; Fungua / Open' if not st.session_state.round_history_expanded else '&#x25b2; Funga / Close'} {t['round_history']}", key="toggle_round_hist", use_container_width=True):
            st.session_state.round_history_expanded = not st.session_state.round_history_expanded
            st.rerun()

        if st.session_state.round_history_expanded:
            if st.session_state.rounds_list:
                for rnd in st.session_state.rounds_list:
                    rn = rnd["round_number"]
                    rn_date = rnd["archived_at"][:10] if rnd.get("archived_at") else ""
                    is_confirm = st.session_state.confirm_delete_round == rn
                    st.markdown(f"""
                    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:16px; padding:14px 18px; margin-bottom:10px; border:1px solid #2a2a4a; display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="color:#FFD700; font-weight:800; font-size:17px;">&#x1f4e6; {t['round_label'].format(rn)}</span>
                            <span style="color:#888; font-size:12px; margin-left:10px;">&#x1f4c5; {rn_date}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    c_view, c_del = st.columns([3, 1])
                    with c_view:
                        if st.button("&#x1f441; " + t["round_label"].format(rn), key=f"view_rnd_{rn}", use_container_width=True):
                            st.session_state.viewing_round = rn
                            st.session_state.sub_view = "viewing_round"
                            st.rerun()
                    with c_del:
                        if is_confirm:
                            if st.button("&#x26a0; Ndiyo / Yes", key=f"confirm_del_{rn}", use_container_width=True):
                                db_delete_round(st.session_state.current_user_id, rn)
                                st.session_state.confirm_delete_round = None
                                load_rounds()
                                st.success(t["round_deleted"])
                                time.sleep(0.5)
                                st.rerun()
                        else:
                            if st.button("&#x274c; " + t["delete_round"], key=f"del_rnd_{rn}", use_container_width=True):
                                st.session_state.confirm_delete_round = rn
                                st.rerun()
            else:
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#0a0a1a,#1a1a2e); border-radius:20px; padding:30px 20px; text-align:center; border:2px dashed #2a2a4a;">
                    <div style="font-size:40px; margin-bottom:8px;">&#x1f4ed;</div>
                    <p style="color:#AAA; font-size:15px; font-weight:600; margin:0 0 4px 0;">{t['no_rounds']}</p>
                    <p style="color:#666; font-size:12px; margin:0;">{t['no_rounds_hint']}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(t["logout"], use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.is_activated = False
            st.session_state.auth_screen = "login"
            st.session_state.current_user_id = None
            st.session_state.current_username = None
            st.session_state.farm_database = {}
            st.rerun()

    elif st.session_state.sub_view == "inputs":
        _, center_form, _ = st.columns([1, 2, 1])
        with center_form:
            if st.button(t["back_btn"]): st.session_state.sub_view = "dashboard"; st.rerun()
            
            chosen_date = st.date_input(t["label_date"], value=date.today())
            date_str = str(chosen_date)
            init_date_entry(date_str)
            current_entry = st.session_state.farm_database[date_str]

            t_chicks = sum(v["chicks_qty"] for v in st.session_state.farm_database.values())
            t_morts = sum(v["mortality"] for v in st.session_state.farm_database.values())
            t_remain = t_chicks - t_morts
            st.markdown(f"""
            <div style="background:#1a1a2e; border-radius:12px; padding:12px 16px; margin-bottom:15px; border-left:5px solid #38bdf8; display:flex; gap:20px; flex-wrap:wrap; font-size:14px;">
                <span style="color:white;">&#x1f425; {t['total_chicks']}: <b style="color:#38bdf8;">{t_chicks}</b></span>
                <span style="color:white;">&#x274c; {t['deaths']}: <b style="color:#FF5252;">{t_morts}</b></span>
                <span style="color:white;">&#x2705; {t['remaining']}: <b style="color:#00E676;">{t_remain}</b></span>
            </div>
            """, unsafe_allow_html=True)

            with st.form(key="inputs_data_capture"):
                st.markdown(f"<h4 style='color:#38bdf8; margin-top:0;'>{t['input_header']}</h4>", unsafe_allow_html=True)
                
                # Uwanja wa Idadi ya vifaranga walioingia bandani leo
                chicks_qty = st.number_input(t["label_chicks_qty"], min_value=0, value=int(current_entry.get("chicks_qty", 0)), step=1)
                
                chicks_cost = st.number_input(t["label_chicks"], value=current_entry["chicks_cost"])
                feeds = st.number_input(t["label_feed"], value=current_entry["feed_cost"])
                meds = st.number_input(t["label_med"], value=current_entry["med_cost"])
                other = st.number_input(t["label_other"], value=current_entry["other_cost"])
                mortality = st.number_input(t["label_mortality"], value=current_entry["mortality"], step=1)
                
                if st.form_submit_button(t["finish_inputs_btn"]):
                    st.session_state.farm_database[date_str].update({
                        "chicks_qty": int(chicks_qty),
                        "chicks_cost": chicks_cost, 
                        "feed_cost": feeds, 
                        "med_cost": meds, 
                        "other_cost": other, 
                        "mortality": int(mortality), 
                        "has_inputs": True
                    })
                    save_data()
                    st.success("&#x1f389; Data za gharama na idadi ya kuku zimehifadhiwa!")
                    time.sleep(1.0)
                    st.session_state.sub_view = "dashboard"
                    st.rerun()

    elif st.session_state.sub_view == "withdraw":
        _, center_form, _ = st.columns([1, 2, 1])
        with center_form:
            if st.button(t["back_btn"]): st.session_state.sub_view = "dashboard"; st.rerun()
            
            chosen_date = st.date_input(t["label_date"], value=date.today())
            date_str = str(chosen_date)
            init_date_entry(date_str)
            
            st.markdown(f"<h3 style='color:#00E676;'>{t['sales_header']}</h3>", unsafe_allow_html=True)
            
            with st.form(key="sales_data_capture", clear_on_submit=True):
                customer_name = st.text_input(t["label_customer"], placeholder=t["customer_placeholder"])
                qty = st.number_input(t["label_qty"], min_value=1, value=1, step=1)
                price = st.number_input(t["label_price"], value=6500.0)
                
                if st.form_submit_button(t["finish_sales_btn"]):
                    if customer_name.strip() == "":
                        st.error(t["empty_name"])
                    else:
                        revenue = float(qty * price)
                        st.session_state.farm_database[date_str]["sales_records"].append({
                            "customer": customer_name.strip(),
                            "qty": int(qty),
                            "price": price,
                            "revenue": revenue
                        })
                        st.session_state.farm_database[date_str]["has_sales"] = True
                        save_data()
                        st.success(f"&#x1f389; {t['save_success_sale']} {customer_name}!")
                        time.sleep(1.0)
                        st.session_state.sub_view = "dashboard"
                        st.rerun()

    elif st.session_state.sub_view == "kumbukumbu_maendeleo":
        st.markdown(f"""<div style="text-align:center; padding:5px 0 15px 0;">
            <span style="font-size:48px;">&#x1f423;</span>
            <h2 style="color:#38bdf8; margin:5px 0 2px 0; font-size:28px; font-weight:800;">{t['kumbu_dev_title']}</h2>
            <p style="color:#888; font-size:13px; margin:0;">{t['kumbu_dev_desc']}</p>
        </div>""", unsafe_allow_html=True)

        input_dates = {k: v for k, v in st.session_state.farm_database.items()
                       if v.get("has_inputs") or any(v.get(k, 0) > 0 for k in ("chicks_qty", "chicks_cost", "feed_cost", "med_cost", "other_cost"))}
        if input_dates:
            t_chicks_d = sum(v.get("chicks_qty", 0) for v in input_dates.values())
            t_morts_d = sum(v.get("mortality", 0) for v in input_dates.values())
            t_costs_d = sum(v.get("chicks_cost", 0) + v.get("feed_cost", 0) + v.get("med_cost", 0) + v.get("other_cost", 0) for v in input_dates.values())
            st.markdown(f"""
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:18px;">
                <div style="flex:1; min-width:100px; background:linear-gradient(135deg,#0a1a2e,#0f2840); border-radius:14px; padding:12px; text-align:center; border:1px solid #1a3a5a;">
                    <div style="font-size:24px;">&#x1f425;</div>
                    <div style="color:#38bdf8; font-size:20px; font-weight:800;">{t_chicks_d}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['total_chicks']}</div>
                </div>
                <div style="flex:1; min-width:100px; background:linear-gradient(135deg,#2a0a0a,#3a1010); border-radius:14px; padding:12px; text-align:center; border:1px solid #5a2020;">
                    <div style="font-size:24px;">&#x274c;</div>
                    <div style="color:#FF5252; font-size:20px; font-weight:800;">{t_morts_d}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['deaths']}</div>
                </div>
                <div style="flex:1; min-width:100px; background:linear-gradient(135deg,#0a2a0a,#103a10); border-radius:14px; padding:12px; text-align:center; border:1px solid #205a20;">
                    <div style="font-size:24px;">&#x2705;</div>
                    <div style="color:#00E676; font-size:20px; font-weight:800;">{t_chicks_d - t_morts_d}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['remaining']}</div>
                </div>
                <div style="flex:1; min-width:120px; background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:14px; padding:12px; text-align:center; border:1px solid #0f3460;">
                    <div style="font-size:24px;">&#x1f4b0;</div>
                    <div style="color:#FFD700; font-size:16px; font-weight:800;">{t_costs_d:,.0f} TSH</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['total_expenses']}</div>
                </div>
                <div style="flex:1; min-width:80px; background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:14px; padding:12px; text-align:center; border:1px solid #0f3460;">
                    <div style="font-size:24px;">&#x1f4cb;</div>
                    <div style="color:#38bdf8; font-size:20px; font-weight:800;">{len(input_dates)}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">Siku</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        _, center_col, _ = st.columns([0.3, 2.4, 0.3])
        with center_col:
            if input_dates:
                for date_key in sorted(input_dates.keys(), reverse=True):
                    e = input_dates[date_key]
                    day_cost = e.get("chicks_cost", 0) + e.get("feed_cost", 0) + e.get("med_cost", 0) + e.get("other_cost", 0)
                    if st.session_state.edit_dev_date == date_key:
                        with st.form(key=f"edit_dev_form_{date_key}"):
                            st.markdown(f"""<div style="background:linear-gradient(135deg,#0a1a2e,#0f2840); border-radius:14px; padding:18px; border:2px solid #38bdf8; margin-bottom:12px;">
                                <h4 style="color:#38bdf8; margin:0 0 14px 0;">&#x270f;&#xfe0f; {t['edit_record_title'].format(date_key)}</h4>""", unsafe_allow_html=True)
                            ec_qty = st.number_input(t["chicks_input_label"], min_value=0, value=int(e.get("chicks_qty", 0)), step=1, key=f"ed_qty_{date_key}")
                            ec_cost = st.number_input(t["chicks_cost_label"], value=e.get("chicks_cost", 0.0), key=f"ed_cost_{date_key}")
                            ef_cost = st.number_input(t["feed_cost_label"], value=e.get("feed_cost", 0.0), key=f"ed_feed_{date_key}")
                            em_cost = st.number_input(t["med_cost_label"], value=e.get("med_cost", 0.0), key=f"ed_med_{date_key}")
                            eo_cost = st.number_input(t["other_cost_label"], value=e.get("other_cost", 0.0), key=f"ed_other_{date_key}")
                            emort = st.number_input(t["mortality_label"], min_value=0, value=int(e.get("mortality", 0)), step=1, key=f"ed_mort_{date_key}")
                            c1, c2 = st.columns(2)
                            with c1:
                                if st.form_submit_button(t["save_btn"], use_container_width=True):
                                    st.session_state.farm_database[date_key].update({"chicks_qty": int(ec_qty), "chicks_cost": ec_cost, "feed_cost": ef_cost, "med_cost": em_cost, "other_cost": eo_cost, "mortality": int(emort)})
                                    save_data()
                                    st.session_state.edit_dev_date = None
                                    st.success(t["save_success"])
                                    time.sleep(0.5)
                                    st.rerun()
                            with c2:
                                if st.form_submit_button(t["cancel_btn"], use_container_width=True):
                                    st.session_state.edit_dev_date = None
                                    st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        surviving = e.get("chicks_qty", 0) - e.get("mortality", 0)
                        st.markdown(f"""
                        <div style="background:#12121a; border-radius:16px; padding:0; margin-bottom:12px; border:1px solid #2a2a3a; overflow:hidden; box-shadow:0 6px 20px rgba(0,0,0,0.3);">
                            <div style="background:linear-gradient(135deg,#0f2027,#203a43); padding:12px 16px; display:flex; justify-content:space-between; align-items:center;">
                                <span style="color:#FFF; font-size:15px; font-weight:700;">&#x1f4c5; {date_key}</span>
                                <span style="background:rgba(56,189,248,0.15); color:#38bdf8; padding:3px 12px; border-radius:20px; font-size:12px; font-weight:600;">{t['day_qty_badge'].format(e.get('chicks_qty', 0))}</span>
                            </div>
                            <div style="padding:14px 16px;">
                                <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px 16px; font-size:13px;">
                                    <span style="color:#AAA;">&#x1f425; {t['chicks_cost_label']}</span>
                                    <span style="text-align:right; color:#FFF; font-weight:600;">{e.get('chicks_cost', 0):,.0f} TSH</span>
                                    <span style="color:#AAA;">&#x1f33e; {t['feed_cost_label']}</span>
                                    <span style="text-align:right; color:#FFF; font-weight:600;">{e.get('feed_cost', 0):,.0f} TSH</span>
                                    <span style="color:#AAA;">💊 {t['med_cost_label']}</span>
                                    <span style="text-align:right; color:#FFF; font-weight:600;">{e.get('med_cost', 0):,.0f} TSH</span>
                                    <span style="color:#AAA;">&#x1f527; {t['other_cost_label']}</span>
                                    <span style="text-align:right; color:#FFF; font-weight:600;">{e.get('other_cost', 0):,.0f} TSH</span>
                                </div>
                                <div style="display:flex; gap:10px; margin-top:10px; padding-top:10px; border-top:1px solid #2a2a3a;">
                                    <span style="flex:1; text-align:center; background:#1a1a2e; border-radius:8px; padding:6px; font-size:12px;">
                                        <span style="color:#FF5252;">&#x274c; {e.get('mortality', 0)}</span>
                                        <span style="color:#789; display:block; font-size:10px;">{t['deaths']}</span>
                                    </span>
                                    <span style="flex:1; text-align:center; background:#1a1a2e; border-radius:8px; padding:6px; font-size:12px;">
                                        <span style="color:#00E676;">&#x2705; {surviving}</span>
                                        <span style="color:#789; display:block; font-size:10px;">{t['remaining']}</span>
                                    </span>
                                    <span style="flex:1; text-align:center; background:#1a1a2e; border-radius:8px; padding:6px; font-size:12px;">
                                        <span style="color:#FFD700;">&#x1f4b0; {day_cost:,.0f} TSH</span>
                                        <span style="color:#789; display:block; font-size:10px;">Jumla</span>
                                    </span>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        _, btn_col, _ = st.columns([2.5, 1, 2.5])
                        with btn_col:
                            if st.button(t["edit_btn"], key=f"edit_dev_btn_{date_key}", use_container_width=True):
                                st.session_state.edit_dev_date = date_key
                                st.rerun()
            else:
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#0a0a1a,#1a1a2e); border-radius:20px; padding:40px 20px; text-align:center; border:2px dashed #2a2a4a;">
                    <div style="font-size:56px; margin-bottom:10px;">&#x1f4ed;</div>
                    <p style="color:#38bdf8; font-size:18px; font-weight:700; margin:0 0 6px 0;">{t['no_dev_records']}</p>
                    <p style="color:#666; font-size:13px; margin:0;">{t['no_dev_hint']}</p>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(t["back_dashboard"], key="back_from_kumbu_dev", use_container_width=True):
            st.session_state.sub_view = "dashboard"
            st.rerun()

    elif st.session_state.sub_view == "kumbukumbu_mauzo":
        st.markdown(f"""<div style="text-align:center; padding:5px 0 15px 0;">
            <span style="font-size:48px;">&#x1f4b0;</span>
            <h2 style="color:#00E676; margin:5px 0 2px 0; font-size:28px; font-weight:800;">{t['kumbu_sale_title']}</h2>
            <p style="color:#888; font-size:13px; margin:0;">{t['kumbu_sale_desc']}</p>
        </div>""", unsafe_allow_html=True)

        sale_dates = {k: v for k, v in st.session_state.farm_database.items() if v.get("has_sales") or len(v.get("sales_records", [])) > 0}
        if sale_dates:
            t_rev_s = sum(sum(r["revenue"] for r in v["sales_records"]) for v in sale_dates.values())
            t_qty_s = sum(sum(r["qty"] for r in v["sales_records"]) for v in sale_dates.values())
            t_cust_s = sum(len(v["sales_records"]) for v in sale_dates.values())
            st.markdown(f"""
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:18px;">
                <div style="flex:1; min-width:120px; background:linear-gradient(135deg,#0a2a0a,#103a10); border-radius:14px; padding:12px; text-align:center; border:1px solid #205a20;">
                    <div style="font-size:24px;">&#x1f4b0;</div>
                    <div style="color:#FFD700; font-size:18px; font-weight:800;">{t_rev_s:,.0f} TSH</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['total_revenue']}</div>
                </div>
                <div style="flex:1; min-width:80px; background:linear-gradient(135deg,#0a1a2e,#0f2840); border-radius:14px; padding:12px; text-align:center; border:1px solid #1a3a5a;">
                    <div style="font-size:24px;">&#x1f414;</div>
                    <div style="color:#38bdf8; font-size:20px; font-weight:800;">{t_qty_s}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['label_qty']}</div>
                </div>
                <div style="flex:1; min-width:80px; background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:14px; padding:12px; text-align:center; border:1px solid #0f3460;">
                    <div style="font-size:24px;">&#x1f465;</div>
                    <div style="color:#00E676; font-size:20px; font-weight:800;">{t_cust_s}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">Wateja</div>
                </div>
                <div style="flex:1; min-width:80px; background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:14px; padding:12px; text-align:center; border:1px solid #0f3460;">
                    <div style="font-size:24px;">&#x1f4cb;</div>
                    <div style="color:#38bdf8; font-size:20px; font-weight:800;">{len(sale_dates)}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">Siku</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        _, center_col, _ = st.columns([0.3, 2.4, 0.3])
        with center_col:
            if sale_dates:
                for date_key in sorted(sale_dates.keys(), reverse=True):
                    e = sale_dates[date_key]
                    day_qty = sum(r["qty"] for r in e["sales_records"])
                    day_rev = sum(r["revenue"] for r in e["sales_records"])
                    st.markdown(f"""
                    <div style="background:#12121a; border-radius:16px; margin-bottom:14px; border:1px solid #2a3a2a; overflow:hidden; box-shadow:0 6px 20px rgba(0,0,0,0.3);">
                        <div style="background:linear-gradient(135deg,#0a2a0a,#1a3a1a); padding:12px 16px; display:flex; justify-content:space-between; align-items:center;">
                            <span style="color:#FFF; font-size:15px; font-weight:700;">&#x1f4c5; {date_key}</span>
                            <div style="text-align:right;">
                                <span style="background:rgba(0,230,118,0.15); color:#00E676; padding:3px 12px; border-radius:20px; font-size:12px; font-weight:600;">{t['day_qty_badge'].format(day_qty)}</span>
                                <div style="color:#FFD700; font-size:13px; font-weight:700; margin-top:3px;">{t['day_sales_total'].format(day_rev)}</div>
                            </div>
                        </div>
                        <div style="padding:10px 16px 6px 16px;">
                    """, unsafe_allow_html=True)
                    for idx, r in enumerate(e["sales_records"]):
                        sale_key = f"{date_key}|{idx}"
                        if st.session_state.edit_sale_key == sale_key:
                            with st.form(key=f"edit_sale_form_{date_key}_{idx}"):
                                st.markdown(f"""<div style="background:linear-gradient(135deg,#0a2a0a,#1a3a1a); border-radius:12px; padding:16px; border:2px solid #00E676; margin-bottom:10px;">
                                    <h4 style="color:#00E676; margin:0 0 12px 0;">&#x270f;&#xfe0f; {t['edit_sale_title'].format(date_key)}</h4>""", unsafe_allow_html=True)
                                sc_name = st.text_input(t["label_customer"], value=r["customer"], key=f"es_name_{date_key}_{idx}")
                                sc_qty = st.number_input(t["label_qty"], min_value=1, value=int(r["qty"]), step=1, key=f"es_qty_{date_key}_{idx}")
                                sc_price = st.number_input(t["label_price"], value=r["price"], key=f"es_price_{date_key}_{idx}")
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.form_submit_button(t["save_btn"], use_container_width=True):
                                        if sc_name.strip():
                                            new_revenue = float(sc_qty * sc_price)
                                            st.session_state.farm_database[date_key]["sales_records"][idx] = {"customer": sc_name.strip(), "qty": int(sc_qty), "price": sc_price, "revenue": new_revenue}
                                            save_data()
                                            st.session_state.edit_sale_key = None
                                            st.success(t["save_success"])
                                            time.sleep(0.5)
                                            st.rerun()
                                        else:
                                            st.error(t["empty_name"])
                                with c2:
                                    if st.form_submit_button(t["cancel_btn"], use_container_width=True):
                                        st.session_state.edit_sale_key = None
                                        st.rerun()
                                st.markdown("</div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div style="display:flex; align-items:center; background:#1a1a2a; border-radius:10px; padding:10px 14px; margin-bottom:6px; border-left:4px solid #00E676;">
                                <div style="flex:1;">
                                    <span style="color:#FFF; font-size:14px; font-weight:600;">&#x1f464; {r['customer']}</span>
                                </div>
                                <div style="text-align:right;">
                                    <span style="color:#AAA; font-size:12px;">{r['qty']} {t['chickens']} &#xd7; {r['price']:,.0f} TSH</span>
                                    <span style="color:#00E676; font-size:14px; font-weight:700; margin-left:10px;">= {r['revenue']:,.0f} TSH</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            _, btn_col, _ = st.columns([2.5, 1, 2.5])
                            with btn_col:
                                if st.button(t["edit_btn"], key=f"edit_sale_btn_{date_key}_{idx}", use_container_width=True):
                                    st.session_state.edit_sale_key = sale_key
                                    st.rerun()
                    st.markdown("</div></div>", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#0a0a1a,#1a1a2e); border-radius:20px; padding:40px 20px; text-align:center; border:2px dashed #2a2a4a;">
                    <div style="font-size:56px; margin-bottom:10px;">&#x1f4ed;</div>
                    <p style="color:#00E676; font-size:18px; font-weight:700; margin:0 0 6px 0;">{t['no_sale_records']}</p>
                    <p style="color:#666; font-size:13px; margin:0;">{t['no_sale_hint']}</p>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(t["back_dashboard"], key="back_from_kumbu_sale", use_container_width=True):
            st.session_state.sub_view = "dashboard"
            st.rerun()

    elif st.session_state.sub_view == "viewing_round":
        rn = st.session_state.viewing_round
        if rn is None:
            st.session_state.sub_view = "dashboard"
            st.rerun()
        rnd_data = db_get_round(st.session_state.current_user_id, rn)
        if not rnd_data:
            st.error("Round not found!")
            if st.button(t["viewing_back"]):
                st.session_state.sub_view = "dashboard"
                st.rerun()
        else:
            import json
            farm_snapshot = json.loads(rnd_data["summary_json"])
            rn_date = rnd_data["archived_at"][:10] if rnd_data.get("archived_at") else ""

            total_chicks_r = sum(v.get("chicks_qty", 0) for v in farm_snapshot.values())
            total_morts_r = sum(v.get("mortality", 0) for v in farm_snapshot.values())
            total_costs_r = sum(v.get("chicks_cost", 0) + v.get("feed_cost", 0) + v.get("med_cost", 0) + v.get("other_cost", 0) for v in farm_snapshot.values())
            total_rev_r = 0
            for v in farm_snapshot.values():
                for rec in v.get("sales_records", []):
                    total_rev_r += rec["revenue"]
            net_r = total_rev_r - total_costs_r

            st.markdown(f"""<div style="text-align:center; padding:5px 0 15px 0;">
                <span style="font-size:48px;">&#x1f4e6;</span>
                <h2 style="color:#FFD700; margin:5px 0 2px 0; font-size:28px; font-weight:800;">{t['viewing_round_title'].format(rn)}</h2>
                <p style="color:#888; font-size:13px; margin:0;">&#x1f4c5; {t['archived_at']}: {rn_date}</p>
            </div>""", unsafe_allow_html=True)

            st.markdown(f"""
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:18px;">
                <div style="flex:1; min-width:100px; background:linear-gradient(135deg,#0a1a2e,#0f2840); border-radius:14px; padding:12px; text-align:center; border:1px solid #1a3a5a;">
                    <div style="font-size:24px;">&#x1f425;</div>
                    <div style="color:#38bdf8; font-size:20px; font-weight:800;">{total_chicks_r}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['total_chicks']}</div>
                </div>
                <div style="flex:1; min-width:100px; background:linear-gradient(135deg,#2a0a0a,#3a1010); border-radius:14px; padding:12px; text-align:center; border:1px solid #5a2020;">
                    <div style="font-size:24px;">&#x274c;</div>
                    <div style="color:#FF5252; font-size:20px; font-weight:800;">{total_morts_r}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['deaths']}</div>
                </div>
                <div style="flex:1; min-width:100px; background:linear-gradient(135deg,#0a2a0a,#103a10); border-radius:14px; padding:12px; text-align:center; border:1px solid #205a20;">
                    <div style="font-size:24px;">&#x2705;</div>
                    <div style="color:#00E676; font-size:20px; font-weight:800;">{total_chicks_r - total_morts_r}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['remaining']}</div>
                </div>
                <div style="flex:1; min-width:120px; background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:14px; padding:12px; text-align:center; border:1px solid #0f3460;">
                    <div style="font-size:24px;">&#x1f4b0;</div>
                    <div style="color:#FF5252; font-size:16px; font-weight:800;">{total_costs_r:,.0f} TSH</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['total_expenses']}</div>
                </div>
                <div style="flex:1; min-width:120px; background:linear-gradient(135deg,#0a2a0a,#103a10); border-radius:14px; padding:12px; text-align:center; border:1px solid #205a20;">
                    <div style="font-size:24px;">&#x1f4e6;</div>
                    <div style="color:#00E676; font-size:16px; font-weight:800;">{total_rev_r:,.0f} TSH</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{t['total_revenue']}</div>
                </div>
                <div style="flex:1; min-width:100px; background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:14px; padding:12px; text-align:center; border:1px solid #0f3460;">
                    <div style="font-size:24px;">{'&#x1f389;' if net_r >= 0 else '&#x26a0;&#xfe0f;'}</div>
                    <div style="color={'#00E676' if net_r >= 0 else '#FF5252'}; font-size:16px; font-weight:800;">{abs(net_r):,.0f} TSH</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">{'Faida' if net_r >= 0 else 'Hasara'}</div>
                </div>
                <div style="flex:1; min-width:80px; background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:14px; padding:12px; text-align:center; border:1px solid #0f3460;">
                    <div style="font-size:24px;">&#x1f4cb;</div>
                    <div style="color:#38bdf8; font-size:20px; font-weight:800;">{len(farm_snapshot)}</div>
                    <div style="color:#789; font-size:10px; font-weight:600;">Siku</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""<div style="margin:20px 0 10px 0;">
                <span style="color:#38bdf8; font-size:18px; font-weight:700;">&#x1f4c5; Siku za Awamu hii / Days in this round</span>
            </div>""", unsafe_allow_html=True)
            for date_key in sorted(farm_snapshot.keys(), reverse=True):
                e = farm_snapshot[date_key]
                day_cost = e.get("chicks_cost", 0) + e.get("feed_cost", 0) + e.get("med_cost", 0) + e.get("other_cost", 0)
                day_sales = e.get("sales_records", [])
                day_rev = sum(r["revenue"] for r in day_sales)
                surviving = e.get("chicks_qty", 0) - e.get("mortality", 0)
                st.markdown(f"""
                <div style="background:#12121a; border-radius:12px; padding:10px 14px; margin-bottom:8px; border:1px solid #2a2a3a;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="color:#FFF; font-size:14px; font-weight:700;">&#x1f4c5; {date_key}</span>
                        <span style="background:rgba(56,189,248,0.15); color:#38bdf8; padding:2px 10px; border-radius:12px; font-size:11px; font-weight:600;">{e.get('chicks_qty', 0)} Kuku</span>
                    </div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap; font-size:12px; margin-top:4px;">
                        <span style="color:#AAA;">&#x1f4b0; Gharama: <b style="color:#FF5252;">{day_cost:,.0f} TSH</b></span>
                        <span style="color:#AAA;">&#x1f4e6; Mapato: <b style="color:#00E676;">{day_rev:,.0f} TSH</b></span>
                        <span style="color:#AAA;">&#x274c; Vifo: <b style="color:#FF5252;">{e.get('mortality', 0)}</b></span>
                        <span style="color:#AAA;">&#x2705; Waliopo: <b style="color:#00E676;">{surviving}</b></span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if day_sales:
                    for rec in day_sales:
                        st.markdown(f"""
                        <div style="margin-left:16px; margin-top:2px; margin-bottom:4px; padding:4px 10px; background:#1a1a2a; border-radius:8px; border-left:3px solid #00E676; font-size:12px;">
                            <span style="color:#FFF;">&#x1f464; {rec['customer']}</span>
                            <span style="color:#AAA; margin-left:10px;">&#x1f414; {rec['qty']} &#xd7; {rec['price']:,.0f} TSH</span>
                            <span style="color:#00E676; margin-left:8px; font-weight:600;">= {rec['revenue']:,.0f} TSH</span>
                        </div>
                        """, unsafe_allow_html=True)

            if st.button("&#x2190; " + t["viewing_back"], use_container_width=True):
                st.session_state.viewing_round = None
                st.session_state.sub_view = "dashboard"
                st.rerun()

    elif st.session_state.sub_view == "profit_page":
        uid = st.session_state.current_user_id
        frows = db_get_farm_dates(uid)
        srows = db_get_sales_records(uid)
        
        total_chicks = sum(r["chicks_qty"] for r in frows)
        total_morts = sum(r["mortality"] for r in frows)
        total_feed = sum(r["feed_cost"] for r in frows)
        total_med = sum(r["med_cost"] for r in frows)
        total_other = sum(r["other_cost"] for r in frows)
        total_chicks_cost = sum(r["chicks_cost"] for r in frows)
        total_costs = total_chicks_cost + total_feed + total_med + total_other
        
        sold_qty = sum(s["qty"] for s in srows)
        total_rev = sum(s["revenue"] for s in srows)
        unique_customers = list(set(s["customer"] for s in srows))
        remaining = total_chicks - total_morts - sold_qty
        if remaining < 0:
            remaining = 0
        
        net = total_rev - total_costs
        
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#0a0a1a,#1a1a2e); border-radius:24px; padding:30px; border:2px solid #FFD700; box-shadow:0 12px 48px rgba(255,215,0,0.1); margin:10px 0;">
            <div style="text-align:center; margin-bottom:20px;">
                <span style="font-size:48px;">{'&#x1f389;' if net >= 0 else '&#x26a0;&#xfe0f;'}</span>
                <h1 style="color:{'#00E676' if net >= 0 else '#FF5252'}; font-size:42px; font-weight:900; margin:8px 0; letter-spacing:1px;">
                    {t['profit_msg'] if net >= 0 else t['loss_msg']} {abs(net):,.0f} TSH
                </h1>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px 20px; background:#12121a; border-radius:16px; padding:20px; border:1px solid #2a2a3a;">
                <div style="color:#AAA; font-size:14px;">&#x1f425; Jumla Vifaranga</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#38bdf8;">{total_chicks}</div>
                <div style="color:#AAA; font-size:14px;">&#x274c; Vifo</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#FF5252;">{total_morts}</div>
                <div style="color:#AAA; font-size:14px;">&#x1f4b0; Waliouzwa</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#FFD700;">{sold_qty}</div>
                <div style="color:#AAA; font-size:14px;">&#x2705; Waliobaki</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#00E676;">{remaining}</div>
                <div style="border-top:1px solid #2a2a3a; grid-column:1/-1; margin:4px 0;"></div>
                <div style="color:#AAA; font-size:14px;">&#x1f33e; Gharama za Chakula</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#FFF;">{total_feed:,.0f} TSH</div>
                <div style="color:#AAA; font-size:14px;">💊 Gharama za Dawa</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#FFF;">{total_med:,.0f} TSH</div>
                <div style="color:#AAA; font-size:14px;">&#x1f527; Gharama Nyingine</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#FFF;">{total_other:,.0f} TSH</div>
                <div style="color:#AAA; font-size:14px;">&#x1f425; Gharama za Vifaranga</div>
                <div style="text-align:right; font-size:16px; font-weight:700; color:#FFF;">{total_chicks_cost:,.0f} TSH</div>
                <div style="color:#AAA; font-size:14px; font-weight:700;">&#x1f4b1; Jumla Matumizi</div>
                <div style="text-align:right; font-size:18px; font-weight:800; color:#FF5252;">{total_costs:,.0f} TSH</div>
                <div style="border-top:1px solid #2a2a3a; grid-column:1/-1; margin:4px 0;"></div>
        """, unsafe_allow_html=True)
        
        if srows:
            st.markdown(f"""
            <div style="grid-column:1/-1;">
                <div style="color:#00E676; font-size:15px; font-weight:700; margin-bottom:8px;">&#x1f465; Wateja ({len(unique_customers)})</div>
            """, unsafe_allow_html=True)
            cust_data = {}
            for s in srows:
                name = s["customer"]
                if name not in cust_data:
                    cust_data[name] = {"qty": 0, "total": 0}
                cust_data[name]["qty"] += s["qty"]
                cust_data[name]["total"] += s["revenue"]
            for cname, cinfo in cust_data.items():
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; background:#1a1a2a; border-radius:8px; padding:8px 12px; margin-bottom:4px; border-left:3px solid #00E676; grid-column:1/-1;">
                    <span style="color:#FFF; font-size:13px;">&#x1f464; {cname}</span>
                    <span style="color:#AAA; font-size:13px;">&#x1f414; {cinfo['qty']}</span>
                    <span style="color:#00E676; font-size:13px; font-weight:600;">{cinfo['total']:,.0f} TSH</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown(f"""
                <div style="display:flex; justify-content:space-between; background:#0a2a0a; border-radius:8px; padding:8px 12px; margin-top:6px; font-weight:700; grid-column:1/-1;">
                    <span style="color:#FFF;">&#x1f4e6; Jumla Mauzo</span>
                    <span style="color:#FFD700; font-size:15px;">{total_rev:,.0f} TSH</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="grid-column:1/-1; color:#888; font-size:13px; text-align:center;">Hakuna mauzo bado / No sales yet</div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div></div>", unsafe_allow_html=True)
        
        if st.button("&#x2190; Rudi Dashibodi / Back to Dashboard", use_container_width=True):
            st.session_state.sub_view = "dashboard"
            st.rerun()

    elif st.session_state.sub_view == "reminders_all":
        st.markdown(f"""<div style="text-align:center;padding:10px 0"><span style="font-size:32px;">&#x23f0;</span><h2 style="color:#FFD700;margin:4px 0;font-size:24px;font-weight:800;">{t['reminder_header']}</h2><p style="color:#888;font-size:13px;margin:0;">{t['reminder_subtitle']}</p></div>""", unsafe_allow_html=True)

        all_reminders = db_get_reminders(st.session_state.current_user_id, include_done=True)
        if not all_reminders:
            st.markdown(f"""<div style="background:linear-gradient(135deg,#0a0a1a,#1a1a2e);border-radius:20px;padding:40px 20px;text-align:center;border:2px dashed #2a2a4a;"><div style="font-size:56px;margin-bottom:10px;">&#x23f0;</div><p style="color:#FFD700;font-size:18px;font-weight:700;margin:0 0 6px 0;">{t['no_reminders']}</p><p style="color:#666;font-size:13px;margin:0;">{t['no_reminders_hint']}</p></div>""", unsafe_allow_html=True)
        else:
            today_str = date.today().strftime("%Y-%m-%d")
            for r in sorted(all_reminders, key=lambda x: x["due_date"]):
                rid = r["id"]
                is_done = r.get("is_done", 0)
                overdue = not is_done and r["due_date"] < today_str
                due_today = not is_done and r["due_date"] == today_str
                icon = {"chanjo": "&#x1f489;", "dawa": "&#x1f48a;", "chakula": "&#x1f33e;"}.get(r["reminder_type"], "&#x1f4cc;")
                type_label = {"chanjo": t["reminder_type_chanjo"], "dawa": t["reminder_type_dawa"], "chakula": t["reminder_type_chakula"]}.get(r["reminder_type"], t["reminder_type_general"])

                if is_done:
                    border = "border-left:6px solid #00E676"
                    bg = "background:linear-gradient(135deg,#0a1a0a,#0a2a0a)"
                    badge = f"<span style='background:#00E676;color:#000;padding:2px 12px;border-radius:12px;font-size:11px;font-weight:700;'>{t['reminder_done']}</span>"
                elif overdue:
                    border = "border-left:6px solid #FF5252"
                    bg = "background:linear-gradient(135deg,#1a0a0a,#2a0a0a)"
                    badge = f"<span style='background:#FF5252;color:#FFF;padding:2px 12px;border-radius:12px;font-size:11px;font-weight:700;'>&#x274c; {t['reminders_overdue_text']}</span>"
                elif due_today:
                    border = "border-left:6px solid #FFD700"
                    bg = "background:linear-gradient(135deg,#1a1a0a,#2a2a0a)"
                    badge = f"<span style='background:#FFD700;color:#000;padding:2px 12px;border-radius:12px;font-size:11px;font-weight:700;'>&#x23f0; {t['reminder_today']}</span>"
                else:
                    border = "border-left:6px solid #38bdf8"
                    bg = "background:linear-gradient(135deg,#0a0a1a,#0f1a2a)"
                    badge = f"<span style='background:#38bdf8;color:#000;padding:2px 12px;border-radius:12px;font-size:11px;font-weight:700;'>&#x1f4c5; {r['due_date']}</span>"

                freq = f"<span style='color:#888;font-size:10px;margin-left:6px;'>| Kila {r['frequency_days']}d</span>" if r['frequency_days'] > 0 else ""
                desc = f"<br><span style='color:#AAA;font-size:12px;'>{r['description']}</span>" if r.get('description') else ""

                st.markdown(f"""<div style="{bg};{border};border-radius:14px;padding:14px 18px;margin-bottom:8px;box-shadow:0 4px 12px rgba(0,0,0,0.3);"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;"><div><span style="color:#FFF;font-size:15px;font-weight:600;">{icon} {r['title']}</span><span style="color:#888;font-size:11px;margin-left:8px;">{type_label}</span>{freq}{desc}</div><div>{badge}</div></div></div>""", unsafe_allow_html=True)

                c1, c2, c3 = st.columns([1, 1, 1])
                if not is_done:
                    with c1:
                        if st.button(t["mark_done"], key=f"rem_done_{rid}", use_container_width=True):
                            db_update_reminder(rid, {"is_done": 1})
                            st.success(t["reminder_updated"])
                            time.sleep(0.3)
                            st.rerun()
                with c2:
                    if st.button(t["reminder_edit"], key=f"rem_edit_{rid}", use_container_width=True):
                        st.session_state.edit_reminder_id = rid
                        st.session_state.sub_view = "reminders_edit"
                        st.rerun()
                with c3:
                    if st.button(t["delete_reminder"], key=f"rem_del_{rid}", use_container_width=True):
                        db_delete_reminder(rid)
                        st.success(t["reminder_deleted"])
                        time.sleep(0.3)
                        st.rerun()

        if st.button(t["add_reminder"], key="add_from_all", use_container_width=True):
            st.session_state.sub_view = "reminders_add"
            st.rerun()
        if st.button("&#x2190; " + t["back_dashboard"], key="back_from_all", use_container_width=True):
            st.session_state.sub_view = "dashboard"
            st.rerun()

    elif st.session_state.sub_view == "reminders_add" or st.session_state.sub_view == "reminders_edit":
        is_edit = st.session_state.sub_view == "reminders_edit"
        edit_id = st.session_state.edit_reminder_id if is_edit else None
        edit_data = None
        if is_edit and edit_id:
            all_r = db_get_reminders(st.session_state.current_user_id, include_done=True)
            for rr in all_r:
                if rr["id"] == edit_id:
                    edit_data = rr
                    break

        _, center_f, _ = st.columns([1, 1.8, 1])
        with center_f:
            st.markdown("""<style>div[data-testid="column"]:has(> div div.reminder-wrap) > div{background:linear-gradient(145deg,#1a1a2e,#16213e)!important;border:1px solid #2a2a4a!important;border-radius:20px!important;padding:32px!important;box-shadow:0 8px 32px rgba(0,0,0,0.4)!important;}</style><div class="reminder-wrap" style="display:none;"></div>""", unsafe_allow_html=True)
            icon = '&#x270f;&#xfe0f;' if is_edit else '&#x2795;'
            title = t['reminder_edit'] if is_edit else t['add_reminder']
            st.markdown(f"<h3 style='text-align:center;color:#FFD700;font-size:24px;font-weight:800;margin-top:0;'>{icon} {title}</h3>", unsafe_allow_html=True)
            st.markdown("<hr style='border-color:#2a2a4a;margin:16px 0;'>", unsafe_allow_html=True)
            rem_type_labels = {
                "chanjo": t["reminder_type_chanjo"],
                "dawa": t["reminder_type_dawa"],
                "chakula": t["reminder_type_chakula"],
                "general": t["reminder_type_general"],
            }
            rt_order = ["chanjo", "dawa", "chakula", "general"]
            default_rt = edit_data.get("reminder_type", "chanjo") if edit_data else "chanjo"
            rt_index = rt_order.index(default_rt) if default_rt in rt_order else 0
            rem_type_val = st.radio(
                t["reminder_type"],
                options=rt_order, index=rt_index,
                format_func=lambda x: rem_type_labels[x],
                horizontal=True,
            )

            rem_title = st.text_input(t["reminder_title"], value=edit_data["title"] if edit_data else "", placeholder="E.g. Gumboro vaccine, Buy feed...")
            rem_desc = st.text_input(t["reminder_desc"], value=edit_data.get("description", "") if edit_data else "", placeholder=t["reminder_desc_placeholder"])
            default_date = edit_data["due_date"] if edit_data else str(date.today())
            rem_date = st.date_input(t["reminder_date"], value=datetime.strptime(default_date, "%Y-%m-%d").date())

            freq_labels = {0: t["reminder_once"], 1: t["reminder_daily"], 7: t["reminder_weekly"], 14: t["reminder_biweekly"], 30: t["reminder_monthly"]}
            freq_order = [0, 1, 7, 14, 30]
            default_fd = edit_data.get("frequency_days", 0) if edit_data else 0
            fd_index = freq_order.index(default_fd) if default_fd in freq_order else 0
            rem_freq_val = st.radio(
                t["reminder_frequency"],
                options=freq_order, index=fd_index,
                format_func=lambda x: freq_labels[x],
                horizontal=True,
            )

            if st.button(t["save_reminder_btn"], key="save_rem_btn", use_container_width=True):
                if rem_title.strip():
                    data = {
                        "title": rem_title.strip(),
                        "description": rem_desc.strip(),
                        "reminder_type": rem_type_val,
                        "due_date": str(rem_date),
                        "frequency_days": rem_freq_val,
                        "round_number": st.session_state.current_round,
                    }
                    if is_edit and edit_id:
                        db_update_reminder(edit_id, data)
                        msg = t["reminder_updated"]
                    else:
                        db_insert_reminder(st.session_state.current_user_id, data)
                        msg = t["reminder_saved"]
                    st.success(msg)
                    time.sleep(0.5)
                    st.session_state.edit_reminder_id = None
                    st.session_state.sub_view = "reminders_all"
                    st.rerun()
                else:
                    st.error("&#x274c; Tafadhali weka jina la kikumbusho!")

            if st.button("&#x2190; " + t["back_to_reminders"], key="back_rem_form", use_container_width=True):
                st.session_state.edit_reminder_id = None
                st.session_state.sub_view = "reminders_all"
                st.rerun()


