/* ═══ TRIGGER TRACKER — CYBERPUNK HUD SPA ═══ */

const API = '';
const BUDGET = 240;

const state = {
    tab: 'timer',
    plan: [],
    goals: [],
    workGoals: [],
    zones: [],
    stats: null,
    active: null,
    todayMin: 0,
    streak: 0,
    timeline: [],
    byGoal: [],
    showAddModal: false,
    loading: true,
};

/* ═══ API LAYER ═══ */
async function api(path, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    try {
        const res = await fetch(API + path, opts);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    } catch (e) {
        console.error(`API error: ${path}`, e);
        return null;
    }
}

async function loadAll() {
    const [plan, goalsData, stats, life] = await Promise.all([
        api('/api/plan/today'),
        api('/api/goals'),
        api('/api/stats'),
        api('/api/life-goals'),
    ]);
    if (plan) {
        state.plan = plan.tasks || [];
        state.workGoals = plan.goals || [];
        state.active = plan.active;
        state.todayMin = plan.today_min || 0;
        state.streak = plan.streak || 0;
        state.timeline = plan.timeline || [];
        state.byGoal = plan.by_goal || [];
    }
    if (goalsData) {
        state.goals = goalsData.work || [];
        state.zones = (life && life.zones) || [];
    }
    if (stats) state.stats = stats;
    state.loading = false;
    render();
}

/* ═══ ACTIONS ═══ */
async function startTimer(taskId) {
    await api(`/api/timer/start/${taskId}`, 'POST');
    await loadAll();
}

async function stopTimer() {
    await api('/api/timer/stop', 'POST');
    await loadAll();
}

async function completeTask(taskId) {
    await api(`/api/tasks/${taskId}/complete`, 'POST');
    await loadAll();
}

async function suggestPlan() {
    await api('/api/plan/suggest', 'POST');
    await loadAll();
}

async function deleteTask(taskId) {
    await api(`/api/tasks/${taskId}`, 'DELETE');
    await loadAll();
}

async function addCustomTask(title, goalId, estimateMin) {
    const body = { title, estimate_min: estimateMin || 60 };
    if (goalId) body.goal_id = goalId;
    const res = await api('/api/tasks/add', 'POST', body);
    if (res && res.ok) {
        state.showAddModal = false;
        await loadAll();
    }
}

/* ═══ HELPERS ═══ */
function fmtMin(m) {
    m = Math.round(m);
    const h = Math.floor(m / 60);
    const min = m % 60;
    if (h && min) return `${h}h ${min}m`;
    if (h) return `${h}h`;
    return `${min}m`;
}

function pct(a, b) { return b > 0 ? Math.min(Math.round(a / b * 100), 100) : 0; }
function fmtRub(n) { return n.toLocaleString('ru-RU') + '\u20BD'; }

function padZero(n) { return String(Math.round(n)).padStart(2, '0'); }

/* ═══ MAIN RENDER ═══ */
function render() {
    const app = document.getElementById('app');
    if (!app) return;

    app.innerHTML = `
        ${renderHeader()}
        <div class="section ${state.tab === 'timer' ? 'active' : ''}" data-section="timer">
            ${renderTimerSection()}
        </div>
        <div class="section ${state.tab === 'plan' ? 'active' : ''}" data-section="plan">
            ${renderPlanSection()}
        </div>
        <div class="section ${state.tab === 'goals' ? 'active' : ''}" data-section="goals">
            ${renderGoalsSection()}
        </div>
        <div class="section ${state.tab === 'life' ? 'active' : ''}" data-section="life">
            ${renderLifeSection()}
        </div>
        <div class="section ${state.tab === 'stats' ? 'active' : ''}" data-section="stats">
            ${renderStatsSection()}
        </div>
        ${renderBottomNav()}
        ${state.showAddModal ? renderAddTaskModal() : ''}
    `;

    bindEvents();
    if (state.tab === 'stats') renderCharts();
}

/* ═══ HEADER ═══ */
function renderHeader() {
    const d = new Date();
    const dateStr = d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
    const dayName = d.toLocaleDateString('ru-RU', { weekday: 'short' });
    return `
        <div class="header">
            <h1>TRIGGER</h1>
            <div class="subtitle">${dateStr} ${dayName} // 4h focus protocol</div>
        </div>
    `;
}

