-- Milestones table for strategic Gantt
CREATE TABLE IF NOT EXISTS milestones (
    id SERIAL PRIMARY KEY,
    phase TEXT NOT NULL,
    title TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    color TEXT DEFAULT '#8B0020',
    status TEXT DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
    priority INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Add time fields to tasks for calendar day view
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS start_time TIME;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS end_time TIME;

-- Seed strategy milestones
INSERT INTO milestones (phase, title, start_date, end_date, color, status, priority) VALUES
('autopilot', 'Определить формат агентства', '2026-05-01', '2026-05-31', '#6366f1', 'todo', 1),
('autopilot', 'Первые 3 клиента на новой модели', '2026-06-01', '2026-06-30', '#8b5cf6', 'todo', 2),
('autopilot', 'Автоматизация привлечения', '2026-07-01', '2026-07-31', '#ec4899', 'todo', 3),
('autopilot', 'Делегирование продаж и реализации', '2026-08-01', '2026-08-31', '#f59e0b', 'todo', 4),
('autopilot', '500к/мес на автопилоте', '2026-09-01', '2026-09-30', '#10b981', 'todo', 5),
('freedom', 'Закрыть все долги', '2026-10-01', '2026-11-15', '#dc2626', 'todo', 6),
('freedom', 'Подушка + хотелки', '2026-11-01', '2026-12-31', '#16a34a', 'todo', 7),
('media', 'Запуск медийного проекта', '2027-01-01', '2027-03-31', '#D4A574', 'todo', 8),
('learning', 'Кештаун', '2026-05-01', '2026-12-31', '#60D0E0', 'todo', 9),
('learning', 'Разработка / вайбкодинг', '2026-05-01', '2026-12-31', '#5EE0A0', 'todo', 10);
