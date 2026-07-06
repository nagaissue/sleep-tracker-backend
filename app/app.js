/**
 * app.js — Sleep Tracker フロントエンド（ローカルストレージ版）
 *
 * - Web Speech API による音声入力 / テキスト入力
 * - /api/parse   → Gemini 2.5 Flash でテキストを解析
 * - /api/analyze → Gemini 2.5 Flash で睡眠データを分析
 * - データの保存・統計計算はすべてブラウザの localStorage で完結（Google Calendar API は廃止済み）
 *
 * カラー定義はモバイルアプリ（lib/theme.ts）と統一：
 *   就寝 = 紺色 #1e3a8a / 起床 = オレンジと黄色の中間色 #f97316 / 昼寝 = 青色 #3b82f6
 */

'use strict';

const API_BASE = ''; // 同一オリジン（Vercel）
const STORAGE_KEY = 'sleep_tracker_records';
const ANALYSIS_PERIOD_DAYS = 30;
const WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'];
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
const DEFAULT_SLEEP_DURATION_MIN = 480; // 就寝のみの場合のデフォルト8時間
const DEFAULT_NAP_DURATION_MIN = 30;    // 昼寝のデフォルト

const COLOR_MAP = {
  '就寝': '#1e3a8a',
  '起床': '#f97316',
  '昼寝': '#3b82f6',
};

let parsedEvents = [];
let recognition  = null;
let isRecording   = false;

// カレンダー状態
const today = new Date();
let calYear  = today.getFullYear();
let calMonth = today.getMonth();
let selectedDay = null;

document.addEventListener('DOMContentLoaded', () => {
  initSpeechRecognition();
  initTabs();
  renderCalendar();
  loadDashboard();
});

// ══════════════════════ タブ切り替え ══════════════════════
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');

      if (btn.dataset.tab === 'calendar') renderCalendar();
      if (btn.dataset.tab === 'stats') loadDashboard();
    });
  });
}

// ══════════════════════ ローカルストレージ ══════════════════════
function getAllRecords() {
  const raw = localStorage.getItem(STORAGE_KEY);
  const records = raw ? JSON.parse(raw) : [];
  return records.sort((a, b) => a.datetime.localeCompare(b.datetime));
}

function getRecentRecords(days) {
  const all = getAllRecords();
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return all.filter((r) => new Date(r.datetime) >= cutoff);
}

function getMonthRecords(year, month) {
  const all = getAllRecords();
  return all.filter((r) => {
    const dt = new Date(r.datetime);
    return dt.getFullYear() === year && dt.getMonth() === month;
  });
}

