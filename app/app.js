/**
 * app.js — Sleep Tracker フロントエンド（認証レス版）
 * - Web Speech API による音声入力
 * - /api/parse  → Gemini 2.5 Flash NLP
 * - /api/calendar → Google Calendar 登録（サーバー側で認証完結）
 * - /api/stats → 睡眠統計ダッシュボード
 *
 * フロントエンドはトークンや認証を一切保持しない。
 */

'use strict';

const API_BASE = '';   // 同一オリジン（Vercel）

const COLOR_MAP = {
  '就寝': '#5484ed',
  '起床': '#ffb878',
  '昼寝': '#a4bdfc',
};

let parsedEvents = [];
let recognition  = null;
let isRecording   = false;

document.addEventListener('DOMContentLoaded', () => {
  initSpeechRecognition();
  loadDashboard();
});

// ── Web Speech API ────────────────────────────────────────
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
    const transcript = Array.from(e.results).map(r => r[0].transcript).join('');
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

// ── API: テキスト解析 ─────────────────────────────────────
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

  // 就寝と起床のペアリング表示
  const sleepEv = events.find(e => e.type === '就寝');
  const wakeEv  = events.find(e => e.type === '起床');
  const napEv   = events.find(e => e.type === '昼寝');

  if (sleepEv && wakeEv) {
    // ペア表示：就寝→起床の睡眠時間を計算
    const sDt = new Date(sleepEv.datetime);
    const wDt = new Date(wakeEv.datetime);
    const hours = ((wDt - sDt) / 3600000).toFixed(1);
    const chip = document.createElement('div');
    chip.className = 'event-chip';
    chip.style.background = `${COLOR_MAP['就寝']}22`;
    chip.innerHTML = `
      <span class="dot" style="background:${COLOR_MAP['就寝']}"></span>
      <span class="ev-type">就寝→起床</span>
      <span class="ev-time">${formatDt(sDt)} 〜 ${formatDt(wDt)}　(${hours}h)</span>
    `;
    container.appendChild(chip);
  } else {
    // 個別表示
    events.forEach(ev => {
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
  }

  section.classList.remove('hidden');
}

function clearPreview() {
  document.getElementById('preview-section').classList.add('hidden');
  parsedEvents = [];
  showTranscript('');
}

// ── API: カレンダー登録（認証レス） ────────────────────────
async function registerToCalendar() {
  if (parsedEvents.length === 0) return;
  showStatus('Googleカレンダーに登録中...', 'info');
  try {
    const res = await fetch(`${API_BASE}/api/calendar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events: parsedEvents }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Calendar error');

    const count = data.created.length;
    showStatus(`✅ ${count}件のイベントをカレンダーに登録しました！`, 'success');
    clearPreview();
    loadDashboard();
  } catch (err) {
    showStatus(`登録エラー: ${err.message}`, 'error');
  }
}

// ── API: 睡眠統計ダッシュボード（認証レス） ────────────────
async function loadDashboard() {
  const loadingEl = document.getElementById('dashboard-loading');
  const contentEl = document.getElementById('dashboard-content');

  loadingEl.classList.remove('hidden');
  contentEl.classList.add('hidden');

  try {
    const res = await fetch(`${API_BASE}/api/stats?days=7`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);

    document.getElementById('stat-avg').textContent =
      data.avg_sleep_hours != null ? data.avg_sleep_hours : '--';
    document.getElementById('stat-nap').textContent = data.nap_count ?? '--';
    document.getElementById('stat-bedtime').textContent  = data.avg_bedtime  || '--';
    document.getElementById('stat-waketime').textContent = data.avg_waketime || '--';

    // 日付ラベル付きセッションデータでチャート描画
    const sessions = data.sleep_sessions_detail || [];
    renderChart(sessions);

    loadingEl.classList.add('hidden');
    contentEl.classList.remove('hidden');
  } catch (err) {
    loadingEl.textContent = `統計読み込みエラー: ${err.message}`;
  }
}

let sleepChart = null;

function renderChart(sessions) {
  const ctx = document.getElementById('sleep-chart').getContext('2d');
  if (sleepChart) sleepChart.destroy();

  if (!sessions.length) return;

  // ラベル: "7/2(水)" 形式
  const labels = sessions.map(s => `${s.date}(${s.weekday})`);
  const hours  = sessions.map(s => s.hours);

  sleepChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: '睡眠時間（時間）',
        data: hours,
        backgroundColor: '#1a237e',
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

// ── ユーティリティ ────────────────────────────────────────
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
