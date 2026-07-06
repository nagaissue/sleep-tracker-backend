# 😴 Sleep Tracker Backend

Sleep Trackerアプリの **Python / Vercelバックエンド**。Gemini 2.5 Flashによる自然言語解析APIと睡眠データ分析APIを提供します。

> モバイルアプリ本体（Expo / React Native）は別リポジトリ [`nagaissue/sleep-tracker-mobile`](https://github.com/nagaissue/sleep-tracker-mobile) で管理しています。このリポジトリはそのバックエンドAPIのみを担当します。

**本番URL**: https://sleep-tracker-app-three.vercel.app

## 目次

- [役割](#役割)
- [技術スタック](#技術スタック)
- [ディレクトリ構成](#ディレクトリ構成)
- [API エンドポイント](#api-エンドポイント)
- [環境変数](#環境変数)
- [ローカル開発](#ローカル開発)
- [デプロイ](#デプロイ)
- [廃止済み機能](#廃止済み機能)
- [変更履歴](#変更履歴)

## 役割

モバイルアプリ（`nagaissue/sleep-tracker-mobile`）から直接呼び出される、認証レスのAPIサーバーです。

- ユーザーが入力したテキスト（例:「23:00に就寝、5:00に起床」）を **Gemini 2.5 Flash** で解析し、構造化された睡眠イベント（種別＋ISO8601時刻）に変換する
- アプリ内に蓄積された睡眠記録一式を受け取り、**Gemini 2.5 Flash** で睡眠パターンを分析し、指標・気づき・改善提案を返す

データの永続化は行いません（ステートレス）。記録の保存・統計計算はすべてモバイルアプリ側のAsyncStorageで完結しており、このバックエンドは解析・分析のロジックのみを担当します。

## 技術スタック

| 項目 | 内容 |
|---|---|
| 言語 / ランタイム | Python 3.12.12 |
| ホスティング | Vercel（Serverless Functions, Freeプラン） |
| 自然言語解析 / AI分析 | Gemini 2.5 Flash API（`google-genai`） |
| バリデーション | Pydantic（`response_schema`によるスキーマ強制） |

## ディレクトリ構成

```
sleep-tracker-app/
├── api/
│   ├── parse.py       # ✅ 使用中 — POST /api/parse（テキスト解析）
│   ├── analyze.py     # ✅ 使用中 — POST /api/analyze（睡眠データ分析）
│   ├── calendar.py    # ❌ 廃止 — 旧Google Calendar連携（参考用に保持のみ）
│   └── stats.py       # ❌ 廃止 — 旧サーバー側統計計算（参考用に保持のみ）
├── app/                # ❌ 廃止 — 旧Manus製Web版PWA（現在はモバイルアプリが主軸）
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── manifest.json
├── requirements.txt
├── vercel.json
└── .env.example
```

> Vercelの Python ランタイムには共有モジュールを配置せず、各エンドポイントファイルに必要なロジックを直接実装する方針を採っています（`api/*.py` はそれぞれ完結したハンドラです）。

## API エンドポイント

### POST /api/parse

自然言語テキストから睡眠イベントを抽出します。入力フォーマットは「カテゴリー（就寝・昼寝・起床）＋時刻（0:00〜23:59）」に固定されており、語順は自由です。

```json
// Request
{ "text": "23:00に就寝、5:00に起床" }

// Response
{
  "events": [
    {
      "type": "就寝",
      "datetime": "2026-07-07T23:00:00+09:00",
      "duration_min": null,
      "colorId": "9",
      "hex": "#5484ed"
    },
    {
      "type": "起床",
      "datetime": "2026-07-08T05:00:00+09:00",
      "duration_min": null,
      "colorId": "6",
      "hex": "#ffb878"
    }
  ]
}
```

- 起床時刻が就寝時刻より数値上小さい場合（例: 就寝23:00→起床5:00）、起床は自動的に翌日の日付として解決されます。
- `colorId` / `hex` はバックエンド互換用のフィールドで、モバイルアプリ内では独自のカラー設定（就寝=紺色、起床=オレンジと黄色の中間色、昼寝=青色）を使用するため参照していません。

### POST /api/analyze

睡眠記録一式（就寝・起床・昼寝のログ）を受け取り、Geminiが睡眠パターンを分析して指標と提案を返します。

```json
// Request
{
  "records": [
    { "type": "就寝", "datetime": "2026-07-01T23:00:00+09:00" },
    { "type": "起床", "datetime": "2026-07-02T06:30:00+09:00" },
    { "type": "昼寝", "datetime": "2026-07-02T14:00:00+09:00" }
  ]
}

// Response
{
  "metrics": {
    "avg_sleep_hours": 7.5,
    "avg_bedtime": "23:00",
    "avg_waketime": "06:30",
    "sleep_consistency_score": 85,
    "total_nap_count": 1,
    "sleep_debt_hours": 0.0
  },
  "summary": "総評テキスト...",
  "insights": ["気づいた点1", "気づいた点2"],
  "recommendations": ["改善提案1", "改善提案2"]
}
```

- 記録が2件未満の場合は分析を行わず、「記録が足りません」という定型レスポンスを返します。
- 就寝と起床を時系列でペアリングして睡眠セッションを特定し、平均睡眠時間・生活リズムの規則性スコア（0〜100）・8時間基準の睡眠負債を算出します。

### レスポンス実装上の注意

Vercelの Python ランタイム（`BaseHTTPRequestHandler`）では、`send_response()` を必ず `send_header()` より前に呼び出す必要があります（`api/parse.py` / `api/analyze.py` 共通の実装ルール）。

## 環境変数

| 変数名 | 説明 | 使用状況 |
|---|---|---|
| `GEMINI_API_KEY` | Gemini 2.5 Flash APIキー | ✅ 使用中 |
| `GOOGLE_CLIENT_ID` | Google OAuth クライアントID | ❌ 廃止（旧Calendar連携用） |
| `GOOGLE_CLIENT_SECRET` | Google OAuth クライアントシークレット | ❌ 廃止（旧Calendar連携用） |
| `GOOGLE_REFRESH_TOKEN` | Google OAuth リフレッシュトークン | ❌ 廃止（旧Calendar連携用） |
| `GOOGLE_CALENDAR_ID` | 対象カレンダーID | ❌ 廃止（旧Calendar連携用） |

`.env.example` を参照。実運用ではVercelのプロジェクト設定に環境変数を登録します（`.env` はコミットしません）。

## ローカル開発

```bash
# 依存関係のインストール
pip install -r requirements.txt

# 環境変数の設定
cp .env.example .env.local
# .env.local に GEMINI_API_KEY を設定

# Vercel CLI でローカル実行
npx vercel dev
```

## デプロイ

Vercel Freeプラン上で本番稼働しています。

```bash
npx vercel --prod
```

Python 3.12系がランタイムとして使用されます（`uv.lock` / `.python-version` により固定）。

## 廃止済み機能

v2.0.0でGoogle Calendar API連携を廃止し、モバイルアプリ側のAsyncStorageによるローカル保存・統計計算に移行しました。`api/calendar.py` と `api/stats.py` は当時の実装の参考として残していますが、本番では呼び出されません。

同様に `app/` 配下の静的Web版PWA（Manus時代の実装）も現在は利用しておらず、モバイルアプリ（`nagaissue/sleep-tracker-mobile`）が正式なクライアントです。

## 変更履歴

### v2.2.0 (2026-07-07)

- `/api/parse` の入力フォーマットを「カテゴリー＋時刻」に固定し、プロンプトを改訂
- 就寝→起床のように時系列が矛盾する場合、起床側を自動的に翌日と判定するロジックを追加
- 新規エンドポイント `/api/analyze` を追加— Gemini 2.5 Flash による睡眠データ分析（指標算出・気づき・改善提案）
- バックエンドをモバイルリポジトリから分離し、`nagaissue/sleep-tracker-backend` として独立管理を開始

### v2.0.0

- Google Calendar API連携を廃止し、クライアント側（AsyncStorage）でのデータ保存・統計計算に移行
- サーバー側は解析・分析のロジックのみを担当するステートレス構成に変更

## ライセンス

個人プロジェクト（非公開用途）
