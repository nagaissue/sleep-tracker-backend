"""
calendar.py — Google Calendar イベント登録エンドポイント（サーバー完結・認証レス）
POST /api/calendar
Input:
  {
    "events": [
      { "type": "就寝", "datetime": "2026-07-01T23:00:00+09:00", "colorId": "9" },
      { "type": "起床", "datetime": "2026-07-02T06:30:00+09:00", "colorId": "6" }
    ]
  }
Output: { "created": [ { "id": "...", "htmlLink": "..." } ] }

※ 就寝と起床が同時に含まれる場合、ペアリングして：
   - 就寝イベントの終了時刻 = 起床時刻（実際の睡眠時間がブロックとして表示される）
   - 起床イベントは起床時刻のマーカー（1分間のポイントイベント）
   就寝のみの場合はデフォルト8時間、起床のみの場合はマーカーのみ。
"""

import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

JST = timezone(timedelta(hours=9))

DEFAULT_SLEEP_DURATION_MIN = 480  # 就寝のみの場合のデフォルト8時間
DEFAULT_NAP_DURATION_MIN = 30     # 昼寝のデフォルト

CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
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


def pair_sleep_events(events: list) -> list:
    """
    就寝と起床をペアリングし、カレンダー登録用のイベントリストを構築する。

    - 就寝+起床がある場合:
        就寝イベント: start=就寝時刻, end=起床時刻（実際の睡眠時間）
        起床イベント: start=起床時刻, end=起床時刻+1分（マーカー）
    - 就寝のみ: デフォルト8時間
    - 起床のみ: マーカーのみ
    - 昼寝: duration_min or デフォルト30分
    """
    sleep_events = [e for e in events if e["type"] == "就寝"]
    wake_events  = [e for e in events if e["type"] == "起床"]
    nap_events   = [e for e in events if e["type"] == "昼寝"]

    # 起床時刻をdatetimeに変換してソート
    wake_dts = sorted([
        datetime.fromisoformat(w["datetime"]) for w in wake_events
    ])

    calendar_events = []

    # --- 就寝イベント（ペアリングあり） ---
    for s in sleep_events:
        s_dt = datetime.fromisoformat(s["datetime"])
        color_id = s.get("colorId", "9")

        # 対応する起床を探す：就寝より後の直近の起床
        matched_wake = None
        for w_dt in wake_dts:
            if w_dt > s_dt:
                diff_hours = (w_dt - s_dt).total_seconds() / 3600
                if 2 <= diff_hours <= 14:  # 妥当な睡眠時間範囲
                    matched_wake = w_dt
                    break

        if matched_wake:
            # ペアリング成功：就寝→起床の実時間
            end_dt = matched_wake
            duration_min = int((end_dt - s_dt).total_seconds() / 60)
        else:
            # 起床なし：デフォルト8時間
            end_dt = s_dt + timedelta(minutes=DEFAULT_SLEEP_DURATION_MIN)
            duration_min = DEFAULT_SLEEP_DURATION_MIN

        calendar_events.append({
            "type": "就寝",
            "start_dt": s_dt,
            "end_dt": end_dt,
            "colorId": color_id,
            "duration_min": duration_min,
            "summary": f"就寝 {s_dt.strftime('%H:%M')}〜{end_dt.strftime('%H:%M')} ({duration_min // 60}h{duration_min % 60}m)",
        })

    # --- 起床イベント（マーカー） ---
    for w in wake_events:
        w_dt = datetime.fromisoformat(w["datetime"])
        color_id = w.get("colorId", "6")
        end_dt = w_dt + timedelta(minutes=1)  # ポイントマーカー

        calendar_events.append({
            "type": "起床",
            "start_dt": w_dt,
            "end_dt": end_dt,
            "colorId": color_id,
            "duration_min": 1,
            "summary": f"起床 {w_dt.strftime('%H:%M')}",
        })

    # --- 昼寝イベント ---
    for n in nap_events:
        n_dt = datetime.fromisoformat(n["datetime"])
        color_id = n.get("colorId", "1")
        duration_min = n.get("duration_min") or DEFAULT_NAP_DURATION_MIN
        end_dt = n_dt + timedelta(minutes=duration_min)

        calendar_events.append({
            "type": "昼寝",
            "start_dt": n_dt,
            "end_dt": end_dt,
            "colorId": color_id,
            "duration_min": duration_min,
            "summary": f"昼寝 {n_dt.strftime('%H:%M')}〜{end_dt.strftime('%H:%M')} ({duration_min}m)",
        })

    return calendar_events


def build_event_body(cal_event: dict) -> dict:
    return {
        "summary": cal_event["summary"],
        "colorId": cal_event["colorId"],
        "start": {"dateTime": cal_event["start_dt"].isoformat(), "timeZone": "Asia/Tokyo"},
        "end":   {"dateTime": cal_event["end_dt"].isoformat(),   "timeZone": "Asia/Tokyo"},
        "reminders": {"useDefault": False},
        "source": {"title": "Sleep Tracker App", "url": "https://sleep-tracker-app.vercel.app"},
    }


def register_events(events: list) -> list:
    service = create_calendar_service()
    cal_events = pair_sleep_events(events)
    created = []
    for ce in cal_events:
        body = build_event_body(ce)
        result = service.events().insert(calendarId=CALENDAR_ID, body=body).execute()
        created.append({
            "id": result.get("id"),
            "type": ce["type"],
            "start": ce["start_dt"].isoformat(),
            "end": ce["end_dt"].isoformat(),
            "duration_min": ce["duration_min"],
            "summary": ce["summary"],
            "htmlLink": result.get("htmlLink"),
        })
    return created


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body)

            events = payload.get("events", [])
            if not events:
                self._send(400, {"error": "events field is required"})
                return

            created = register_events(events)
            self._send(200, {"created": created})

        except json.JSONDecodeError:
            self._send(400, {"error": "Invalid JSON"})
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
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
