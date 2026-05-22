-- Create tables for Mfugaji Kwanza broiler management app
-- Paste this into Supabase SQL Editor and run

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    is_activated INTEGER DEFAULT 0,
    subscription_start TEXT,
    subscription_end TEXT,
    security_question TEXT,
    security_answer TEXT
);

CREATE TABLE IF NOT EXISTS farm_dates (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date_key TEXT NOT NULL,
    chicks_qty INTEGER DEFAULT 0,
    chicks_cost DOUBLE PRECISION DEFAULT 0.0,
    feed_cost DOUBLE PRECISION DEFAULT 0.0,
    med_cost DOUBLE PRECISION DEFAULT 0.0,
    other_cost DOUBLE PRECISION DEFAULT 0.0,
    mortality INTEGER DEFAULT 0,
    has_inputs INTEGER DEFAULT 0,
    has_sales INTEGER DEFAULT 0,
    UNIQUE(user_id, date_key)
);

CREATE TABLE IF NOT EXISTS sales_records (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date_key TEXT NOT NULL,
    customer TEXT NOT NULL,
    qty INTEGER NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    revenue DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS rounds (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    archived_at TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    UNIQUE(user_id, round_number)
);