/* ═══ TIMER SECTION — HUD DISPLAY ═══ */
function renderTimerSection() {
    const p = pct(state.todayMin, BUDGET);
    const remaining = Math.max(0, BUDGET - state.todayMin);
    const hrs = Math.floor(state.todayMin / 60);
    const mins = padZero(state.todayMin % 60);

    let activeHtml = '';
    if (state.active) {
        const elapsed = (Date.now() - new Date(state.active.started_at).getTime()) / 60000;
        activeHtml = `
            <div class="active-task-hud scanline">
                <div class="active-indicator">
                    <div class="pulse-dot"></div>
                    <span class="active-label">Recording</span>
                </div>
                <div class="active-task-name">${esc(state.active.task_title)}</div>
                <div class="active-task-goal">${state.active.goal_title || ''}</div>
                <div class="active-task-time" id="activeElapsed">${fmtMin(elapsed)}</div>
                <div class="active-controls">
                    <button class="btn btn-complete" onclick="completeTask(${state.active.task_id || 0})">DONE</button>
                    <button class="btn btn-stop" onclick="stopTimer()">PAUSE</button>
                </div>
            </div>
        `;
    }

    let byGoalHtml = '';
    if (state.byGoal.length > 0) {
        byGoalHtml = `
            <div style="margin-top: 18px;">
                <div class="card-title">Time Distribution</div>
                ${state.byGoal.map(g => `
                    <div class="by-goal-row">
                        <span class="label">${g.emoji || ''} ${esc(g.title)}</span>
                        <span class="value">${fmtMin(g.total_min)}</span>
                    </div>
                    <div class="progress-bar" style="margin-bottom:8px;">
                        <div class="progress-fill" style="width:${pct(g.total_min, state.todayMin)}%;background:${g.color || 'var(--burg-light)'}"></div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    return `
        <div class="card scanline">
            <div class="hud-timer">
                <div class="streak-badge">
                    <span class="streak-fire">&#x1F525;</span>
                    <span class="streak-number">${state.streak}</span>
                    <span class="streak-label">${state.streak === 1 ? 'day' : 'days'} streak</span>
                </div>

                <div class="hud-time-display">
                    <div class="hud-digits" id="hudDigits">
                        ${hrs}<span class="sep">:</span>${mins}
                    </div>
                    <div class="hud-sub">of 4 hours today</div>
                    <div class="hud-remaining">${fmtMin(remaining)} remaining</div>
                </div>

                <div class="hud-progress-wrap">
                    <div class="hud-progress-track">
                        <div class="hud-progress-fill" id="hudProgressFill" style="width: ${p}%"></div>
                    </div>
                    <div class="hud-progress-labels">
                        <span>0h</span>
                        <span>1h</span>
                        <span>2h</span>
                        <span>3h</span>
                        <span>4h</span>
                    </div>
                    <div class="hud-pct">${p}%</div>
                </div>

                ${activeHtml}
            </div>
            ${byGoalHtml}
        </div>

        ${state.timeline.length > 0 ? `
        <div class="card">
            <div class="card-title">Timeline</div>
            ${state.timeline.map(e => `
                <div class="timeline-item ${e.active ? 'active' : ''}">
                    <div class="timeline-time">${e.start_time} \u2013 ${e.end_time}</div>
                    <div class="timeline-content">
                        <div class="timeline-task">${e.goal_emoji || ''} ${esc(e.task_title)}</div>
                        <div class="timeline-duration">${fmtMin(e.duration_min)}</div>
                    </div>
                </div>
            `).join('')}
        </div>
        ` : ''}
    `;
}

/* ═══ PLAN SECTION ═══ */
function renderPlanSection() {
    const todo = state.plan.filter(t => t.status !== 'done');
    const done = state.plan.filter(t => t.status === 'done');
    const totalEst = todo.reduce((s, t) => s + (t.estimate_min || 0), 0);

    return `
        <div class="card">
            <div class="card-title">Today's Plan // ${fmtMin(totalEst)} estimated</div>

            ${state.plan.length === 0 ? `
                <div class="empty-state">
                    <div class="empty-icon">&#x1F4A1;</div>
                    <div class="empty-text">No tasks yet. Get AI recommendations or add your own.</div>
                    <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;">
                        <button class="btn btn-primary" onclick="suggestPlan()">SUGGEST PLAN</button>
                        <button class="btn btn-secondary" onclick="openAddModal()">+ ADD TASK</button>
                    </div>
                </div>
            ` : ''}

            ${todo.map(t => renderTaskCard(t)).join('')}

            ${state.plan.length > 0 ? `
                <div style="margin-top:12px;">
                    <button class="btn btn-secondary btn-sm" onclick="openAddModal()">+ ADD TASK</button>
                </div>
            ` : ''}

            ${done.length > 0 ? `
                <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--glass-border);">
                    <div class="card-title" style="color:var(--green);">Completed</div>
                    ${done.map(t => renderTaskCard(t)).join('')}
                </div>
            ` : ''}
        </div>
    `;
}

