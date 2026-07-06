"""
stats.py — 睡眠統計ダッシュボード用データ集計エンドポイント（認証レス）
GET /api/stats?days=7
Output: 睡眠統計サマリー（日付ラベル付きセッションデータを含む）
"""

import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

JST = timezone(timedelta(hours=9))
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
EVENT_TYPES = ["就寝", "起床", "昼寝"]
TOKEN_URL = "https://oauth2.googleapis.com/token"

_cached_token: str | None = None
_cached_expiry: float = 0


def get_access_token() -> str:
    """環境変数のリフレッシュトークンからアクセストークンを取得（必要な場合のみ更新）"""
    global _cached_token, _cached_expiry

    if _cached_token and time.time() < _cached_expiry - 60:
        return _cached_token

    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())

    _cached_token = result["access_token"]
    _cached_expiry = time.time() + result.get("expires_in", 3600)
    return _cached_token


def create_calendar_service():
    token = get_access_token()
    creds = Credentials(token=token)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def fetch_sleep_events(service, days: int) -> list:
    now = datetime.now(JST)
    time_min = (now - timedelta(days=days)).isoformat()
    time_max = now.isoformat()

    all_events = []
    for ev_type in EVENT_TYPES:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            q=ev_type,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        for item in result.get("items", []):
            if item.get("summary") and item["summary"].startswith(ev_type):
                all_events.append({
                    "type": ev_type,
                    "summary": item["summary"],
                    "start": item["start"].get("dateTime"),
                    "end": item["end"].get("dateTime"),
                })
    return all_events


def compute_stats(events: list, days: int) -> dict:
    sleep_events = [e for e in events if e["type"] == "就寝"]
    wake_events  = [e for e in events if e["type"] == "起床"]
    nap_events   = [e for e in events if e["type"] == "昼寝"]

    # 就寝イベントから実際の睡眠時間を計算（カレンダーのend時刻を使用）
    sleep_sessions = []
    for s in sleep_events:
        s_dt = datetime.fromisoformat(s["start"])
        e_dt = datetime.fromisoformat(s["end"])
        dur_hours = round((e_dt - s_dt).total_seconds() / 3600, 1)

        # 対応する起床を探す
        wake_time = None
        for w in wake_events:
            w_dt = datetime.fromisoformat(w["start"])
            diff = (w_dt - s_dt).total_seconds() / 3600
            if 0 <= diff <= 14:
                wake_time = w_dt.strftime("%H:%M")
                break

        sleep_sessions.append({
            "date": s_dt.strftime("%m/%d"),
            "bedtime": s_dt.strftime("%H:%M"),
            "waketime": wake_time,
            "hours": dur_hours,
            "weekday": ["月", "火", "水", "木", "金", "土", "日"][s_dt.weekday()],
        })

    # 日付順にソート（古い順）
    sleep_sessions.sort(key=lambda x: x["date"])
    sleep_durations = [s["hours"] for s in sleep_sessions]

    avg_sleep_h = round(sum(sleep_durations) / len(sleep_durations), 1) if sleep_durations else None

    def avg_time_str(dts: list) -> str | None:
        if not dts:
            return None
        minutes = [(dt.hour * 60 + dt.minute) for dt in dts]
        avg_min = int(sum(minutes) / len(minutes))
        return f"{avg_min // 60:02d}:{avg_min % 60:02d}"

    sleep_dts = [datetime.fromisoformat(e["start"]) for e in sleep_events]
    wake_dts  = [datetime.fromisoformat(e["start"]) for e in wake_events]

    nap_total_min = 0
    for n in nap_events:
        if n["start"] and n["end"]:
            diff = datetime.fromisoformat(n["end"]) - datetime.fromisoformat(n["start"])
            nap_total_min += int(diff.total_seconds() / 60)

    return {
        "period_days": days,
        "total_records": len(events),
        "sleep_sessions": len(sleep_sessions),
        "avg_sleep_hours": avg_sleep_h,
        "avg_bedtime": avg_time_str(sleep_dts),
        "avg_waketime": avg_time_str(wake_dts),
        "nap_count": len(nap_events),
        "nap_total_min": nap_total_min,
        "events_breakdown": {
            "就寝": len(sleep_events),
            "起床": len(wake_events),
            "昼寝": len(nap_events),
        },
        # 日付ラベル付きセッションデータ（チャート用）
        "sleep_sessions_detail": sleep_sessions,
        "daily_sleep_hours": sleep_durations,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            days = int(params.get("days", ["7"])[0])

            if not (1 <= days <= 90):
                self._send(400, {"error": "days must be between 1 and 90"})
                return

            service = create_calendar_service()
            events = fetch_sleep_events(service, days)
            stats = compute_stats(events, days)
            self._send(200, stats)

        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _send(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
