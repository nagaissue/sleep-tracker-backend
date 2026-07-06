"""
parse.py — Gemini 2.5 Flash による自然言語解析エンドポイント
POST /api/parse
Input:  { "text": "23:00に就寝、5:00に起床" }
Output: { "events": [ { "type": "就寝"|"起床"|"昼寝", "datetime": "ISO8601" } ] }

【入力フォーマット（固定・v2.2.0〜）】
睡眠記録は以下の2要素のみで構成される：
  1. カテゴリー: 「就寝」「昼寝」「起床」のいずれか
  2. 時刻:      0:00〜23:59（当日基準）

例:
  「23:00に就寝、5:00に起床」
  「23:00、就寝、5:00、起床」（カテゴリーと時刻はどちらが先でもよい）
  「就寝 23:00 起床 5:00」
"""

import os
import json
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

from google import genai
from google.genai import types
from pydantic import BaseModel

# ── 定数 ──────────────────────────────────────────────
JST = timezone(timedelta(hours=9))
MODEL_ID = "gemini-2.5-flash"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Googleカレンダーイベントカラーマッピング（アプリ内では未使用・バックエンド互換用）
COLOR_MAP = {
    "就寝": {"colorId": "9",  "hex": "#5484ed"},   # Blueberry（紺）
    "起床": {"colorId": "6",  "hex": "#ffb878"},   # Tangerine（オレンジ×黄中間）
    "昼寝": {"colorId": "1",  "hex": "#a4bdfc"},   # Lavender（青）
}

# ── Pydanticスキーマ ───────────────────────────────────
class SleepEvent(BaseModel):
    type: str        # "就寝" | "起床" | "昼寝"
    datetime: str    # ISO8601形式 (JST)

class ParseResult(BaseModel):
    events: list[SleepEvent]

# ── Gemini クライアント ────────────────────────────────
def get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)

def build_prompt(user_text: str, now_jst: datetime) -> str:
    return f"""
あなたは睡眠記録アシスタントです。
ユーザーの入力から「就寝」「昼寝」「起床」の記録を抽出してください。

【現在日時（JST）】: {now_jst.strftime("%Y-%m-%d %H:%M")}（{["月","火","水","木","金","土","日"][now_jst.weekday()]}曜日）

【入力フォーマット（固定・重要）】
記録は必ず以下の2要素のみで構成されます。
  1. カテゴリー: 「就寝」「昼寝」「起床」のいずれか
  2. 時刻: 0:00〜23:59 の時刻（24時間表記、分単位）

カテゴリーと時刻はどちらが先に書かれていても構いません。以下はすべて同じ内容を表す入力例です:
  - "23:00に就寝、5:00に起床"
  - "23:00、就寝、5:00、起床"
  - "就寝 23:00 起床 5:00"
  - "就寝23時 起床5時"

【ユーザー入力】: {user_text}

【日付解決ルール】（重要・厳守）
1. 時刻には日付が明示されないため、以下の優先順位で日付を決定する：
   a. 「昨夜」「昨日」「今朝」「今日」などの相対語が明示されている場合はそれに従う。
   b. 複数のイベントが同一入力内にあり、時系列的に矛盾する場合（例：就寝23:00→起床5:00のように、後続の時刻が前の時刻より小さい）は、後続のイベントを「翌日」の日付とする。
      例: 現在日時が 2026-07-07 の入力で「23:00に就寝、5:00に起床」の場合、
          就寝 = 2026-07-07T23:00:00+09:00、起床 = 2026-07-08T05:00:00+09:00（翌日）
   c. 単独のイベントで相対語もない場合は、現在日時を基準に「直近の過去」に解決する（未来にならないようにする）。
      例: 現在時刻が 02:00 で「23:00に就寝」とだけ入力された場合、その23:00は前日の夜を指すため前日の日付とする。
2. 「うたた寝」「仮眠」は「昼寝」として扱う。
3. type は必ず「就寝」「起床」「昼寝」のいずれかとする。
4. 時刻に関する説明（何分眠った等）や不要な情報は無視し、カテゴリーと時刻のみを抽出する。
5. 抽出できる正しいイベントのみを返す（形式に合わないものは含めない）。
6. 時刻は必ず JST の ISO8601 形式（例: 2026-07-07T23:00:00+09:00）で返す。

JSON形式で返してください。
"""

def parse_sleep_text(user_text: str) -> dict:
    client = get_client()
    now_jst = datetime.now(JST)
    prompt = build_prompt(user_text, now_jst)

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParseResult,
            temperature=0.1,
        ),
    )

    result = ParseResult.model_validate_json(response.text)

    # カラー情報を付与（バックエンド互換用。アプリ内では未使用）
    enriched_events = []
    for ev in result.events:
        color_info = COLOR_MAP.get(ev.type, {"colorId": "8", "hex": "#e1e1e1"})
        enriched_events.append({
            "type": ev.type,
            "datetime": ev.datetime,
            "duration_min": None,
            "colorId": color_info["colorId"],
            "hex": color_info["hex"],
        })

    return {"events": enriched_events}

# ── Vercel Handler ─────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body)
            user_text = payload.get("text", "").strip()

            if not user_text:
                self._send(400, {"error": "text field is required"})
                return

            result = parse_sleep_text(user_text)
            self._send(200, result)

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