function renderTaskCard(t) {
    const isActive = t.status === 'in_progress';
    const isDone = t.status === 'done';
    const cardClass = isActive ? 'is-active' : isDone ? 'is-done' : '';
    const iconClass = isDone ? 'done' : isActive ? 'running' : 'todo';
    const icon = isDone ? '\u2713' : isActive ? '\u25B6' : '\u25CB';

    let actions = '';
    if (isDone) {
        actions = `<span class="task-est">${fmtMin(t.estimate_min)}</span>`;
    } else if (isActive) {
        actions = `
            <button class="btn btn-complete btn-sm" onclick="event.stopPropagation();completeTask(${t.id})">DONE</button>
            <button class="btn btn-stop btn-sm" onclick="event.stopPropagation();stopTimer()">STOP</button>
        `;
    } else {
        actions = `
            <button class="btn btn-start" onclick="event.stopPropagation();startTimer(${t.id})">\u25B6 START</button>
            <span class="task-est">${fmtMin(t.estimate_min)}</span>
        `;
    }

    const deleteBtn = !isActive ? `<button class="btn-delete" onclick="event.stopPropagation();deleteTask(${t.id})" title="Delete">\u2715</button>` : '';

    return `
        <div class="task-card ${cardClass}">
            <div class="task-status-icon ${iconClass}"
                 onclick="${isActive ? 'stopTimer()' : isDone ? '' : `startTimer(${t.id})`}">
                ${icon}
            </div>
            <div class="task-body">
                <div class="task-name ${isDone ? 'done-text' : ''}">${esc(t.title)}</div>
                <div class="task-goal-label">${esc(t.goal_title || '')}</div>
            </div>
            <div class="task-actions">
                ${actions}
                ${deleteBtn}
            </div>
        </div>
    `;
}

/* ═══ GOALS SECTION ═══ */
function renderGoalsSection() {
    const goals = state.workGoals.length > 0 ? state.workGoals : state.goals;
    return `
        <div class="card">
            <div class="card-title">Work Goals</div>
            ${(goals || []).map(g => `
                <div class="goal-item">
                    <div class="goal-header">
                        <span class="goal-name">${esc(g.title)}</span>
                        <span class="goal-pct">${g.pct || 0}%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width:${g.pct || 0}%;background:${g.color || 'var(--burg-light)'}"></div>
                    </div>
                    <div class="goal-meta">
                        <span>${g.done_tasks || 0}/${g.total_tasks || 0} tasks</span>
                        <span>${g.hours_spent || 0}h worked</span>
                    </div>
                </div>
            `).join('')}
            ${(!goals || goals.length === 0) ? '<div class="empty-state"><div class="empty-text">No goals configured yet.</div></div>' : ''}
        </div>
    `;
}