function saveRecordsToStorage(events) {
  const existing = getAllRecords();
  const now = new Date().toISOString();
  const newRecords = events.map((ev, idx) => ({
    ...ev,
    id: `${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
    created_at: now,
  }));
  const updated = [...existing, ...newRecords];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  return newRecords;
}

function deleteRecordFromStorage(id) {
  const all = getAllRecords();
  const filtered = all.filter((r) => r.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
}

// ══════════════════════ Web Speech API ══════════════════════
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    const btn = document.getElementById('btn-mic');
    btn.textContent = '⚠ 音声入力非対応';
    btn.disabled = true;
    return;
  }
  recognition = new SpeechRecognition();
  recognition.lang = 'ja-JP';
  recognition.continuous = false;
  recognition.interimResults = true;

  recognition.onresult = (e) => {
    const transcript = Array.from(e.results).map((r) => r[0].transcript).join('');
    showTranscript(transcript);
    if (e.results[e.results.length - 1].isFinal) {
      stopRecording();
      parseText(transcript);
    }
  };
  recognition.onerror = (e) => {
    stopRecording();
    showStatus(`音声認識エラー: ${e.error}`, 'error');
  };
  recognition.onend = () => stopRecording();
}

function toggleRecording() {
  isRecording ? stopRecording() : startRecording();
}

function startRecording() {
  if (!recognition) return;
  isRecording = true;
  recognition.start();
  const btn = document.getElementById('btn-mic');
  btn.textContent = '⏹ 停止';
  btn.classList.add('recording');
  showTranscript('');
}

function stopRecording() {
  if (!recognition) return;
  isRecording = false;
  try { recognition.stop(); } catch (_) {}
  const btn = document.getElementById('btn-mic');
  btn.textContent = '🎤 音声入力開始';
  btn.classList.remove('recording');
}

function showTranscript(text) {
  const box = document.getElementById('transcript-box');
  document.getElementById('transcript-text').textContent = text;
  box.classList.toggle('hidden', !text);
}

function handleTextParse() {
  const input = document.getElementById('text-input');
  const text = input.value.trim();
  if (!text) return;
  parseText(text);
  input.value = '';
}

// ══════════════════════ API: テキスト解析 ══════════════════════
async function parseText(text) {
  showStatus('Gemini 2.5 Flash で解析中...', 'info');
  try {
    const res = await fetch(`${API_BASE}/api/parse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Parse error');
    parsedEvents = data.events || [];
    renderPreview(parsedEvents);
    hideStatus();
  } catch (err) {
    showStatus(`解析エラー: ${err.message}`, 'error');
  }
}

function renderPreview(events) {
  const section = document.getElementById('preview-section');
  const container = document.getElementById('events-preview');
  container.innerHTML = '';

  if (!events.length) {
    showStatus('イベントを検出できませんでした。もう一度お試しください。', 'error');
    return;
  }

  events.forEach((ev) => {
    const dt = new Date(ev.datetime);
    const chip = document.createElement('div');
    chip.className = 'event-chip';
    chip.style.background = `${COLOR_MAP[ev.type] || '#e1e1e1'}22`;
    chip.innerHTML = `
      <span class="dot" style="background:${COLOR_MAP[ev.type] || '#e1e1e1'}"></span>
      <span class="ev-type">${ev.type}</span>
      <span class="ev-time">${formatDt(dt)}${ev.duration_min ? `　(${ev.duration_min}分)` : ''}</span>
    `;
    container.appendChild(chip);
  });

  section.classList.remove('hidden');
}

function clearPreview() {
  document.getElementById('preview-section').classList.add('hidden');
  parsedEvents = [];
  showTranscript('');
}

// ══════════════════════ ローカル保存 ══════════════════════
function saveEvents() {
  if (parsedEvents.length === 0) return;
  const saved = saveRecordsToStorage(
    parsedEvents.map((ev) => ({
      type: ev.type,
      datetime: ev.datetime,
      duration_min: ev.duration_min ?? null,
    }))
  );
  showStatus(`✅ ${saved.length}件の記録を保存しました！`, 'success');
  clearPreview();
  renderCalendar();
  loadDashboard();
}

// ══════════════════════ カレンダー ══════════════════════
function changeMonth(delta) {
  calMonth += delta;
  if (calMonth < 0) { calMonth = 11; calYear--; }
  if (calMonth > 11) { calMonth = 0; calYear++; }
  selectedDay = null;
  renderCalendar();
}

function renderCalendar() {
  document.getElementById('month-label').textContent = `${calYear}年 ${MONTHS[calMonth]}`;

  const records = getMonthRecords(calYear, calMonth);
  const recordsByDay = {};
  for (const r of records) {
    const dt = new Date(r.datetime);
    if (dt.getFullYear() === calYear && dt.getMonth() === calMonth) {
      const day = dt.getDate();
      if (!recordsByDay[day]) recordsByDay[day] = [];
      recordsByDay[day].push(r);
    }
  }

  const firstDay = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();

  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const grid = document.getElementById('calendar-grid');
  grid.innerHTML = '';

  const now = new Date();
  const isToday = (day) =>
    now.getFullYear() === calYear && now.getMonth() === calMonth && now.getDate() === day;

  cells.forEach((day) => {
    const cell = document.createElement('div');
    cell.className = 'day-cell';
    if (day === null) {
      cell.classList.add('empty');
      grid.appendChild(cell);
      return;
    }
    if (isToday(day)) cell.classList.add('today');
    if (selectedDay === day) cell.classList.add('selected');

    const dayNum = document.createElement('span');
    dayNum.className = 'day-num';
    dayNum.textContent = day;
    cell.appendChild(dayNum);

    const dayRecords = recordsByDay[day] || [];
    const types = Array.from(new Set(dayRecords.map((r) => r.type)));
    if (types.length > 0) {
      const dotsRow = document.createElement('div');
      dotsRow.className = 'dots-row';
      types.slice(0, 3).forEach((t) => {
        const dot = document.createElement('span');
        dot.className = 'day-dot';
        dot.style.background = COLOR_MAP[t] || '#999';
        dotsRow.appendChild(dot);
      });
      cell.appendChild(dotsRow);
    }

    cell.addEventListener('click', () => {
      selectedDay = day;
      renderCalendar();
      renderDayDetail(day, recordsByDay[day] || []);
    });

    grid.appendChild(cell);
  });

  document.getElementById('month-record-count').textContent =
    `${MONTHS[calMonth]}の記録: ${records.length}件`;

  if (selectedDay !== null) {
    renderDayDetail(selectedDay, recordsByDay[selectedDay] || []);
  } else {
    document.getElementById('day-detail').classList.add('hidden');
  }
}

function renderDayDetail(day, records) {
  const section = document.getElementById('day-detail');
  const title = document.getElementById('day-detail-title');
  const content = document.getElementById('day-detail-content');

  title.textContent = `${calYear}年${calMonth + 1}月${day}日の記録`;
  content.innerHTML = '';

  if (records.length === 0) {
    content.innerHTML = '<p class="hint">この日の記録はありません</p>';
  } else {
    records
      .sort((a, b) => a.datetime.localeCompare(b.datetime))
      .forEach((r) => {
        const dt = new Date(r.datetime);
        const row = document.createElement('div');
        row.className = 'detail-row';
        row.innerHTML = `
          <span class="dot" style="background:${COLOR_MAP[r.type] || '#999'}"></span>
          <span class="ev-type">${r.type}</span>
          <span class="ev-time">${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}${r.duration_min ? `　(${r.duration_min}分)` : ''}</span>
          <button class="delete-btn" title="削除">✕</button>
        `;
        row.querySelector('.delete-btn').addEventListener('click', () => {
          if (confirm(`${r.type} — ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')} の記録を削除しますか？`)) {
            deleteRecordFromStorage(r.id);
            renderCalendar();
            loadDashboard();
          }
        });
        content.appendChild(row);
      });
  }

  section.classList.remove('hidden');
}

// ══════════════════════ 統計計算（ローカル） ══════════════════════
function buildSleepSessions(records) {
  const sleepEvents = records.filter((r) => r.type === '就寝').sort((a, b) => a.datetime.localeCompare(b.datetime));
  const wakeEvents  = records.filter((r) => r.type === '起床').sort((a, b) => a.datetime.localeCompare(b.datetime));

  const sessions = [];
  for (const sleep of sleepEvents) {
    const sDt = new Date(sleep.datetime);
    let matchedWake = null;
    for (const wake of wakeEvents) {
      const wDt = new Date(wake.datetime);
      const diffHours = (wDt.getTime() - sDt.getTime()) / 3600000;
      if (diffHours >= 0 && diffHours <= 14) {
        if (!matchedWake || wDt < matchedWake) matchedWake = wDt;
      }
    }
    const hours = matchedWake
      ? (matchedWake.getTime() - sDt.getTime()) / 3600000
      : DEFAULT_SLEEP_DURATION_MIN / 60;

    sessions.push({
      date: `${String(sDt.getMonth() + 1).padStart(2, '0')}/${String(sDt.getDate()).padStart(2, '0')}`,
      hours: Math.round(hours * 10) / 10,
      weekday: WEEKDAYS[sDt.getDay()],
    });
  }
  return sessions.sort((a, b) => a.date.localeCompare(b.date));
}

function avgTimeStr(datetimes) {
  if (datetimes.length === 0) return null;
  const minutes = datetimes.map((dt) => {
    const d = new Date(dt);
    return d.getHours() * 60 + d.getMinutes();
  });
  const avgMin = Math.round(minutes.reduce((a, b) => a + b, 0) / minutes.length);
  return `${String(Math.floor(avgMin / 60)).padStart(2, '0')}:${String(avgMin % 60).padStart(2, '0')}`;
}

function computeStats(days) {
  const records = getRecentRecords(days);
  const sleepEvents = records.filter((r) => r.type === '就寝');
  const wakeEvents  = records.filter((r) => r.type === '起床');
  const napEvents   = records.filter((r) => r.type === '昼寝');

  const sessions = buildSleepSessions(records);
  const sleepDurations = sessions.map((s) => s.hours);
  const avgSleepHours = sleepDurations.length > 0
    ? Math.round((sleepDurations.reduce((a, b) => a + b, 0) / sleepDurations.length) * 10) / 10
    : null;

  let napTotalMin = 0;
  for (const nap of napEvents) {
    napTotalMin += nap.duration_min || DEFAULT_NAP_DURATION_MIN;
  }

  return {
    total_records: records.length,
    sleep_sessions: sessions.length,
    avg_sleep_hours: avgSleepHours,
    avg_bedtime: avgTimeStr(sleepEvents.map((e) => e.datetime)),
    avg_waketime: avgTimeStr(wakeEvents.map((e) => e.datetime)),
    nap_count: napEvents.length,
    nap_total_min: napTotalMin,
    sleep_sessions_detail: sessions,
  };
}

function loadDashboard() {
  const loadingEl = document.getElementById('dashboard-loading');
  const contentEl = document.getElementById('dashboard-content');
  const emptyEl   = document.getElementById('stat-empty');

  loadingEl.classList.remove('hidden');
  contentEl.classList.add('hidden');

  const data = computeStats(7);

  document.getElementById('stat-avg').textContent = data.avg_sleep_hours != null ? data.avg_sleep_hours : '--';
  document.getElementById('stat-nap').textContent = data.nap_count ?? '--';
  document.getElementById('stat-bedtime').textContent  = data.avg_bedtime  || '--';
  document.getElementById('stat-waketime').textContent = data.avg_waketime || '--';

  const sessions = data.sleep_sessions_detail || [];
  emptyEl.classList.toggle('hidden', sessions.length > 0);
  renderChart(sessions);

  loadingEl.classList.add('hidden');
  contentEl.classList.remove('hidden');
}

let sleepChart = null;

function renderChart(sessions) {
  const ctx = document.getElementById('sleep-chart').getContext('2d');
  if (sleepChart) sleepChart.destroy();
  if (!sessions.length) return;

  const labels = sessions.map((s) => `${s.date}(${s.weekday})`);
  const hours  = sessions.map((s) => s.hours);

  sleepChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '睡眠時間（時間）',
        data: hours,
        backgroundColor: '#1e3a8a',
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, max: 12, ticks: { stepSize: 2 } } },
    },
  });
}

