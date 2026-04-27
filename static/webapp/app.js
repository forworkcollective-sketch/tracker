/* ═══ FOCUS TRACKER v2 — TELEGRAM MINI APP ═══ */

const API = '';
const BUDGET = 240; // 4h daily goal in minutes

/* ═══ STATE ═══ */
const state = {
    tab: 'timer',
    loading: true,
    // plan/today
    tasks: [],
    goals: [],
    active: null,
    todayMin: 0,
    pomodoros: 0,
    streak: 0,
    timeline: [],
    byGoal: [],
    schedule: null,
    xp: 0,
    // goals tab
    workGoals: [],
    debts: null,
    sales: null,
    // rewards
    rewards: null,
    xpData: null,
    // stats
    stats: null,
    // settings
    scheduleData: null,
    allGoals: [],
    allRewards: [],
    // modal
    modal: null,
    // calendar/track
    calView: 'day',  // day | week | month | gantt
    calDate: new Date().toISOString().slice(0, 10),
    calData: null,
    milestones: [],
};

/* ═══ TELEGRAM WEBAPP ═══ */
let tg = null;
try {
    tg = window.Telegram && window.Telegram.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
    }
} catch (e) { /* not in Telegram */ }

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

/* ═══ DATA LOADING ═══ */
async function loadAll() {
    const [plan, xpData, statsData] = await Promise.all([
        api('/api/plan/today'),
        api('/api/xp'),
        api('/api/stats'),
    ]);
    if (plan) {
        state.tasks = plan.tasks || [];
        state.goals = plan.goals || [];
        state.active = plan.active;
        state.todayMin = plan.today_min || 0;
        state.pomodoros = plan.pomodoros || 0;
        state.streak = plan.streak || 0;
        state.timeline = plan.timeline || [];
        state.byGoal = plan.by_goal || [];
        state.schedule = plan.schedule || null;
        state.xp = plan.xp || 0;
    }
    if (xpData) {
        state.xpData = xpData;
        state.xp = xpData.total_xp || state.xp;
        state.streak = xpData.streak || state.streak;
    }
    if (statsData) state.stats = statsData;
    state.loading = false;
    render();
}

async function loadGoalsTab() {
    const [goalsData, salesData] = await Promise.all([
        api('/api/goals'),
        api('/api/sales'),
    ]);
    if (goalsData) {
        state.workGoals = goalsData.work || [];
        // Extract debts from zones array (zone with key "debts")
        const zones = goalsData.zones || [];
        const debtsZone = zones.find(z => z.key === 'debts');
        if (debtsZone) {
            state.debts = debtsZone;
        }
    }
    if (salesData) state.sales = salesData;
    render();
}

async function loadRewardsTab() {
    const data = await api('/api/rewards');
    if (data) state.rewards = data;
    render();
}

async function loadTrackTab() {
    let endpoint = '';
    const v = state.calView;
    if (v === 'day') endpoint = `/api/calendar/day?date_str=${state.calDate}`;
    else if (v === 'week') endpoint = `/api/calendar/week?date_str=${state.calDate}`;
    else if (v === 'month') endpoint = `/api/calendar/month?month=${state.calDate.slice(0, 7)}`;
    else endpoint = `/api/milestones`;

    const [calData, milestones] = await Promise.all([
        api(endpoint),
        v !== 'gantt' ? api('/api/milestones') : null,
    ]);
    if (calData) {
        state.calData = calData;
        if (v === 'gantt') state.milestones = calData.milestones || [];
        else state.milestones = milestones?.milestones || [];
    }
    render();
}

function calNavigate(delta) {
    const d = new Date(state.calDate);
    if (state.calView === 'day') d.setDate(d.getDate() + delta);
    else if (state.calView === 'week') d.setDate(d.getDate() + delta * 7);
    else if (state.calView === 'month') d.setMonth(d.getMonth() + delta);
    else d.setMonth(d.getMonth() + delta * 3);
    state.calDate = d.toISOString().slice(0, 10);
    loadTrackTab();
}

function setCalView(v) {
    state.calView = v;
    loadTrackTab();
}

async function loadSettingsTab() {
    const [schedData, goalsData, rewardsData] = await Promise.all([
        api('/api/schedule'),
        api('/api/goals'),
        api('/api/rewards'),
    ]);
    if (schedData) state.scheduleData = schedData;
    if (goalsData) {
        const debtsZone = (goalsData.zones || []).find(z => z.key === 'debts');
        const debtGoals = debtsZone ? (debtsZone.goals_list || debtsZone.items || []) : [];
        state.allGoals = [...(goalsData.work || []), ...debtGoals];
    }
    if (rewardsData) state.allRewards = rewardsData.rewards || [];
    render();
}

/* ═══ ACTIONS ═══ */
async function startTimer(taskId) {
    await api(`/api/timer/start/${taskId}`, 'POST');
    await loadAll();
}

async function stopTimer() {
    const res = await api('/api/timer/stop', 'POST');
    if (res && res.xp_earned) showToast(`+${res.xp_earned} XP`);
    await loadAll();
}

async function completeTask(taskId) {
    const res = await api(`/api/tasks/${taskId}/complete`, 'POST');
    if (res && res.xp_earned) showToast(`+${res.xp_earned} XP`);
    await loadAll();
}

async function deleteTask(taskId) {
    await api(`/api/tasks/${taskId}`, 'DELETE');
    await loadAll();
}

async function suggestPlan() {
    const res = await api('/api/plan/suggest', 'POST');
    if (res && res.ok) showToast(`Запланировано ${res.scheduled} задач`);
    await loadAll();
}

async function addTask(title, goalId, estimateMin) {
    const body = { title, estimate_min: estimateMin || 60 };
    if (goalId) body.goal_id = goalId;
    const res = await api('/api/tasks/add', 'POST', body);
    if (res && res.ok) {
        closeModal();
        await loadAll();
    }
}

async function editTask(taskId, title, estimateMin, goalId) {
    const body = { title, estimate_min: estimateMin };
    if (goalId) body.goal_id = goalId;
    await api(`/api/tasks/${taskId}`, 'PUT', body);
    closeModal();
    await loadAll();
}

async function payDebt(goalId, amount, note) {
    const res = await api('/api/debts/pay', 'POST', { goal_id: goalId, amount, note });
    if (res && res.ok) showToast('Платёж внесён');
    closeModal();
    await loadGoalsTab();
}

async function addSale(productType, revenue, cost, clientName, note) {
    const res = await api('/api/sales', 'POST', {
        product_type: productType, revenue, cost, client_name: clientName, note
    });
    if (res && res.ok) showToast('Продажа добавлена');
    closeModal();
    await loadGoalsTab();
}

async function claimReward(rewardId) {
    const res = await api(`/api/rewards/claim/${rewardId}`, 'POST');
    if (res && res.ok) showToast(res.message || 'Награда получена!');
    await loadRewardsTab();
    await loadAll();
}

async function addReward(title, emoji, costXp, category) {
    await api('/api/rewards', 'POST', { title, emoji, cost_xp: costXp, category });
    closeModal();
    await loadRewardsTab();
}

async function editReward(id, title, emoji, costXp, category) {
    await api(`/api/rewards/${id}`, 'PUT', { title, emoji, cost_xp: costXp, category });
    closeModal();
    await loadRewardsTab();
}

async function deleteReward(id) {
    await api(`/api/rewards/${id}`, 'DELETE');
    await loadRewardsTab();
}

async function addGoal(title, description, type, zone, targetRub, emoji, color) {
    await api('/api/goals', 'POST', {
        title, description, type, zone, target_rub: targetRub, emoji, color
    });
    closeModal();
    await loadSettingsTab();
}

async function editGoal(id, title, emoji, color) {
    await api(`/api/goals/${id}`, 'PUT', { title, emoji, color });
    closeModal();
    await loadSettingsTab();
}

async function deleteGoal(id) {
    await api(`/api/goals/${id}`, 'DELETE');
    await loadSettingsTab();
}

async function saveScheduleDay(weekday, focus, hours) {
    await api(`/api/schedule/${weekday}`, 'PUT', { focus, hours });
}

/* ═══ HELPERS ═══ */
function fmtMin(m) {
    m = Math.max(0, Math.round(m || 0));
    const h = Math.floor(m / 60);
    const min = m % 60;
    if (h && min) return `${h}ч ${min}м`;
    if (h) return `${h}ч`;
    return `${min}м`;
}
function fmtRub(n) {
    if (!n && n !== 0) return '0\u20BD';
    if (n >= 1000) return Math.round(n / 1000) + 'к\u20BD';
    return Math.round(n).toLocaleString('ru-RU') + '\u20BD';
}
function fmtRubFull(n) {
    return Math.round(n || 0).toLocaleString('ru-RU') + '\u20BD';
}
function pct(a, b) { return b > 0 ? Math.max(0, Math.min(Math.round((a || 0) / b * 100), 100)) : 0; }
function padZero(n) { return String(Math.max(0, Math.round(n))).padStart(2, '0'); }
function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