/* ═══ LIFE SECTION ═══ */
function renderLifeSection() {
    const zoneColors = {
        debts: '#CD5C5C', goals: '#6083C8', travel: '#D4A574',
        future: '#6EBF8B', wife: '#C97FB5'
    };

    if (!state.zones.length) {
        return '<div class="card"><div class="empty-state"><div class="empty-text">No life goals data.</div></div></div>';
    }

    return state.zones.map(z => {
        const color = zoneColors[z.key] || z.color || 'var(--burg)';
        return `
        <div class="card">
            <div class="zone-card" style="border-left-color:${color}">
                <div class="zone-header">
                    <span class="zone-title">${esc(z.title)}</span>
                    <span class="zone-pct" style="color:${color}">${z.pct}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width:${z.pct}%;background:${color}"></div>
                </div>
                <div class="zone-stats">
                    ${z.total_target > 0 ? `
                        <span>Target: ${fmtRub(z.total_target)}</span>
                        <span>Paid: ${fmtRub(z.total_paid)}</span>
                        <span>Left: <b>${fmtRub(z.total_remaining)}</b></span>
                    ` : ''}
                    ${z.total_monthly > 0 ? `<span>Monthly: ${fmtRub(z.total_monthly)}</span>` : ''}
                </div>
                ${(z.goals_list || []).map(g => `
                    <div class="zone-detail-item">
                        <div class="zone-detail-head">
                            <span>${g.emoji || ''} ${esc(g.title)}</span>
                            ${g.target_rub > 0 ? `<span style="color:${color}">${g.pct}%</span>` : ''}
                            ${g.monthly_rub > 0 && !g.target_rub ? `<span>${fmtRub(g.monthly_rub)}/mo</span>` : ''}
                        </div>
                        ${g.target_rub > 0 ? `
                            <div class="zone-detail-bar">
                                <div style="width:${g.pct}%;background:${color}"></div>
                            </div>
                            <div class="zone-detail-meta">${fmtRub(g.paid_rub || 0)} / ${fmtRub(g.target_rub)}</div>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        </div>
        `;
    }).join('');
}

/* ═══ STATS SECTION ═══ */
function renderStatsSection() {
    if (!state.stats) return '<div class="card"><div class="card-title">Loading...</div></div>';
    return `
        <div class="card">
            <div class="card-title">Last 30 Days</div>
            <div class="chart-wrap"><canvas id="dailyChart"></canvas></div>
        </div>
        <div class="card">
            <div class="card-title">Time by Goal</div>
            <div class="chart-wrap"><canvas id="goalChart"></canvas></div>
        </div>
    `;
}

/* ═══ BOTTOM NAV ═══ */
function renderBottomNav() {
    const items = [
        { key: 'timer', icon: '\u23F1', label: 'Timer' },
        { key: 'plan', icon: '\u{1F4CB}', label: 'Plan' },
        { key: 'goals', icon: '\u{1F3AF}', label: 'Goals' },
        { key: 'life', icon: '\u{1F4BC}', label: 'Life' },
        { key: 'stats', icon: '\u{1F4CA}', label: 'Stats' },
    ];
    return `<div class="bottom-nav">${items.map(i => `
        <div class="nav-item ${state.tab === i.key ? 'active' : ''}" data-tab="${i.key}">
            <span class="nav-icon">${i.icon}</span>
            ${i.label}
        </div>
    `).join('')}</div>`;
}

/* ═══ ADD TASK MODAL ═══ */
function renderAddTaskModal() {
    const goalOptions = (state.workGoals.length > 0 ? state.workGoals : state.goals)
        .map(g => `<option value="${g.id}">${esc(g.title)}</option>`)
        .join('');

    return `
        <div class="modal-overlay" onclick="closeAddModal(event)">
            <div class="modal-sheet" onclick="event.stopPropagation()">
                <h3>Add Task</h3>
                <div class="modal-field">
                    <label>Task name</label>
                    <input type="text" id="newTaskTitle" placeholder="What needs to be done?" autofocus>
                </div>
                <div class="modal-field">
                    <label>Goal (optional)</label>
                    <select id="newTaskGoal">
                        <option value="">No goal</option>
                        ${goalOptions}
                    </select>
                </div>
                <div class="modal-field">
                    <label>Estimate (minutes)</label>
                    <input type="number" id="newTaskEstimate" value="60" min="5" max="480" step="5">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="state.showAddModal=false;render();">Cancel</button>
                    <button class="btn btn-primary" onclick="submitNewTask()">Add</button>
                </div>
            </div>
        </div>
    `;
}

function openAddModal() {
    state.showAddModal = true;
    render();
    setTimeout(() => {
        const inp = document.getElementById('newTaskTitle');
        if (inp) inp.focus();
    }, 100);
}

function closeAddModal(e) {
    if (e.target.classList.contains('modal-overlay')) {
        state.showAddModal = false;
        render();
    }
}

function submitNewTask() {
    const title = (document.getElementById('newTaskTitle').value || '').trim();
    if (!title) return;
    const goalSelect = document.getElementById('newTaskGoal');
    const goalId = goalSelect.value ? parseInt(goalSelect.value) : null;
    const estimate = parseInt(document.getElementById('newTaskEstimate').value) || 60;
    addCustomTask(title, goalId, estimate);
}

/* ═══ CHARTS ═══ */
function renderCharts() {
    if (!state.stats) return;

    const daily = state.stats.daily || [];
    const canvas1 = document.getElementById('dailyChart');
    if (daily.length && canvas1) {
        new Chart(canvas1, {
            type: 'bar',
            data: {
                labels: daily.map(d => d.day.slice(5)),
                datasets: [{
                    data: daily.map(d => +(d.total_min / 60).toFixed(1)),
                    backgroundColor: daily.map(d =>
                        d.total_min >= 240 ? 'rgba(94, 224, 160, 0.5)' :
                        d.total_min >= 120 ? 'rgba(212, 54, 79, 0.5)' :
                        'rgba(255, 248, 240, 0.08)'
                    ),
                    borderRadius: 4,
                    barThickness: 10,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ctx.raw + 'h' } } },
                scales: {
                    y: {
                        beginAtZero: true, max: 6,
                        grid: { color: 'rgba(255,248,240,0.03)' },
                        ticks: { color: '#6B5545', callback: v => v + 'h', font: { family: 'JetBrains Mono', size: 10 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#6B5545', font: { family: 'JetBrains Mono', size: 9 } }
                    }
                }
            }
        });
    }

    const byGoal = state.stats.by_goal || [];
    const canvas2 = document.getElementById('goalChart');
    if (byGoal.length && canvas2) {
        new Chart(canvas2, {
            type: 'doughnut',
            data: {
                labels: byGoal.map(g => g.title),
                datasets: [{
                    data: byGoal.map(g => +(g.total_min / 60).toFixed(1)),
                    backgroundColor: byGoal.map(g => g.color || '#9B1B30'),
                    borderWidth: 0,
                    spacing: 3,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: '#FFF5EB',
                            padding: 10,
                            font: { family: 'Rajdhani', size: 12 }
                        }
                    },
                    tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.raw + 'h' } }
                }
            }
        });
    }
}

