-- ═══ ФОКУС-ТРЕКЕР v2 — Миграция ═══
-- Запустить в Supabase SQL Editor

-- ══ 1. Обновляем goals ══
ALTER TABLE goals ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'work';
ALTER TABLE goals ADD COLUMN IF NOT EXISTS zone TEXT DEFAULT 'work';
ALTER TABLE goals ADD COLUMN IF NOT EXISTS target_rub BIGINT DEFAULT 0;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS paid_rub BIGINT DEFAULT 0;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS monthly_rub BIGINT DEFAULT 0;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS emoji TEXT DEFAULT '';
ALTER TABLE goals ADD COLUMN IF NOT EXISTS xp_per_task INT DEFAULT 25;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS sort_order INT DEFAULT 0;

-- ══ 2. Обновляем tasks ══
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS xp_earned INT DEFAULT 0;

-- ══ 3. Таблица платежей (если ещё нет) ══
CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    goal_id BIGINT REFERENCES goals(id) ON DELETE CASCADE,
    amount BIGINT NOT NULL,
    note TEXT DEFAULT '',
    paid_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payments_goal ON payments(goal_id);

-- ══ 4. Продажи ══
CREATE TABLE IF NOT EXISTS sales (
    id BIGSERIAL PRIMARY KEY,
    product_type TEXT NOT NULL, -- smm, dmp, site_bot
    client_name TEXT DEFAULT '',
    revenue BIGINT NOT NULL DEFAULT 0,
    cost BIGINT NOT NULL DEFAULT 0,
    margin BIGINT NOT NULL DEFAULT 0,
    note TEXT DEFAULT '',
    sold_at TIMESTAMPTZ DEFAULT now()
);

-- ══ 5. Награды ══
CREATE TABLE IF NOT EXISTS rewards (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    emoji TEXT DEFAULT '🎁',
    cost_xp INT NOT NULL DEFAULT 100,
    category TEXT DEFAULT 'food', -- food, purchase, fun, donate
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ══ 6. История забранных наград ══
CREATE TABLE IF NOT EXISTS reward_claims (
    id BIGSERIAL PRIMARY KEY,
    reward_id BIGINT REFERENCES rewards(id) ON DELETE SET NULL,
    reward_title TEXT NOT NULL,
    cost_xp INT NOT NULL,
    claimed_at TIMESTAMPTZ DEFAULT now()
);

-- ══ 7. XP аккаунт ══
CREATE TABLE IF NOT EXISTS xp_account (
    id BIGSERIAL PRIMARY KEY,
    total_xp INT DEFAULT 0,
    level INT DEFAULT 1,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Инициализируем XP аккаунт
INSERT INTO xp_account (total_xp, level)
SELECT 0, 1 WHERE NOT EXISTS (SELECT 1 FROM xp_account);

-- ══ 8. Расписание недели ══
CREATE TABLE IF NOT EXISTS schedule (
    id BIGSERIAL PRIMARY KEY,
    weekday INT NOT NULL, -- 0=ПН, 1=ВТ, ..., 6=ВС
    focus TEXT NOT NULL DEFAULT '',
    hours INT DEFAULT 4,
    tasks_template JSONB DEFAULT '[]'::jsonb
);

-- ══ 9. Ежедневные итоги ══
CREATE TABLE IF NOT EXISTS daily_summaries (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    focus_minutes INT DEFAULT 0,
    tasks_done INT DEFAULT 0,
    tasks_total INT DEFAULT 0,
    xp_earned INT DEFAULT 0,
    streak INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ══ RLS ══
ALTER TABLE sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE rewards ENABLE ROW LEVEL SECURITY;
ALTER TABLE reward_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE xp_account ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedule ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "full_access" ON sales FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "full_access" ON rewards FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "full_access" ON reward_claims FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "full_access" ON xp_account FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "full_access" ON schedule FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "full_access" ON daily_summaries FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "full_access" ON payments FOR ALL USING (true);