const DAY_NAMES = ['ВС', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ'];
const DAY_NAMES_FULL = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];

function todayDayName() {
    return DAY_NAMES[new Date().getDay()];
}
function todayDateStr() {
    return new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

/* ═══ TOAST ═══ */
function showToast(msg) {
    let el = document.getElementById('toast');
    if (!el) {
        el = document.createElement('div');
        el.id = 'toast';
        el.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:999;' +
            'padding:10px 24px;border-radius:12px;background:rgba(94,224,160,0.15);border:1px solid rgba(94,224,160,0.3);' +
            'color:#5EE0A0;font-family:Orbitron,sans-serif;font-size:12px;font-weight:700;letter-spacing:2px;' +
            'backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);pointer-events:none;' +
            'animation:fade-in 0.3s ease;text-align:center;';
        document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.display = 'block';
    el.style.animation = 'fade-in 0.3s ease';
    setTimeout(() => { el.style.display = 'none'; }, 2000);
}

/* ═══ MODAL SYSTEM ═══ */
function openModal(type, data = {}) {
    state.modal = { type, ...data };
    render();
    setTimeout(() => {
        const first = document.querySelector('.modal-sheet input, .modal-sheet select');
        if (first) first.focus();
    }, 150);
}
function closeModal() {
    state.modal = null;
    render();
}

/* ═══ MAIN RENDER ═══ */
function render() {
    const app = document.getElementById('app');
    if (!app) return;

    if (state.loading) {
        app.innerHTML = `
            <div class="loading-screen">
                <div class="loading-spinner"></div>
                <div class="loading-text">LOADING...</div>
            </div>
        `;
        return;
    }

    app.innerHTML = `
        ${renderHeader()}
        <div class="section ${state.tab === 'timer' ? 'active' : ''}" data-section="timer">
            ${renderTimerTab()}
        </div>
        <div class="section ${state.tab === 'plan' ? 'active' : ''}" data-section="plan">
            ${renderPlanTab()}
        </div>
        <div class="section ${state.tab === 'goals' ? 'active' : ''}" data-section="goals">
            ${renderGoalsTab()}
        </div>
        <div class="section ${state.tab === 'rewards' ? 'active' : ''}" data-section="rewards">
            ${renderRewardsTab()}
        </div>
        <div class="section ${state.tab === 'track' ? 'active' : ''}" data-section="track">
            ${renderTrackTab()}
        </div>
        <div class="section ${state.tab === 'stats' ? 'active' : ''}" data-section="stats">
            ${renderStatsTab()}
        </div>
        <div class="section ${state.tab === 'settings' ? 'active' : ''}" data-section="settings">
            ${renderSettingsTab()}
        </div>
        ${renderBottomNav()}
        ${state.modal ? renderModal() : ''}
    `;

    bindEvents();
    if (state.tab === 'stats') renderCharts();
    if (state.tab === 'track' && !state.calData) loadTrackTab();
}

/* ═══ HEADER ═══ */
function renderHeader() {
    return `
        <div class="header">
            <h1>ФОКУС-ТРЕКЕР</h1>
            <div class="header-sub">${todayDateStr()} ${todayDayName()} // протокол 4ч</div>
            <div class="header-badges">
                <div class="badge badge-streak">
                    <span>\uD83D\uDD25</span>
                    <span class="badge-num">${state.streak}</span>
                    <span>${state.streak === 1 ? 'день' : 'дней'}</span>
                </div>
                <div class="badge badge-xp">
                    <span>\u2B50</span>
                    <span class="badge-num">${state.xp}</span>
                    <span>XP</span>
                </div>
            </div>
        </div>
    `;
}

/* ═══ TAB 1: TIMER ═══ */
function renderTimerTab() {
    const todayMinSafe = Math.max(0, state.todayMin);
    const p = pct(todayMinSafe, BUDGET);
    const remaining = Math.max(0, BUDGET - todayMinSafe);
    const hrs = Math.floor(todayMinSafe / 60);
    const mins = padZero(todayMinSafe % 60);
    const pomTarget = Math.ceil(BUDGET / 30);

    let activeHtml = '';
    if (state.active) {
        const elapsed = Math.max(0, (Date.now() - new Date(state.active.started_at).getTime()) / 60000);
        const pomElapsed = Math.floor(elapsed / 30);
        const pomMin = Math.floor(elapsed % 30);
        const pomSec = Math.floor(((elapsed % 30) - pomMin) * 60);
        activeHtml = `
            <div class="active-task-hud">
                <div class="active-indicator">
                    <div class="pulse-dot"></div>
                    <span class="active-label">В РАБОТЕ</span>
                </div>
                <div class="active-task-name">${esc(state.active.task_title)}</div>
                <div class="active-task-goal">${state.active.goal_title || ''}</div>
                <div class="active-task-time" id="activeElapsed">${fmtMin(elapsed)}</div>
                <div class="active-controls">
                    <button class="btn btn-complete" onclick="completeTask(${state.active.task_id || 0})">\u2713 ГОТОВО</button>
                    <button class="btn btn-stop" onclick="stopTimer()">\u23F8 ПАУЗА</button>
                </div>
            </div>
        `;
    }

    let byGoalHtml = '';
    if (state.byGoal.length > 0) {
        byGoalHtml = `
            <div class="mt-16">
                <div class="card-title">\uD83D\uDCCA Распределение времени</div>
                ${state.byGoal.map(g => `
                    <div class="by-goal-row">
                        <span class="label">${g.emoji || '\uD83C\uDFAF'} ${esc(g.title)}</span>
                        <span class="value">${fmtMin(g.total_min)}</span>
                    </div>
                    <div class="progress-bar mb-8">
                        <div class="progress-fill" style="width:${pct(g.total_min, state.todayMin)}%;background:${g.color || 'var(--burg-light)'}"></div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    return `
        <div class="card scanline">
            <div class="hud-timer">
                <div class="hud-pomodoros">
                    <span class="pom-icon">\uD83C\uDF45</span>
                    ${Math.max(0, state.pomodoros)}/${pomTarget} 🍅
                </div>

                <div class="hud-time-display">
                    <div class="hud-digits" id="hudDigits">
                        ${hrs}<span class="sep">:</span>${mins}
                    </div>
                    <div class="hud-sub">из 4ч</div>
                    <div class="hud-remaining">ещё ${fmtMin(remaining)}</div>
                </div>

                <div class="hud-progress-wrap">
                    <div class="hud-progress-track">
                        <div class="hud-progress-fill" id="hudProgressFill" style="width: ${p}%"></div>
                    </div>
                    <div class="hud-progress-labels">
                        <span>0ч</span><span>1ч</span><span>2ч</span><span>3ч</span><span>4ч</span>
                    </div>
                    <div class="hud-pct">${p}%</div>
                </div>

                ${activeHtml}
            </div>
            ${byGoalHtml}
        </div>

        ${state.timeline.length > 0 ? `
        <div class="card">
            <div class="card-title">\uD83D\uDCCB Таймлайн</div>
            ${state.timeline.map(e => `
                <div class="timeline-item ${e.active ? 'active' : ''}">
                    <div class="timeline-time">${e.start_time} \u2013 ${e.end_time || 'сейчас'}</div>
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

/* ═══ TAB 2: PLAN ═══ */
function renderPlanTab() {
    const todo = state.tasks.filter(t => t.status !== 'done');
    const done = state.tasks.filter(t => t.status === 'done');
    const totalEst = todo.reduce((s, t) => s + (t.estimate_min || 0), 0);

    const schedInfo = state.schedule
        ? `<div class="schedule-bar"><span class="sch-icon">\uD83D\uDCC5</span> Сегодня ${todayDayName()} \u2014 фокус: ${esc(state.schedule.focus || 'Свободный')}</div>`
        : '';

    return `
        ${schedInfo}
        <div class="card">
            <div class="card-title">\uD83D\uDCCB ПЛАН ДНЯ // ${fmtMin(totalEst)}</div>

            ${state.tasks.length === 0 ? `
                <div class="empty-state">
                    <div class="empty-icon">\uD83D\uDCA1</div>
                    <div class="empty-text">Пусто. Получи план или добавь задачи</div>
                    <div class="flex-row center wrap">
                        <button class="btn btn-primary" onclick="suggestPlan()">\uD83E\uDD16 ПЛАН</button>
                        <button class="btn btn-secondary" onclick="openModal('addTask')">+ Задача</button>
                    </div>
                </div>
            ` : ''}

            ${todo.map(t => renderTaskCard(t)).join('')}

            ${state.tasks.length > 0 ? `
                <div class="flex-row mt-12">
                    <button class="btn btn-secondary btn-sm" onclick="openModal('addTask')">+ Задача</button>
                    <button class="btn btn-secondary btn-sm" onclick="suggestPlan()">\uD83E\uDD16 ПЛАН</button>
                </div>
            ` : ''}

            ${done.length > 0 ? `
                <div class="mt-16 pt-12 border-t">
                    <div class="card-title text-green">\u2713 Выполнено (${done.length})</div>
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
            <button class="btn btn-complete btn-sm" onclick="event.stopPropagation();completeTask(${t.id})">ГОТОВО</button>
            <button class="btn btn-stop btn-sm" onclick="event.stopPropagation();stopTimer()">СТОП</button>
        `;
    } else {
        actions = `
            <button class="btn btn-start" onclick="event.stopPropagation();startTimer(${t.id})">\u25B6 СТАРТ</button>
            <span class="task-est">${fmtMin(t.estimate_min)}</span>
        `;
    }

    const deleteBtn = !isActive ? `<button class="btn-delete" onclick="event.stopPropagation();deleteTask(${t.id})" title="Удалить">\u2715</button>` : '';

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

/* ═══ TAB 3: GOALS ═══ */
function renderGoalsTab() {
    if (!state.debts && !state.sales) {
        return `<div class="card"><div class="loading-screen"><div class="loading-spinner"></div><div class="loading-text">LOADING...</div></div></div>`;
    }

    let debtHtml = '';
    if (state.debts) {
        const d = state.debts;
        debtHtml = `
        <div class="card card-gold">
            <div class="card-title">\uD83D\uDCB0 Финансовая цель</div>
            <div class="debt-hero">
                <div class="debt-hero-amount">${fmtRub(d.total_target)}</div>
                <div class="debt-hero-label">цель // ${d.pct || 0}% закрыто</div>
                <div class="progress-bar thick mt-8">
                    <div class="progress-fill" style="width:${d.pct || 0}%;background:linear-gradient(90deg, var(--gold), #E8C090)"></div>
                </div>
                <div class="flex-row between mt-8">
                    <span class="text-sm text-mono text-green">\u2713 ${fmtRubFull(d.total_paid)}</span>
                    <span class="text-sm text-mono text-dim">\u2192 ${fmtRubFull(d.total_remaining)}</span>
                </div>
            </div>
            ${(d.items || []).map(item => `
                <div class="debt-card">
                    <div class="debt-icon">${item.paid_rub > 0 ? '\uD83D\uDD13' : '\uD83D\uDD12'}</div>
                    <div class="debt-info">
                        <div class="debt-title">${esc(item.title)}</div>
                        <div class="debt-nums"><b>${fmtRubFull(item.paid_rub || 0)}</b> / ${fmtRubFull(item.target_rub)}</div>
                        <div class="progress-bar debt-bar mt-8">
                            <div class="progress-fill" style="width:${item.pct || 0}%;background:var(--gold)"></div>
                        </div>
                    </div>
                    <div class="debt-action">
                        <button class="btn btn-gold btn-sm" onclick="openModal('payDebt', {goalId:${item.id},title:'${esc(item.title)}'})">
                            \uD83D\uDCB3
                        </button>
                    </div>
                </div>
            `).join('')}
        </div>
        `;
    }

    let workGoalsHtml = '';
    if (state.workGoals && state.workGoals.length > 0) {
        workGoalsHtml = `
        <div class="card">
            <div class="card-title">\uD83C\uDFAF Рабочие цели</div>
            ${state.workGoals.map(g => `
                <div class="goal-item">
                    <div class="goal-header">
                        <span class="goal-name">${g.emoji || '\uD83C\uDFAF'} ${esc(g.title)}</span>
                        <span class="goal-pct">${g.pct || 0}%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width:${g.pct || 0}%;background:${g.color || 'var(--burg-light)'}"></div>
                    </div>
                    <div class="goal-meta">
                        <span>${g.done_tasks || 0}/${g.total_tasks || 0} задач</span>
                        <span>${fmtMin((g.hours_spent || 0) * 60)}</span>
                    </div>
                </div>
            `).join('')}
        </div>
        `;
    }

    let salesHtml = '';
    if (state.sales) {
        const s = state.sales;
        salesHtml = `
        <div class="card">
            <div class="card-title">\uD83D\uDCC8 Продажи</div>
            <div class="sales-grid">
                <div class="sales-stat">
                    <div class="stat-value">${s.total_clients || 0}</div>
                    <div class="stat-label">Клиентов</div>
                </div>
                <div class="sales-stat">
                    <div class="stat-value">${fmtRub(s.total_revenue)}</div>
                    <div class="stat-label">Выручка</div>
                </div>
                <div class="sales-stat">
                    <div class="stat-value text-green">${fmtRub(s.total_margin)}</div>
                    <div class="stat-label">Маржа</div>
                </div>
            </div>
            ${(s.by_product || []).map(p => `
                <div class="sales-product">
                    <span class="sp-name">${esc(p.product_type)}</span>
                    <span class="sp-value">${fmtRubFull(p.revenue)}</span>
                </div>
            `).join('')}
            <div class="mt-12">
                <button class="btn btn-green btn-sm btn-block" onclick="openModal('addSale')">+ Внести продажу</button>
            </div>
        </div>
        `;
    }

    return debtHtml + workGoalsHtml + salesHtml;
}

/* ═══ TAB 4: REWARDS ═══ */
function renderRewardsTab() {
    if (!state.rewards) {
        return `<div class="card"><div class="loading-screen"><div class="loading-spinner"></div><div class="loading-text">LOADING...</div></div></div>`;
    }

    const r = state.rewards;
    const xp = (state.xpData ? state.xpData.total_xp : null) || r.xp || state.xp || 0;
    const level = state.xpData ? state.xpData.level : 1;
    const rewards = r.rewards || [];
    const history = r.history || [];

    return `
        <div class="card">
            <div class="xp-hero">
                <div class="xp-hero-amount">${xp}</div>
                <div class="xp-hero-label">Experience Points</div>
                <div class="xp-hero-level">\uD83C\uDFC6 Level ${level}</div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">\uD83D\uDED2 Каталог наград</div>
            ${rewards.length === 0 ? `
                <div class="empty-state">
                    <div class="empty-icon">\uD83C\uDF81</div>
                    <div class="empty-text">Добавь награды, чтобы мотивироваться!</div>
                </div>
            ` : ''}
            ${rewards.map(rw => `
                <div class="reward-card">
                    <div class="reward-emoji">${rw.emoji || '\uD83C\uDF81'}</div>
                    <div class="reward-info">
                        <div class="reward-title">${esc(rw.title)}</div>
                        <div class="reward-cost">${rw.cost_xp} XP</div>
                    </div>
                    <div class="reward-actions">
                        <button class="btn-claim ${xp >= rw.cost_xp ? '' : ''}"
                                ${xp < rw.cost_xp ? 'disabled' : ''}
                                onclick="claimReward(${rw.id})">
                            ${xp >= rw.cost_xp ? '\uD83C\uDF1F Забрать' : `\uD83D\uDD12 ${rw.cost_xp} XP`}
                        </button>
                        <button class="btn-delete" onclick="openModal('editReward', ${JSON.stringify(rw).replace(/"/g, '&quot;')})" title="Ред.">\u270F</button>
                    </div>
                </div>
            `).join('')}
            <div class="mt-12">
                <button class="btn btn-secondary btn-sm btn-block" onclick="openModal('addReward')">+ Добавить награду</button>
            </div>
        </div>

        ${history.length > 0 ? `
        <div class="card">
            <div class="card-title">\uD83D\uDCDC История</div>
            ${history.map(h => `
                <div class="reward-history-item">
                    <span class="rh-title">${h.emoji || ''} ${esc(h.title)}</span>
                    <span class="rh-date">${h.claimed_at || ''}</span>
                </div>
            `).join('')}
        </div>
        ` : ''}
    `;
}

/* ═══ TAB 5: STATS ═══ */
function renderStatsTab() {
    if (!state.stats) {
        return `<div class="card"><div class="loading-screen"><div class="loading-spinner"></div><div class="loading-text">LOADING...</div></div></div>`;
    }
    const s = state.stats;

    return `
        <div class="card">
            <div class="card-title">\uD83D\uDCCA Последние 30 дней</div>
            <div class="chart-wrap"><canvas id="dailyChart"></canvas></div>
        </div>
        <div class="card">
            <div class="card-title">\uD83C\uDFAF Время по целям</div>
            <div class="chart-wrap"><canvas id="goalChart"></canvas></div>
        </div>
        <div class="card">
            <div class="card-title">\uD83D\uDCCB Сводка</div>
            <div class="stat-row">
                <span class="sr-label">\uD83D\uDD25 Стрик</span>
                <span class="sr-value">${s.streak || 0} дней</span>
            </div>
            <div class="stat-row">
                <span class="sr-label">\u23F1 Сегодня</span>
                <span class="sr-value">${fmtMin(s.today_minutes || 0)}</span>
            </div>
            <div class="stat-row">
                <span class="sr-label">\uD83C\uDF45 Помодорок</span>
                <span class="sr-value">${s.pomodoros || 0}</span>
            </div>
            <div class="stat-row">
                <span class="sr-label">\u2B50 XP</span>
                <span class="sr-value">${s.xp || state.xp || 0}</span>
            </div>
            ${s.sales ? `
            <div class="stat-row">
                <span class="sr-label">\uD83D\uDCB0 Продажи</span>
                <span class="sr-value">${fmtRub(s.sales.total_revenue || 0)}</span>
            </div>
            ` : ''}
            ${s.debts ? `
            <div class="stat-row">
                <span class="sr-label">\uD83D\uDCB3 Долги</span>
                <span class="sr-value">${s.debts.pct || 0}%</span>
            </div>
            ` : ''}
        </div>
    `;
}

/* ═══ TAB 6: SETTINGS ═══ */
function renderSettingsTab() {
    if (!state.scheduleData) {
        return `<div class="card"><div class="loading-screen"><div class="loading-spinner"></div><div class="loading-text">LOADING...</div></div></div>`;
    }

    const schedule = state.scheduleData.schedule || [];
    const todayIdx = state.scheduleData.today;
    const dayLabels = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'];

    let scheduleHtml = schedule.map((day, i) => {
        const isToday = (i === todayIdx) || (day.weekday === todayIdx);
        const wd = day.weekday !== undefined ? day.weekday : i;
        return `
            <div class="schedule-day ${isToday ? 'is-today' : ''}">
                <div class="sd-day">${dayLabels[i] || dayLabels[wd] || i}</div>
                <div class="sd-focus">
                    <input type="text" value="${esc(day.focus || '')}" placeholder="Фокус..."
                           onblur="saveScheduleDay(${wd}, this.value, this.closest('.schedule-day').querySelector('.sd-hours input').value)">
                </div>
                <div class="sd-hours">
                    <input type="number" value="${day.hours || 4}" min="0" max="12" step="0.5"
                           onblur="saveScheduleDay(${wd}, this.closest('.schedule-day').querySelector('.sd-focus input').value, this.value)">
                    <span class="sd-hours-label">ч</span>
                </div>
            </div>
        `;
    }).join('');

    let goalsListHtml = '';
    if (state.allGoals && state.allGoals.length > 0) {
        goalsListHtml = state.allGoals.map(g => `
            <div class="settings-item">
                <div class="si-left">
                    <span class="si-emoji">${g.emoji || '\uD83C\uDFAF'}</span>
                    <div>
                        <div class="si-title">${esc(g.title)}</div>
                        <div class="si-sub">${g.type || ''} ${g.zone ? '/ ' + g.zone : ''}</div>
                    </div>
                </div>
                <div class="si-actions">
                    <button class="btn-delete" onclick="openModal('editGoal', ${JSON.stringify({id:g.id,title:g.title,emoji:g.emoji||'',color:g.color||''}).replace(/"/g,'&quot;')})" title="Ред.">\u270F</button>
                    <button class="btn-delete" onclick="if(confirm('Удалить цель?'))deleteGoal(${g.id})" title="Удалить">\u2715</button>
                </div>
            </div>
        `).join('');
    }

    let rewardsListHtml = '';
    if (state.allRewards && state.allRewards.length > 0) {
        rewardsListHtml = state.allRewards.map(rw => `
            <div class="settings-item">
                <div class="si-left">
                    <span class="si-emoji">${rw.emoji || '\uD83C\uDF81'}</span>
                    <div>
                        <div class="si-title">${esc(rw.title)}</div>
                        <div class="si-sub">${rw.cost_xp} XP ${rw.category ? '/ ' + rw.category : ''}</div>
                    </div>
                </div>
                <div class="si-actions">
                    <button class="btn-delete" onclick="openModal('editReward', ${JSON.stringify(rw).replace(/"/g,'&quot;')})" title="Ред.">\u270F</button>
                    <button class="btn-delete" onclick="if(confirm('Удалить награду?'))deleteReward(${rw.id})" title="Удалить">\u2715</button>
                </div>
            </div>
        `).join('');
    }

    return `
        <div class="card">
            <div class="card-title">\uD83D\uDCC5 Расписание недели</div>
            ${scheduleHtml}
        </div>

        <div class="card">
            <div class="card-title">\u2600\uFE0F Дизайн дня</div>
            <div class="stat-row">
                <span class="sr-label">\uD83C\uDF05 Утро (7-12)</span>
                <span class="sr-value text-gold" style="font-size:12px">Ритуал + глубокая работа</span>
            </div>
            <div class="stat-row">
                <span class="sr-label">\u2600\uFE0F День (12-17)</span>
                <span class="sr-value text-gold" style="font-size:12px">Встречи + коммуникация</span>
            </div>
            <div class="stat-row">
                <span class="sr-label">\uD83C\uDF19 Вечер (17-22)</span>
                <span class="sr-value text-gold" style="font-size:12px">Обучение + отдых</span>
            </div>
        </div>

        <div class="card">
            <div class="settings-section-title">\uD83C\uDFAF Цели</div>
            ${goalsListHtml}
            <div class="mt-12">
                <button class="btn btn-secondary btn-sm btn-block" onclick="openModal('addGoal')">+ Добавить цель</button>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">\uD83C\uDF81 Награды</div>
                ${rewardsListHtml}
                <div class="mt-12">
                    <button class="btn btn-secondary btn-sm btn-block" onclick="openModal('addReward')">+ Добавить награду</button>
                </div>
            </div>
        </div>
    `;
}

/* ═══ BOTTOM NAV ═══ */
/* ═══ TAB: TRACK (Calendar + Gantt) ═══ */

const DAYS_SHORT = ['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'];
const MONTHS_RU = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];

function renderTrackTab() {
    const cd = new Date(state.calDate);
    let dateLabel = '';
    if (state.calView === 'day') {
        dateLabel = `${cd.getDate()} ${MONTHS_RU[cd.getMonth()]}`;
    } else if (state.calView === 'week') {
        const mon = new Date(cd); mon.setDate(cd.getDate() - cd.getDay() + (cd.getDay() === 0 ? -6 : 1));
        const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
        dateLabel = `${mon.getDate()} - ${sun.getDate()} ${MONTHS_RU[sun.getMonth()]}`;
    } else if (state.calView === 'month') {
        dateLabel = `${MONTHS_RU[cd.getMonth()]} ${cd.getFullYear()}`;
    } else {
        dateLabel = `${cd.getFullYear()}`;
    }

    const isToday = state.calDate === new Date().toISOString().slice(0, 10);

    return `
        <div class="track-header">
            <div class="track-view-switcher">
                ${['day','week','month','gantt'].map(v => `
                    <button class="track-view-btn ${state.calView === v ? 'active' : ''}"
                            onclick="setCalView('${v}')">
                        ${{day:'День',week:'Неделя',month:'Месяц',gantt:'Гант'}[v]}
                    </button>
                `).join('')}
            </div>
            <div class="track-nav">
                <button class="track-nav-btn" onclick="calNavigate(-1)">\u2039</button>
                <span class="track-date-label">${dateLabel}</span>
                <button class="track-nav-btn" onclick="calNavigate(1)">\u203A</button>
                ${!isToday ? `<button class="track-today-btn" onclick="state.calDate=new Date().toISOString().slice(0,10);loadTrackTab()">Сегодня</button>` : ''}
            </div>
        </div>
        <div class="track-content">
            ${state.calData ? renderCalContent() : '<div class="track-loading">Загрузка...</div>'}
        </div>
        <div class="track-fab" onclick="openTrackAddModal()">+</div>
    `;
}

function renderCalContent() {
    switch (state.calView) {
        case 'day': return renderDayView();
        case 'week': return renderWeekView();
        case 'month': return renderMonthView();
        case 'gantt': return renderGanttView();
        default: return '';
    }
}

function renderDayView() {
    const data = state.calData;
    if (!data) return '';
    const hours = [];
    for (let h = 6; h <= 23; h++) hours.push(h);

    // Build task blocks positioned on timeline
    const tasks = data.tasks || [];
    const logs = data.logs || [];
    const ical = data.ical_events || [];

    let blocksHtml = '';

    // Time log blocks (actual work done)
    logs.forEach(log => {
        if (!log.started_at) return;
        const start = new Date(log.started_at);
        const startMin = start.getHours() * 60 + start.getMinutes();
        const dur = log.duration_min || 30;
        const top = ((startMin - 360) / 60) * 60; // 6am = 0
        const height = Math.max((dur / 60) * 60, 20);
        if (top < 0) return;
        blocksHtml += `
            <div class="cal-block cal-block-log" style="top:${top}px;height:${height}px;border-left-color:${log.goal_color}">
                <div class="cal-block-title">${esc(log.task_title)}</div>
                <div class="cal-block-time">${fmtMin(dur)}</div>
            </div>
        `;
    });

    // Scheduled tasks with time
    tasks.forEach(t => {
        if (!t.start_time) return;
        const [h, m] = t.start_time.split(':').map(Number);
        const startMin = h * 60 + m;
        const dur = t.estimate_min || 60;
        const top = ((startMin - 360) / 60) * 60;
        const height = Math.max((dur / 60) * 60, 20);
        if (top < 0) return;
        const done = t.status === 'done';
        const td = encodeURIComponent(JSON.stringify({id:t.id,title:t.title,goal_emoji:t.goal_emoji,goal_title:t.goal_title,estimate_min:t.estimate_min,status:t.status}));
        blocksHtml += `
            <div class="cal-block ${done ? 'cal-block-done' : ''}" style="top:${top}px;height:${height}px;border-left-color:${t.goal_color || 'var(--burg-light)'}"
                 onclick="event.stopPropagation();openCalTaskModal('${td}')">
                <div class="cal-block-title">${t.goal_emoji || ''} ${esc(t.title)}</div>
                <div class="cal-block-time">${t.start_time.slice(0,5)} - ${fmtMin(dur)}</div>
            </div>
        `;
    });

    // iCal events
    ical.forEach(ev => {
        if (!ev.start || ev.all_day) return;
        const start = new Date(ev.start);
        const startMin = start.getHours() * 60 + start.getMinutes();
        const end = ev.end ? new Date(ev.end) : null;
        const dur = end ? (end - start) / 60000 : 60;
        const top = ((startMin - 360) / 60) * 60;
        const height = Math.max((dur / 60) * 60, 20);
        if (top < 0) return;
        blocksHtml += `
            <div class="cal-block cal-block-ical" style="top:${top}px;height:${height}px">
                <div class="cal-block-title">${esc(ev.title)}</div>
            </div>
        `;
    });

    // All tasks (unscheduled = no start_time)
    const unscheduled = tasks.filter(t => !t.start_time);
    const allTasks = tasks;

    // All-day iCal events
    const allDayEvents = ical.filter(ev => ev.all_day);

    // Helper to encode task for modal
    function taskData(t) {
        return encodeURIComponent(JSON.stringify({id:t.id,title:t.title,goal_emoji:t.goal_emoji,goal_title:t.goal_title,estimate_min:t.estimate_min,status:t.status}));
    }

    return `
        ${allDayEvents.length > 0 ? `
            <div class="cal-allday">
                ${allDayEvents.map(ev => `<div class="cal-allday-chip">${esc(ev.title)}</div>`).join('')}
            </div>
        ` : ''}
        ${unscheduled.length > 0 ? `
            <div class="cal-unscheduled">
                <div class="cal-unsched-title">Задачи</div>
                ${unscheduled.map(t => `
                    <div class="cal-unsched-item ${t.status === 'done' ? 'done' : ''}"
                         onclick="openCalTaskModal('${taskData(t)}')">
                        <span class="cal-unsched-dot" style="background:${t.goal_color || 'var(--burg-light)'}"></span>
                        ${t.goal_emoji || ''} ${esc(t.title)}
                        <span class="cal-unsched-est">${fmtMin(t.estimate_min)}</span>
                    </div>
                `).join('')}
            </div>
        ` : ''}
        <div class="cal-timeline" id="calTimeline" onclick="onTimelineClickGlobal(event)">
            <div class="cal-hours">
                ${hours.map(h => `
                    <div class="cal-hour-row">
                        <div class="cal-hour-label">${String(h).padStart(2,'0')}:00</div>
                        <div class="cal-hour-line"></div>
                    </div>
                `).join('')}
            </div>
            <div class="cal-blocks">${blocksHtml}</div>
            ${renderNowLine()}
        </div>
    `;
}

function renderNowLine() {
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);
    if (state.calDate !== todayStr) return '';
    const min = now.getHours() * 60 + now.getMinutes();
    const top = ((min - 360) / 60) * 60;
    if (top < 0) return '';
    return `<div class="cal-now-line" style="top:${top}px"><div class="cal-now-dot"></div></div>`;
}

function renderWeekView() {
    const data = state.calData;
    if (!data) return '';
    const start = new Date(data.start);
    const tasks = data.tasks || [];
    const logs = data.logs || [];

    // Group by day
    const days = [];
    for (let i = 0; i < 7; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        const ds = d.toISOString().slice(0, 10);
        const isToday = ds === new Date().toISOString().slice(0, 10);
        const dayTasks = tasks.filter(t => t.scheduled_date === ds);
        const dayLogs = logs.filter(l => l.started_at && l.started_at.slice(0, 10) === ds);
        const totalMin = dayLogs.reduce((s, l) => s + (l.duration_min || 0), 0);
        days.push({ date: d, ds, isToday, tasks: dayTasks, logs: dayLogs, totalMin });
    }

    return `
        <div class="week-grid">
            <div class="week-header">
                ${days.map(d => `
                    <div class="week-day-header ${d.isToday ? 'today' : ''}"
                         onclick="state.calDate='${d.ds}';setCalView('day')">
                        <div class="week-day-name">${DAYS_SHORT[d.date.getDay() === 0 ? 6 : d.date.getDay() - 1]}</div>
                        <div class="week-day-num">${d.date.getDate()}</div>
                    </div>
                `).join('')}
            </div>
            <div class="week-body">
                ${days.map(d => `
                    <div class="week-day-col ${d.isToday ? 'today' : ''}"
                         onclick="state.calDate='${d.ds}';setCalView('day')">
                        ${d.tasks.slice(0, 4).map(t => `
                            <div class="week-task-dot" style="background:${t.goal_color || 'var(--burg-light)'}">
                                <span class="week-task-text">${esc(t.title).slice(0, 12)}</span>
                            </div>
                        `).join('')}
                        ${d.tasks.length > 4 ? `<div class="week-more">+${d.tasks.length - 4}</div>` : ''}
                        ${d.totalMin > 0 ? `<div class="week-total">${fmtMin(d.totalMin)}</div>` : ''}
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function renderMonthView() {
    const data = state.calData;
    if (!data) return '';
    const start = new Date(data.start);
    const end = new Date(data.end);
    const tasks = data.tasks || [];
    const milestones = data.milestones || [];
    const todayStr = new Date().toISOString().slice(0, 10);

    // Build calendar grid
    const firstDay = new Date(start.getFullYear(), start.getMonth(), 1);
    let startWeekday = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1; // Monday = 0
    const daysInMonth = new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate();

    const cells = [];
    for (let i = 0; i < startWeekday; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
        const ds = `${start.getFullYear()}-${String(start.getMonth()+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        const dayTasks = tasks.filter(t => t.scheduled_date === ds);
        cells.push({ day: d, ds, isToday: ds === todayStr, tasks: dayTasks });
    }

    // Active milestones this month
    const monthMilestones = milestones.filter(m =>
        m.start_date <= data.end && m.end_date >= data.start
    );

    return `
        ${monthMilestones.length > 0 ? `
            <div class="month-milestones">
                ${monthMilestones.map(m => {
                    const mStart = new Date(m.start_date);
                    const mEnd = new Date(m.end_date);
                    const monthStart = new Date(data.start);
                    const monthEnd = new Date(data.end);
                    const visStart = mStart < monthStart ? monthStart : mStart;
                    const visEnd = mEnd > monthEnd ? monthEnd : mEnd;
                    const totalDays = (monthEnd - monthStart) / 86400000 + 1;
                    const left = Math.max(0, (visStart - monthStart) / 86400000) / totalDays * 100;
                    const width = ((visEnd - visStart) / 86400000 + 1) / totalDays * 100;
                    return `
                        <div class="month-ms-bar" style="left:${left}%;width:${width}%;background:${m.color}40;border-left:3px solid ${m.color}">
                            <span>${esc(m.title)}</span>
                        </div>
                    `;
                }).join('')}
            </div>
        ` : ''}
        <div class="month-grid">
            <div class="month-header">
                ${DAYS_SHORT.map(d => `<div class="month-hdr-cell">${d}</div>`).join('')}
            </div>
            <div class="month-body">
                ${cells.map(c => {
                    if (!c) return '<div class="month-cell empty"></div>';
                    return `
                        <div class="month-cell ${c.isToday ? 'today' : ''} ${c.tasks.length ? 'has-tasks' : ''}"
                             onclick="state.calDate='${c.ds}';setCalView('day')">
                            <div class="month-cell-num">${c.day}</div>
                            ${c.tasks.length > 0 ? `
                                <div class="month-cell-dots">
                                    ${c.tasks.slice(0, 3).map(t => `
                                        <div class="month-dot" style="background:${t.goal_color || 'var(--burg-light)'}"></div>
                                    `).join('')}
                                </div>
                            ` : ''}
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

function renderGanttView() {
    const milestones = state.milestones || [];
    if (!milestones.length) return '<div class="track-empty">Нет вех. Добавь через стратегию.</div>';

    const phases = {
        autopilot: { label: 'Автопилот агентства', color: '#8b5cf6' },
        freedom: { label: 'Финансовая свобода', color: '#dc2626' },
        media: { label: 'Медийный проект', color: '#D4A574' },
        learning: { label: 'Учёба', color: '#60D0E0' },
    };

    // Timeline: from earliest start to latest end
    const allDates = milestones.flatMap(m => [new Date(m.start_date), new Date(m.end_date)]);
    const minDate = new Date(Math.min(...allDates));
    const maxDate = new Date(Math.max(...allDates));
    const totalDays = (maxDate - minDate) / 86400000 + 1;
    const today = new Date();
    const todayPct = Math.max(0, Math.min(100, ((today - minDate) / 86400000) / totalDays * 100));

    // Month markers
    const months = [];
    let cursor = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
    while (cursor <= maxDate) {
        const pct = Math.max(0, (cursor - minDate) / 86400000 / totalDays * 100);
        months.push({ label: MONTHS_RU[cursor.getMonth()].slice(0, 3), pct });
        cursor.setMonth(cursor.getMonth() + 1);
    }

    // Group by phase
    const grouped = {};
    milestones.forEach(m => {
        if (!grouped[m.phase]) grouped[m.phase] = [];
        grouped[m.phase].push(m);
    });

    return `
        <div class="gantt-container">
            <div class="gantt-months">
                ${months.map(m => `<div class="gantt-month" style="left:${m.pct}%">${m.label}</div>`).join('')}
            </div>
            <div class="gantt-today" style="left:${todayPct}%">
                <div class="gantt-today-line"></div>
                <div class="gantt-today-label">Сегодня</div>
            </div>
            ${Object.entries(grouped).map(([phase, items]) => {
                const p = phases[phase] || { label: phase, color: '#888' };
                return `
                    <div class="gantt-phase">
                        <div class="gantt-phase-label" style="color:${p.color}">${p.label}</div>
                        ${items.map(m => {
                            const left = (new Date(m.start_date) - minDate) / 86400000 / totalDays * 100;
                            const width = ((new Date(m.end_date) - new Date(m.start_date)) / 86400000 + 1) / totalDays * 100;
                            const done = m.status === 'done';
                            return `
                                <div class="gantt-bar-wrap">
                                    <div class="gantt-bar ${done ? 'done' : ''}"
                                         onclick="openModal('editMilestone',${JSON.stringify(m).replace(/"/g,'&quot;')})"
                                         style="left:${left}%;width:${width}%;background:${m.color}50;border-left:3px solid ${m.color}">
                                        <span class="gantt-bar-text">${esc(m.title)}</span>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function renderBottomNav() {
    const items = [
        { key: 'timer', icon: '\u23F1', label: 'Время' },
        { key: 'track', icon: '\uD83D\uDCC5', label: 'Трек' },
        { key: 'plan', icon: '\uD83D\uDCCB', label: 'План' },
        { key: 'goals', icon: '\uD83C\uDFAF', label: 'Цели' },
        { key: 'stats', icon: '\uD83D\uDCCA', label: 'Стат' },
        { key: 'settings', icon: '\u2699\uFE0F', label: 'Сет' },
    ];
    return `<div class="bottom-nav">${items.map(i => `
        <div class="nav-item ${state.tab === i.key ? 'active' : ''}" data-tab="${i.key}">
            <span class="nav-icon">${i.icon}</span>
            ${i.label}
        </div>
    `).join('')}</div>`;
}

/* ═══ MODAL RENDERER ═══ */
function renderModal() {
    if (!state.modal) return '';
    const m = state.modal;

    let content = '';

    switch (m.type) {
        case 'addTask': {
            const goalOptions = (state.goals.length > 0 ? state.goals : state.workGoals)
                .map(g => `<option value="${g.id}">${esc(g.title)}</option>`).join('');
            content = `
                <h3>\uD83D\uDCDD Новая задача</h3>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" placeholder="Что нужно сделать?">
                </div>
                <div class="modal-field">
                    <label>Цель</label>
                    <select id="m_goal"><option value="">Без цели</option>${goalOptions}</select>
                </div>
                <div class="modal-field">
                    <label>Оценка (минуты)</label>
                    <input type="number" id="m_est" value="60" min="5" max="480" step="5">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-primary" onclick="submitAddTask()">Добавить</button>
                </div>
            `;
            break;
        }
        case 'payDebt': {
            content = `
                <h3>\uD83D\uDCB3 Внести платёж</h3>
                <div class="text-dim mb-12">${esc(m.title)}</div>
                <div class="modal-field">
                    <label>Сумма (\u20BD)</label>
                    <input type="number" id="m_amount" placeholder="10000" min="1">
                </div>
                <div class="modal-field">
                    <label>Заметка</label>
                    <input type="text" id="m_note" placeholder="Откуда оплата...">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-gold" onclick="submitPayDebt(${m.goalId})">Внести</button>
                </div>
            `;
            break;
        }
        case 'addSale': {
            content = `
                <h3>\uD83D\uDCB0 Новая продажа</h3>
                <div class="modal-field">
                    <label>Тип продукта</label>
                    <select id="m_product">
                        <option value="smm">SMM</option>
                        <option value="target">Таргет</option>
                        <option value="website">Сайт</option>
                        <option value="branding">Брендинг</option>
                        <option value="other">Другое</option>
                    </select>
                </div>
                <div class="modal-field">
                    <label>Выручка (\u20BD)</label>
                    <input type="number" id="m_revenue" placeholder="50000" min="0">
                </div>
                <div class="modal-field">
                    <label>Расходы (\u20BD)</label>
                    <input type="number" id="m_cost" placeholder="15000" min="0">
                </div>
                <div class="modal-field">
                    <label>Клиент</label>
                    <input type="text" id="m_client" placeholder="Имя клиента">
                </div>
                <div class="modal-field">
                    <label>Заметка</label>
                    <input type="text" id="m_note" placeholder="Детали...">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-green" onclick="submitAddSale()">Добавить</button>
                </div>
            `;
            break;
        }
        case 'addReward': {
            content = `
                <h3>\uD83C\uDF81 Новая награда</h3>
                <div class="modal-field">
                    <label>Эмодзи</label>
                    <input type="text" id="m_emoji" placeholder="\uD83C\uDF55" maxlength="4">
                </div>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" placeholder="Пицца / Кино / Выходной...">
                </div>
                <div class="modal-field">
                    <label>Стоимость (XP)</label>
                    <input type="number" id="m_cost" value="100" min="1">
                </div>
                <div class="modal-field">
                    <label>Категория</label>
                    <select id="m_cat">
                        <option value="food">Еда</option>
                        <option value="entertainment">Развлечения</option>
                        <option value="self-care">Забота</option>
                        <option value="purchase">Покупка</option>
                        <option value="other">Другое</option>
                    </select>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-primary" onclick="submitAddReward()">Добавить</button>
                </div>
            `;
            break;
        }
        case 'editReward': {
            content = `
                <h3>\u270F Редактировать награду</h3>
                <div class="modal-field">
                    <label>Эмодзи</label>
                    <input type="text" id="m_emoji" value="${esc(m.emoji || '')}" maxlength="4">
                </div>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" value="${esc(m.title || '')}">
                </div>
                <div class="modal-field">
                    <label>Стоимость (XP)</label>
                    <input type="number" id="m_cost" value="${m.cost_xp || 100}" min="1">
                </div>
                <div class="modal-field">
                    <label>Категория</label>
                    <input type="text" id="m_cat" value="${esc(m.category || '')}">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-danger btn-sm" onclick="if(confirm('Удалить?'))deleteReward(${m.id})">Удалить</button>
                    <button class="btn btn-primary" onclick="submitEditReward(${m.id})">Сохранить</button>
                </div>
            `;
            break;
        }
        case 'addGoal': {
            content = `
                <h3>\uD83C\uDFAF Новая цель</h3>
                <div class="modal-field">
                    <label>Эмодзи</label>
                    <input type="text" id="m_emoji" placeholder="\uD83D\uDE80" maxlength="4">
                </div>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" placeholder="Название цели">
                </div>
                <div class="modal-field">
                    <label>Описание</label>
                    <textarea id="m_desc" placeholder="Описание..."></textarea>
                </div>
                <div class="modal-field">
                    <label>Тип</label>
                    <select id="m_type">
                        <option value="work">Рабочая</option>
                        <option value="debt">Долг</option>
                    </select>
                </div>
                <div class="modal-field">
                    <label>Зона</label>
                    <select id="m_zone">
                        <option value="">Без зоны</option>
                        <option value="agency">Агентство</option>
                        <option value="debts">Долги</option>
                        <option value="goals">Цели</option>
                    </select>
                </div>
                <div class="modal-field">
                    <label>Целевая сумма (\u20BD, для долгов)</label>
                    <input type="number" id="m_target" value="0" min="0">
                </div>
                <div class="modal-field">
                    <label>Цвет</label>
                    <input type="text" id="m_color" placeholder="#D4364F" value="#D4364F">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-primary" onclick="submitAddGoal()">Создать</button>
                </div>
            `;
            break;
        }
        case 'editGoal': {
            content = `
                <h3>\u270F Редактировать цель</h3>
                <div class="modal-field">
                    <label>Эмодзи</label>
                    <input type="text" id="m_emoji" value="${esc(m.emoji || '')}" maxlength="4">
                </div>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" value="${esc(m.title || '')}">
                </div>
                <div class="modal-field">
                    <label>Цвет</label>
                    <input type="text" id="m_color" value="${esc(m.color || '#D4364F')}">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-danger btn-sm" onclick="if(confirm('Удалить цель?'))deleteGoal(${m.id})">Удалить</button>
                    <button class="btn btn-primary" onclick="submitEditGoal(${m.id})">Сохранить</button>
                </div>
            `;
            break;
        }
        case 'addCalTaskAtTime': {
            const goalOpts = (state.goals.length > 0 ? state.goals : state.workGoals)
                .map(g => `<option value="${g.id}">${g.emoji || ''} ${esc(g.title)}</option>`).join('');
            content = `
                <h3>Задача на ${m.time}</h3>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" placeholder="Что нужно сделать?">
                </div>
                <div class="modal-field">
                    <label>Цель</label>
                    <select id="m_goal"><option value="">Без цели</option>${goalOpts}</select>
                </div>
                <div class="modal-row">
                    <div class="modal-field" style="flex:1">
                        <label>Длительность</label>
                        <select id="m_est">
                            <option value="15">15 мин</option>
                            <option value="30">30 мин</option>
                            <option value="45">45 мин</option>
                            <option value="60" selected>1 час</option>
                            <option value="90">1.5 часа</option>
                            <option value="120">2 часа</option>
                        </select>
                    </div>
                    <div class="modal-field" style="flex:1">
                        <label>Приоритет</label>
                        <select id="m_priority">
                            <option value="1">Высокий</option>
                            <option value="2" selected>Средний</option>
                            <option value="3">Низкий</option>
                        </select>
                    </div>
                </div>
                <input type="hidden" id="m_date" value="${m.date}">
                <input type="hidden" id="m_time" value="${m.time}">
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-primary" onclick="submitAddCalTaskAtTime(false)">Добавить</button>
                    <button class="btn btn-green" onclick="submitAddCalTaskAtTime(true)">+ Фокус</button>
                </div>
            `;
            break;
        }
        case 'addCalTask': {
            const goalOptions = (state.goals.length > 0 ? state.goals : state.workGoals)
                .map(g => `<option value="${g.id}">${g.emoji || ''} ${esc(g.title)}</option>`).join('');
            content = `
                <h3>Новая задача</h3>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" placeholder="Что нужно сделать?">
                </div>
                <div class="modal-field">
                    <label>Дата</label>
                    <input type="date" id="m_date" value="${m.date || state.calDate}">
                </div>
                <div class="modal-field">
                    <label>Цель</label>
                    <select id="m_goal"><option value="">Без цели</option>${goalOptions}</select>
                </div>
                <div class="modal-field">
                    <label>Оценка (мин)</label>
                    <input type="number" id="m_est" value="60" min="5" max="480" step="5">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-primary" onclick="submitAddCalTask()">Добавить</button>
                </div>
            `;
            break;
        }
        case 'addMilestone': {
            content = `
                <h3>Новая веха</h3>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" placeholder="Название вехи">
                </div>
                <div class="modal-field">
                    <label>Фаза</label>
                    <select id="m_phase">
                        <option value="autopilot">Автопилот агентства</option>
                        <option value="freedom">Финансовая свобода</option>
                        <option value="media">Медийный проект</option>
                        <option value="learning">Учёба</option>
                    </select>
                </div>
                <div class="modal-field">
                    <label>Начало</label>
                    <input type="date" id="m_start">
                </div>
                <div class="modal-field">
                    <label>Конец</label>
                    <input type="date" id="m_end">
                </div>
                <div class="modal-field">
                    <label>Цвет</label>
                    <input type="color" id="m_color" value="#8B0020">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-primary" onclick="submitAddMilestone()">Добавить</button>
                </div>
            `;
            break;
        }
        case 'editMilestone': {
            const statusOptions = [
                { value: 'todo', label: 'Todo' },
                { value: 'in_progress', label: 'В работе' },
                { value: 'done', label: 'Готово' },
            ];
            content = `
                <h3>Веха: ${esc(m.title)}</h3>
                <div class="modal-field">
                    <label>Название</label>
                    <input type="text" id="m_title" value="${esc(m.title || '')}">
                </div>
                <div class="modal-field">
                    <label>Начало</label>
                    <input type="date" id="m_start" value="${m.start_date || ''}">
                </div>
                <div class="modal-field">
                    <label>Конец</label>
                    <input type="date" id="m_end" value="${m.end_date || ''}">
                </div>
                <div class="modal-field">
                    <label>Статус</label>
                    <select id="m_status">
                        ${statusOptions.map(s => `<option value="${s.value}" ${m.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}
                    </select>
                </div>
                <div class="modal-field">
                    <label>Цвет</label>
                    <input type="color" id="m_color" value="${m.color || '#8B0020'}">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    <button class="btn btn-danger btn-sm" onclick="if(confirm('Удалить веху?'))deleteMilestoneAction(${m.id})">Удалить</button>
                    <button class="btn btn-primary" onclick="submitEditMilestone(${m.id})">Сохранить</button>
                </div>
            `;
            break;
        }
        case 'calTask': {
            const t = m.task;
            const isActive = state.active && state.active.task_id === t.id;
            content = `
                <h3>${t.goal_emoji || ''} ${esc(t.title)}</h3>
                <div class="text-dim mb-12">${t.goal_title || 'Без цели'} &middot; ${fmtMin(t.estimate_min)}</div>
                <div class="modal-actions" style="flex-wrap:wrap;gap:8px">
                    ${t.status === 'done'
                        ? '<span class="text-green" style="font-size:14px">Выполнено</span>'
                        : isActive
                            ? `<button class="btn btn-stop" onclick="stopTimer();closeModal();loadTrackTab()">Стоп</button>`
                            : `<button class="btn btn-green" style="flex:1" onclick="startTimer(${t.id});closeModal();loadTrackTab();api('/api/notify','POST',{text:'▶️ Фокус: ${esc(t.title)}'})">
                                Фокус
                               </button>`
                    }
                    ${t.status !== 'done' ? `<button class="btn btn-primary" style="flex:1" onclick="completeTask(${t.id});closeModal();loadTrackTab()">Готово</button>` : ''}
                    <button class="btn btn-secondary" style="flex:1" onclick="closeModal()">Закрыть</button>
                </div>
            `;
            break;
        }
        default:
            content = '<h3>Modal</h3>';
    }

    return `
        <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
            <div class="modal-sheet" onclick="event.stopPropagation()">
                ${content}
            </div>
        </div>
    `;
}

/* ═══ MODAL SUBMIT HANDLERS ═══ */
async function submitEditMilestone(mid) {
    const title = (document.getElementById('m_title')?.value || '').trim();
    const start_date = document.getElementById('m_start')?.value;
    const end_date = document.getElementById('m_end')?.value;
    const status = document.getElementById('m_status')?.value;
    const color = document.getElementById('m_color')?.value;
    if (!title || !start_date || !end_date) return;
    await api(`/api/milestones/${mid}`, 'PUT', { title, start_date, end_date, status, color });
    closeModal();
    state.calData = null;
    loadTrackTab();
}

async function deleteMilestoneAction(mid) {
    await api(`/api/milestones/${mid}`, 'DELETE');
    closeModal();
    state.calData = null;
    loadTrackTab();
}

function onTimelineClickGlobal(event) {
    // Ignore clicks on task blocks
    if (event.target.closest('.cal-block')) return;
    const timeline = document.getElementById('calTimeline');
    if (!timeline) return;
    const rect = timeline.getBoundingClientRect();
    const y = event.clientY - rect.top;
    // Each hour = 60px, starts at hour 6
    const totalMinutes = Math.round((y / 60) * 60) + 360; // 360 = 6*60
    const hour = Math.floor(totalMinutes / 60);
    const min = Math.round((totalMinutes % 60) / 15) * 15; // snap 15min
    if (hour < 6 || hour > 23) return;
    const timeStr = `${String(hour).padStart(2,'0')}:${String(min === 60 ? 0 : min).padStart(2,'0')}`;
    openModal('addCalTaskAtTime', { date: state.calDate, time: timeStr });
}

function openTrackAddModal() {
    if (state.calView === 'gantt') {
        openModal('addMilestone', {});
    } else {
        openModal('addCalTask', { date: state.calDate });
    }
}

async function submitAddCalTaskAtTime(startFocus) {
    const title = (document.getElementById('m_title')?.value || '').trim();
    if (!title) return;
    const goalId = document.getElementById('m_goal')?.value ? parseInt(document.getElementById('m_goal').value) : null;
    const est = parseInt(document.getElementById('m_est')?.value) || 60;
    const priority = parseInt(document.getElementById('m_priority')?.value) || 2;
    const date = document.getElementById('m_date')?.value || state.calDate;
    const time = document.getElementById('m_time')?.value;
    const body = { title, estimate_min: est, scheduled_date: date, priority };
    if (goalId) body.goal_id = goalId;
    if (time) body.start_time = time;
    const res = await api('/api/tasks/add', 'POST', body);
    if (res && res.ok) {
        // Send notification to bot
        await api('/api/notify', 'POST', { text: `📋 Новая задача: ${title} (${time || 'без времени'})` });
        if (startFocus) {
            await api(`/api/timer/start/${res.task_id}`, 'POST');
            showToast('Фокус запущен!');
        }
        closeModal();
        state.calData = null;
        await loadTrackTab();
        if (startFocus) await loadAll();
    }
}

async function submitAddCalTask() {
    const title = (document.getElementById('m_title')?.value || '').trim();
    if (!title) return;
    const goalId = document.getElementById('m_goal')?.value ? parseInt(document.getElementById('m_goal').value) : null;
    const est = parseInt(document.getElementById('m_est')?.value) || 60;
    const date = document.getElementById('m_date')?.value || state.calDate;
    const body = { title, estimate_min: est, scheduled_date: date };
    if (goalId) body.goal_id = goalId;
    const res = await api('/api/tasks/add', 'POST', body);
    if (res && res.ok) {
        closeModal();
        state.calData = null;
        loadTrackTab();
    }
}

async function submitAddMilestone() {
    const title = (document.getElementById('m_title')?.value || '').trim();
    const phase = document.getElementById('m_phase')?.value || 'autopilot';
    const start_date = document.getElementById('m_start')?.value;
    const end_date = document.getElementById('m_end')?.value;
    const color = document.getElementById('m_color')?.value || '#8B0020';
    if (!title || !start_date || !end_date) return;
    await api('/api/milestones', 'POST', { title, phase, start_date, end_date, color });
    closeModal();
    state.calData = null;
    loadTrackTab();
}

function openCalTaskModal(taskJson) {
    const task = JSON.parse(decodeURIComponent(taskJson));
    openModal('calTask', { task });
}

function submitAddTask() {
    const title = (document.getElementById('m_title')?.value || '').trim();
    if (!title) return;
    const goalId = document.getElementById('m_goal')?.value ? parseInt(document.getElementById('m_goal').value) : null;
    const est = parseInt(document.getElementById('m_est')?.value) || 60;
    addTask(title, goalId, est);
}

function submitPayDebt(goalId) {
    const amount = parseFloat(document.getElementById('m_amount')?.value);
    if (!amount || amount <= 0) return;
    const note = (document.getElementById('m_note')?.value || '').trim();
    payDebt(goalId, amount, note);
}

function submitAddSale() {
    const product = document.getElementById('m_product')?.value || 'other';
    const revenue = parseFloat(document.getElementById('m_revenue')?.value) || 0;
    const cost = parseFloat(document.getElementById('m_cost')?.value) || 0;
    const client = (document.getElementById('m_client')?.value || '').trim();
    const note = (document.getElementById('m_note')?.value || '').trim();
    addSale(product, revenue, cost, client, note);
}

function submitAddReward() {
    const emoji = (document.getElementById('m_emoji')?.value || '').trim() || '\uD83C\uDF81';
    const title = (document.getElementById('m_title')?.value || '').trim();
    if (!title) return;
    const cost = parseInt(document.getElementById('m_cost')?.value) || 100;
    const cat = document.getElementById('m_cat')?.value || 'other';
    addReward(title, emoji, cost, cat);
}

function submitEditReward(id) {
    const emoji = (document.getElementById('m_emoji')?.value || '').trim() || '\uD83C\uDF81';
    const title = (document.getElementById('m_title')?.value || '').trim();
    if (!title) return;
    const cost = parseInt(document.getElementById('m_cost')?.value) || 100;
    const cat = (document.getElementById('m_cat')?.value || '').trim();
    editReward(id, title, emoji, cost, cat);
}

function submitAddGoal() {
    const emoji = (document.getElementById('m_emoji')?.value || '').trim() || '\uD83C\uDFAF';
    const title = (document.getElementById('m_title')?.value || '').trim();
    if (!title) return;
    const desc = (document.getElementById('m_desc')?.value || '').trim();
    const type = document.getElementById('m_type')?.value || 'work';
    const zone = document.getElementById('m_zone')?.value || '';
    const target = parseFloat(document.getElementById('m_target')?.value) || 0;
    const color = (document.getElementById('m_color')?.value || '').trim() || '#D4364F';
    addGoal(title, desc, type, zone, target, emoji, color);
}

function submitEditGoal(id) {
    const emoji = (document.getElementById('m_emoji')?.value || '').trim();
    const title = (document.getElementById('m_title')?.value || '').trim();
    if (!title) return;
    const color = (document.getElementById('m_color')?.value || '').trim();
    editGoal(id, title, emoji, color);
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
                labels: daily.map(d => d.day ? d.day.slice(5) : ''),
                datasets: [{
                    data: daily.map(d => +(d.total_min / 60).toFixed(1)),
                    backgroundColor: daily.map(d =>
                        d.total_min >= 240 ? 'rgba(94, 224, 160, 0.5)' :
                        d.total_min >= 120 ? 'rgba(212, 165, 116, 0.4)' :
                        'rgba(212, 54, 79, 0.3)'
                    ),
                    borderRadius: 4,
                    barThickness: 10,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: ctx => ctx.raw + 'ч' } }
                },
                scales: {
                    y: {
                        beginAtZero: true, max: 6,
                        grid: { color: 'rgba(255,248,240,0.03)' },
                        ticks: { color: '#6B5545', callback: v => v + 'ч', font: { family: 'JetBrains Mono', size: 10 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#6B5545', font: { family: 'JetBrains Mono', size: 9 }, maxRotation: 45 }
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
                    backgroundColor: byGoal.map(g => g.color || '#8B0020'),
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
                    tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.raw + 'ч' } }
                }
            }
        });
    }
}

/* ═══ EVENT BINDING ═══ */
function bindEvents() {
    document.querySelectorAll('[data-tab]').forEach(el => {
        el.onclick = () => {
            const newTab = el.dataset.tab;
            if (state.tab === newTab) return;
            state.tab = newTab;
            render();
            // lazy-load tab-specific data
            if (newTab === 'goals') loadGoalsTab();
            if (newTab === 'rewards') loadRewardsTab();
            if (newTab === 'settings') loadSettingsTab();
            if (newTab === 'stats') loadAll();
            if (newTab === 'track') loadTrackTab();
        };
    });

    // Enter key support in modals
    document.querySelectorAll('.modal-sheet input').forEach(inp => {
        inp.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                const btn = document.querySelector('.modal-actions .btn-primary, .modal-actions .btn-gold, .modal-actions .btn-green');
                if (btn) btn.click();
            }
        });
    });
}

/* ═══ LIVE TIMER TICK ═══ */
let tickInterval;
function startLiveTick() {
    clearInterval(tickInterval);
    tickInterval = setInterval(() => {
        if (!state.active) return;

        const elapsed = Math.max(0, (Date.now() - new Date(state.active.started_at).getTime()) / 60000);

        // Update active task elapsed display
        const elEl = document.getElementById('activeElapsed');
        if (elEl) elEl.textContent = fmtMin(elapsed);

        // Update HUD digits
        const alreadyCounted = state.active.already_counted || 0;
        const totalNow = Math.max(0, state.todayMin + elapsed - alreadyCounted);
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

/* ═══ INIT ═══ */
document.addEventListener('DOMContentLoaded', () => {
    loadAll();
    startLiveTick();
    // Auto-refresh every 60s
    setInterval(loadAll, 60000);
});