/* ═══ EVENTS ═══ */
function bindEvents() {
    document.querySelectorAll('[data-tab]').forEach(el => {
        el.onclick = () => {
            state.tab = el.dataset.tab;
            render();
        };
    });

    // Enter key in add-task modal
    const titleInput = document.getElementById('newTaskTitle');
    if (titleInput) {
        titleInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') submitNewTask();
        });
    }
}

/* ═══ LIVE TIMER UPDATE ═══ */
let tickInterval;
function startLiveTick() {
    clearInterval(tickInterval);
    tickInterval = setInterval(() => {
        if (!state.active) return;

        const elapsed = (Date.now() - new Date(state.active.started_at).getTime()) / 60000;

        // Update active task elapsed display
        const elEl = document.getElementById('activeElapsed');
        if (elEl) elEl.textContent = fmtMin(elapsed);

        // Update HUD digits
        const alreadyCounted = state.active.already_counted || 0;
        const totalNow = state.todayMin + elapsed - alreadyCounted;
        const hrs = Math.floor(totalNow / 60);
        const mins = padZero(totalNow % 60);

        const digitsEl = document.getElementById('hudDigits');
        if (digitsEl) {
            digitsEl.innerHTML = `${hrs}<span class="sep">:</span>${mins}`;
        }

        // Update progress bar
        const p = Math.min(totalNow / BUDGET * 100, 100);
        const fillEl = document.getElementById('hudProgressFill');
        if (fillEl) fillEl.style.width = p + '%';
    }, 3000);
}

/* ═══ UTILITY ═══ */
function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

/* ═══ INIT ═══ */
document.addEventListener('DOMContentLoaded', () => {
    loadAll();
    startLiveTick();
    setInterval(loadAll, 60000);
});