// ══════════════════════ API: AI睡眠分析 ══════════════════════
async function runAnalysis() {
  const btn = document.getElementById('btn-analyze');
  const loadingEl = document.getElementById('analysis-loading');
  const errorEl   = document.getElementById('analysis-error');
  const resultEl  = document.getElementById('analysis-result');

  errorEl.classList.add('hidden');
  resultEl.classList.add('hidden');
  loadingEl.classList.remove('hidden');
  btn.disabled = true;

  try {
    const records = getRecentRecords(ANALYSIS_PERIOD_DAYS);
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        records: records.map((r) => ({ type: r.type, datetime: r.datetime })),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Analyze error');

    document.getElementById('analysis-consistency').textContent =
      data.metrics?.sleep_consistency_score ?? '--';
    document.getElementById('analysis-debt').textContent =
      data.metrics?.sleep_debt_hours ?? '--';
    document.getElementById('analysis-summary').textContent = data.summary || '';

    const insightsEl = document.getElementById('analysis-insights');
    insightsEl.innerHTML = '';
    (data.insights || []).forEach((text) => {
      const li = document.createElement('li');
      li.textContent = text;
      insightsEl.appendChild(li);
    });

    const recEl = document.getElementById('analysis-recommendations');
    recEl.innerHTML = '';
    (data.recommendations || []).forEach((text) => {
      const li = document.createElement('li');
      li.textContent = text;
      recEl.appendChild(li);
    });

    resultEl.classList.remove('hidden');
  } catch (err) {
    errorEl.textContent = `分析エラー: ${err.message}`;
    errorEl.classList.remove('hidden');
  } finally {
    loadingEl.classList.add('hidden');
    btn.disabled = false;
  }
}

// ══════════════════════ ユーティリティ ══════════════════════
function formatDt(dt) {
  const M = dt.getMonth() + 1, D = dt.getDate();
  const H = String(dt.getHours()).padStart(2, '0');
  const m = String(dt.getMinutes()).padStart(2, '0');
  return `${M}/${D} ${H}:${m}`;
}

function showStatus(msg, type = 'info') {
  const el = document.getElementById('status-msg');
  el.textContent = msg;
  el.className = `status-msg ${type}`;
  el.classList.remove('hidden');
}

function hideStatus() {
  document.getElementById('status-msg').classList.add('hidden');
}
