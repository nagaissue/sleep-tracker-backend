"""
analyze.py — Gemini 2.5 Flash による睡眠データ分析エンドポイント
POST /api/analyze
Input:  { "records": [ { "type": "就寝"|"起床"|"昼寝", "datetime": "ISO8601" }, ... ] }
Output: {
  "metrics": {
    "avg_sleep_hours": float | null,
    "avg_bedtime": "HH:MM" | null,
    "avg_waketime": "HH:MM" | null,
    "sleep_consistency_score": int | null,   // 0-100（高いほど規則的）
    "total_nap_count": int,
    "sleep_debt_hours": float | null         // 8時間基準の累積不足時間（正の値=不足）
  },
  "summary": "総評テキスト",
  "insights": ["気づいた点1", "気づいた点2", ...],
  "recommendations": ["改善提案1", "改善提案2", ...]
}

アプリ内のAsyncStorageに保存された睡眠記録一式をこのエンドポイントに送信し、
Gemini 2.5 Flash に睡眠パターンの分析・指標算出・改善提案の生成を行わせる。
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
MIN_RECORDS_FOR_ANALYSIS = 2

# ── Pydanticスキーマ ───────────────────────────────────
class SleepMetrics(BaseModel):
    avg_sleep_hours: float | None = None
    avg_bedtime: str | None = None
    avg_waketime: str | None = None
    sleep_consistency_score: int | None = None
    total_nap_count: int = 0
    sleep_debt_hours: float | None = None

class SleepAnalysis(BaseModel):
    metrics: SleepMetrics
    summary: str
    insights: list[str]
    recommendations: list[str]

# ── Gemini クライアント ────────────────────────────────
def get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)

def build_prompt(records: list[dict], now_jst: datetime) -> str:
    records_sorted = sorted(records, key=lambda r: r.get("datetime", ""))
    records_json = json.dumps(records_sorted, ensure_ascii=False, indent=2)

    return f"""
あなたは睡眠データアナリストです。
以下の睡眠記録（就寝・起床・昼寝の時刻ログ）を分析し、睡眠指標の算出と改善提案を行ってください。

【現在日時（JST）】: {now_jst.strftime("%Y-%m-%d %H:%M")}

【睡眠記録一覧（時系列昇順・JST）】
{records_json}

【分析手順】
1. 「就寝」と「起床」を時系列でペアリングし、各夜の睡眠セッション（就寝時刻→翌朝起床時刻）を特定する。
   - ペアが成立しない孤立した記録（起床のない就寝、就寝のない起床など）は睡眠時間の計算対象から除外してよい。
2. 各セッションの睡眠時間（時間単位）を算出し、平均睡眠時間（avg_sleep_hours）を求める。
3. 就寝時刻・起床時刻それぞれの「時刻部分（時:分）」の平均を求め、avg_bedtime / avg_waketime として HH:MM 形式で返す。
4. 就寝時刻・起床時刻のばらつき（分散）をもとに、生活リズムの規則性を 0〜100 のスコア（sleep_consistency_score）で表す。
   - 就寝・起床時刻が毎日ほぼ同じ → 100に近いスコア
   - 日によって大きく異なる → 0に近いスコア
5. 「昼寝」の記録数を total_nap_count として数える。
6. 各セッションの睡眠時間と目安（8時間）との差を求め、不足分（8時間未満だった場合の差分）を合計したものを sleep_debt_hours とする（8時間以上だったセッションは0として扱う。全体で不足がなければ0）。
7. データが不足している場合（セッションが0〜1件など）は、算出できない指標は null にしてよい。

【出力内容】
- metrics: 上記で算出した指標
- summary: 全体的な睡眠傾向についての簡潔な総評（2〜3文、日本語、親しみやすい口調）
- insights: 記録から読み取れる具体的な気づき・パターン（3〜5項目、日本語の箇条書き）
  例: 「平日に比べて休日の起床時刻が2時間以上遅く、リズムが崩れています」
- recommendations: 睡眠改善のための具体的な提案（2〜4項目、日本語の箇条書き、実行しやすい内容）

データが少なすぎて意味のある分析ができない場合（記録が1件以下など）は、
summary にその旨を記載し、insights は空配列、recommendations には
「まずは就寝・起床を数日間記録してみましょう」といった一般的な助言を1件入れてください。

JSON形式で返してください。
"""

def analyze_sleep_data(records: list[dict]) -> dict:
    client = get_client()
    now_jst = datetime.now(JST)
    prompt = build_prompt(records, now_jst)

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SleepAnalysis,
            temperature=0.3,
        ),
    )

    result = SleepAnalysis.model_validate_json(response.text)
    return result.model_dump()

# ── Vercel Handler ─────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body)
            records = payload.get("records", [])

            if not isinstance(records, list):
                self._send(400, {"error": "records must be an array"})
                return

            if len(records) < MIN_RECORDS_FOR_ANALYSIS:
                self._send(200, {
                    "metrics": {
                        "avg_sleep_hours": None,
                        "avg_bedtime": None,
                        "avg_waketime": None,
                        "sleep_consistency_score": None,
                        "total_nap_count": 0,
                        "sleep_debt_hours": None,
                    },
                    "summary": "分析に必要な記録がまだ足りません。就寝・起床を数日間記録してから、もう一度お試しください。",
                    "insights": [],
                    "recommendations": ["まずは就寝・起床を数日間続けて記録してみましょう。"],
                })
                return

            result = analyze_sleep_data(records)
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
