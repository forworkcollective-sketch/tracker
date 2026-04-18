-- Trigger Tracker — Supabase Schema
-- Запусти в Supabase SQL Editor (Dashboard → SQL Editor → New Query)

CREATE TABLE goals (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    target_hours REAL DEFAULT 0,
    color TEXT DEFAULT '#6366f1',
    priority INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    deadline DATE
);

CREATE TABLE tasks (
    id BIGSERIAL PRIMARY KEY,
    goal_id BIGINT REFERENCES goals(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    estimate_min INTEGER DEFAULT 60,
    priority INTEGER DEFAULT 1,
    status TEXT DEFAULT 'todo',
    scheduled_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE time_logs (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    duration_min REAL DEFAULT 0
);

-- Индексы для скорости
CREATE INDEX idx_tasks_goal ON tasks(goal_id);
CREATE INDEX idx_tasks_date ON tasks(scheduled_date);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_timelogs_task ON time_logs(task_id);
CREATE INDEX idx_timelogs_started ON time_logs(started_at);
CREATE INDEX idx_timelogs_active ON time_logs(ended_at) WHERE ended_at IS NULL;

-- RLS: отключаем (бот работает через service_role key)
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE time_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON goals FOR ALL USING (true);
CREATE POLICY "Service role full access" ON tasks FOR ALL USING (true);
CREATE POLICY "Service role full access" ON time_logs FOR ALL USING (true);
