-- Добавляем поля под финансовые цели (из Финансист.jsx)

ALTER TABLE goals ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'work';
-- work | debt | money | travel | future | health | wife

ALTER TABLE goals ADD COLUMN IF NOT EXISTS zone TEXT DEFAULT 'work';
-- living | debts | wife | goals | travel | future | work

ALTER TABLE goals ADD COLUMN IF NOT EXISTS target_rub BIGINT DEFAULT 0;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS paid_rub BIGINT DEFAULT 0;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS monthly_rub BIGINT DEFAULT 0;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS emoji TEXT DEFAULT '';

-- Таблица платежей по финансовым целям (история: сколько и когда внёс)
CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    goal_id BIGINT REFERENCES goals(id) ON DELETE CASCADE,
    amount BIGINT NOT NULL,
    note TEXT DEFAULT '',
    paid_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payments_goal ON payments(goal_id);

ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON payments FOR ALL USING (true);
