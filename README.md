# 😴 Sleep Tracker App

Android向け睡眠記録アプリ。テキスト入力で「就寝」「起床」「昼寝」の時刻を記録し、アプリ内カレンダーで管理します。記録したデータはGeminiによるAI分析にも対応しています。

**v2.1.0より音声認識機能を廃止し、テキスト入力専用となりました。**
**v2.2.0より入力フォーマットを「カテゴリー＋時刻」に固定し、AI睡眠分析機能を追加しました。**

## 目次

- [機能](#機能)
- [技術スタック](#技術スタック)
- [アーキテクチャ](#アーキテクチャ)
- [イベントカラー](#イベントカラー)
- [前提条件](#前提条件)
- [インストール手順](#インストール手順)
- [ビルド手順（Android APK）](#ビルド手順android-apk)
- [ビルドトラブルシューティング](#ビルドトラブルシューティング)
- [API エンドポイント](#api-エンドポイント)
- [プロジェクト構成](#プロジェクト構成)
- [変更履歴](#変更履歴)

## 機能

- ⌨️ **テキスト入力（固定フォーマット）** — 「カテゴリー（就寝・昼寝・起床）＋時刻（0:00〜23:59）」で記録
  - 例: 「23:00に就寝、5:00に起床」「23:00、就寝、5:00、起床」など、語順は自由
- 🤖 **自然言語解析** — Gemini 2.5 Flash API が時刻情報を自動抽出、日付またぎ（就寝→翌朝起床）も自動判定
- 🧠 **AI睡眠分析** — 過去30日間の記録をGeminiが分析し、睡眠指標・気づき・改善提案を提示
  - 平均睡眠時間、生活リズムの規則性スコア、推定睡眠負債などを算出
- 📅 **アプリ内カレンダー** — 月間ビューで睡眠記録をカラー ドット表示
  - 日をタップするとその日の就寝/起床/昼寝の詳細を表示
  - 前月/翌月へのナビゲーション対応
- 🗑️ **個別削除** — カレンダー詳細画面で記録を1件ずつ削除可能
- 💾 **ローカルストレージ** — AsyncStorage でデータをアプリ内に保存（ネットワーク不要）
- 📊 **睡眠統計ダッシュボード** — 過去7日間の平均睡眠時間、就寝/起床時刻、日別チャート
  - 就寝↔起床のペアリングで実際の睡眠時間を自動計算

## 技術スタック

| レイヤー | 技術 |
|---|---|
| フロントエンド | Expo SDK 52 + React Native + TypeScript |
| 入力方式 | TextInput（テキスト入力専用） |
| 自然言語解析 | Gemini 2.5 Flash API（Vercel バックエンド経由） |
| データ保存 | @react-native-async-storage/async-storage（アプリ内ローカル） |
| 統計計算 | クライアント側（lib/stats.ts） |
| バックエンド | Python 3.12 + Vercel Serverless Functions（テキスト解析のみ） |
| デプロイ | Vercel (Hobby Free Plan) |

## アーキテクチャ

```
テキスト入力
      ↓
Gemini 2.5 Flash解析（Vercel /api/parse）
      ↓
SleepEvent[] （就寝/起床/昼寝 + 日時）
      ↓
AsyncStorage にローカル保存
      ↓
カレンダー表示 / 統計計算（すべてアプリ内で完結）
```

Google Calendar APIは使用しません。データはデバイス内のAsyncStorageに保存され、ネットワーク接続なしでもカレンダー閲覧・統計確認が可能です。

## イベントカラー

| イベント | カラー | 説明 |
|---|---|---|
| 就寝 | 紺（#1e3a8a） | 睡眠開始を示す |
| 起床 | オレンジ×黄（#f97316） | 睡眠終了を示す |
| 昼寝 | 青（#3b82f6） | 昼間の仮眠を示す |

## 前提条件

- Node.js 18+
- npm（Node.jsに同梱）
- Android Studio（Android SDK + Build Tools + NDK + CMake）
- JDK 17（Android Gradle Plugin 8.x対応）
- Git

### Android Studio側の準備

1. Android Studioをインストール
2. **More Actions** → **SDK Manager** で以下をインストール：
   - Android SDK Platform 35
   - Android SDK Build-Tools 35.0.0
   - NDK (Side by side) 26.1.10909125
   - CMake 3.22.1
3. SDKのインストール先パスを確認（通常 `C:\Users\<ユーザー名>\AppData\Local\Android\Sdk`）

## インストール手順

### 1. リポジトリのクローン

```bash
# Windowsの場合、パスが短い場所にクローンすることが重要
# ❌ 避ける: C:\Users\<ユーザー名>\GitRepo\sleep-tracker-mobile
# ✅ 推奨: C:\dev\app のような短いパス

mkdir C:\dev
cd C:\dev
git clone https://github.com/nagaissue/sleep-tracker-mobile.git app
cd app
```

> ⚠️ **重要:** Windows環境では、プロジェクトパスが長すぎるとCMake/ninjaのビルドが失敗します（詳細は[トラブルシューティング](#ビルドトラブルシューティング)を参照）。`C:\dev\app`のような短いパスを推奨します。

### 2. 依存関係のインストール

```bash
npm install --legacy-peer-deps
```

### 3. Vercelバックエンドのセットアップ

バックエンド（テキスト解析API）は別リポジトリ `sleep-tracker-app` で管理しています。

詳細は `sleep-tracker-app/README.md` を参照してください。必要な環境変数：

| 環境変数 | 説明 |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio で取得したGemini APIキー |
| `GOOGLE_CLIENT_ID` | Google Cloud Console のOAuth クライアントID |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console のOAuth クライアントシークレット |
| `GOOGLE_REFRESH_TOKEN` | OAuth Playground で取得したリフレッシュトークン |

> v2.0.0以降、バックエンドで使用するのは `/api/parse`（Gemini解析）のみです。`/api/calendar` と `/api/stats` は不要です。

### 4. API接続先の設定（任意）

デフォルトのAPI URLを変更する場合、`.env` ファイルを作成：

```bash
echo "EXPO_PUBLIC_API_BASE_URL=https://your-vercel-app.vercel.app" > .env
```

未設定の場合はデフォルトURL（`https://sleep-tracker-app-three.vercel.app`）が使用されます。

## ビルド手順（Android APK）

### 手順1: prebuild でAndroidプロジェクトを生成

```bash
cd C:\dev\app
npx expo prebuild --platform android --clean
```

> `--clean` は既存のAndroidプロジェクトを削除して再生成します。`local.properties`も消えるため、次の手順で再作成が必要です。

### 手順2: local.properties を作成

`prebuild --clean` で消えた `local.properties` を再作成します：

```bash
echo "sdk.dir=C:/Users/<ユーザー名>/AppData/Local/Android/Sdk" > android/local.properties
```

> パスの区切り文字は `\` ではなく `/` を使用してください。
> 実際のSDKパスは Android Studio の SDK Manager で確認できます。

### 手順3: Kotlin バージョンを修正

Expo SDK 52 のprebuildでは、Kotlin バージョンの指定が不足している場合があります。以下を修正します：

**3a.** `android/gradle.properties` の末尾に追加：

```bash
echo "android.kotlinVersion=1.9.25" >> android/gradle.properties
```

**3b.** `android/build.gradle` の `kotlin-gradle-plugin` にバージョンを指定：

```powershell
# PowerShellの場合
(Get-Content android/build.gradle) -replace "classpath\('org.jetbrains.kotlin:kotlin-gradle-plugin'\)", 'classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.25")' | Set-Content android/build.gradle
```

### 手順4: ビルド実行

```bash
cd android
./gradlew clean
./gradlew assembleRelease
```

ビルドには10〜25分かかります（初回はNDKやCMakeのダウンロードも含むため）。

### 手順5: APKの取得

ビルド成功後、APKは以下に生成されます：

```
android/app/build/outputs/apk/release/app-release.apk
```

### 手順6: Android端末にインストール

**方法A: adbコマンドを使用**

```bash
adb install android/app/build/outputs/apk/release/app-release.apk
```

**方法B: ファイルを直接コピー**

1. エクスプローラーからAPKファイルをAndroid端末にコピー（USB転送やクラウド経由）
2. 端末でAPKをタップしてインストール
3. 「提供元不明のアプリ」の許可が必要な場合があります

## ビルドトラブルシューティング

このプロジェクトのビルド過程で実際に遭遇したエラーと解決方法を記録します。

### 1. SDK location not found

```
> SDK location not found. Define a valid SDK location with an ANDROID_HOME
  environment variable or by setting the sdk.dir path in your project's
  local properties file at '.../android/local.properties'.
```

**原因:** `local.properties` ファイルが存在しない、または `expo prebuild --clean` で削除された。

**解決策:** `local.properties` を手動で作成：

```bash
echo "sdk.dir=C:/Users/<ユーザー名>/AppData/Local/Android/Sdk" > android/local.properties
```

> `prebuild --clean` を実行するたびにこのファイルが消えるため、毎回再作成が必要です。

---

### 2. Kotlin バージョン不一致

```
e: This version (1.5.15) of the Compose Compiler requires Kotlin version 1.9.25
   but you appear to be using Kotlin version 1.9.24 which is not known to be compatible.
```

**原因:** Expo SDK 52 のprebuildで生成された `build.gradle` において、Kotlin Gradle Plugin のバージョンが未指定（デフォルトの1.9.24が使用される）だったが、Compose Compiler 1.5.15 は Kotlin 1.9.25 を要求する。

**解決策:** 以下の2箇所を修正：

1. `android/gradle.properties` に追加：
   ```properties
   android.kotlinVersion=1.9.25
   ```

2. `android/build.gradle` のclasspathを修正：
   ```groovy
   // 修正前
   classpath('org.jetbrains.kotlin:kotlin-gradle-plugin')
   // 修正後
   classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.25")
   ```

---

### 3. Windowsパス長制限によるninjaエラー

```
ninja: error: mkdir(src/main/cpp/reanimated/CMakeFiles/reanimated.dir/
  C_/Users/r9one/GitRepo/sleep-tracker-mobile/node_modules/
  react-native-reanimated/Common): No such file or directory
```

**原因:** Windowsのファイルパス長制限（MAX_PATH = 260文字）。`react-native-reanimated` のCMakeビルドでは、オブジェクトファイルのパスが260文字を超えるため、ninjaがディレクトリを作成できない。ビルドログにも以下の警告が出力される：

```
The object file directory has 180 characters. The maximum full path
to an object file is 250 characters (see CMAKE_OBJECT_PATH_MAX).
```

**解決策:** プロジェクトを短いパスに配置する：

```bash
# ❌ 長すぎるパス（約50文字）
C:\Users\r9one\GitRepo\sleep-tracker-mobile

# ✅ 短いパス（約10文字）
C:\dev\app
```

**補足:** Windows長パスサポート（レジストリ `LongPathsEnabled=1`）を有効にしても、ninja/CMakeが対応しないため効果なし。パスを短くするのが唯一の確実な解決策。

---

### 4. git clone でサブフォルダが作成される

```bash
cd C:\dev
git clone https://github.com/nagaissue/sleep-tracker-mobile.git
# C:\dev\sleep-tracker-mobile\ にクローンされてしまう
```

**原因:** `git clone` はデフォルトでリポジトリ名のディレクトリを作成する。

**解決策:** クローン時にターゲットディレクトリ名を指定：

```bash
git clone https://github.com/nagaissue/sleep-tracker-mobile.git app
# C:\dev\app\ に直接クローンされる
```

すでにクローン済みの場合は、ファイルを移動：

```powershell
cd C:\dev
Copy-Item -Path .\sleep-tracker-mobile\* -Destination .\ -Recurse -Force
Copy-Item -Path .\sleep-tracker-mobile\.git -Destination .\ -Recurse -Force
Copy-Item -Path .\sleep-tracker-mobile\.gitignore -Destination .\ -Force
Remove-Item -Recurse -Force .\sleep-tracker-mobile
```

## API エンドポイント

### バックエンド（Vercel / sleep-tracker-app リポジトリ）

| エンドポイント | メソッド | 説明 | 使用状況 |
|---|---|---|---|
| `/api/parse` | POST | Gemini 2.5 Flash でテキスト解析（カテゴリー＋時刻の抽出） | ✅ 使用中 |
| `/api/analyze` | POST | Gemini 2.5 Flash で睡眠記録全体を分析（指標算出・気づき・提案） | ✅ 使用中（v2.2.0〜） |
| `/api/calendar` | POST | Google Calendar にイベント登録 | ❌ 廃止（v2.0.0〜） |
| `/api/stats` | GET | 睡眠統計データを取得 | ❌ 廃止（v2.0.0〜） |

### POST /api/parse

入力フォーマットは「カテゴリー（就寝・昼寝・起床）＋時刻（0:00〜23:59）」で固定。カテゴリーと時刻の語順は自由。

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

> 起床時刻が就寝時刻より数値上小さい場合（例: 就寝23:00→起床5:00）、起床は自動的に翌日の日付として解決される。

### POST /api/analyze

アプリ内に保存された睡眠記録一式（就寝・起床・昼寝のログ）を送信すると、Geminiが睡眠パターンを分析し、指標・気づき・改善提案を返す。

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

> 記録が2件未満の場合は分析を行わず、「記録が足りません」という定型レスポンスを返す。

## プロジェクト構成

```
├── app/
│   ├── _layout.tsx              # ルートレイアウト（SafeAreaProvider + Stack）
│   ├── (tabs)/
│   │   ├── _layout.tsx          # タブナビゲーション（記録 / カレンダー / 統計 / 設定）
│   │   ├── index.tsx            # 記録タブ — テキスト入力（固定フォーマット）→ Gemini解析 → ローカル保存
│   │   ├── calendar.tsx         # カレンダータブ — 月間カレンダー（カラードット + 日詳細 + 個別削除）
│   │   ├── stats.tsx            # 統計タブ — 睡眠統計ダッシュボード（ローカル計算）+ AI睡眠分析（Gemini）
│   │   └── settings.tsx         # 設定タブ — データ管理・API状態・カラー凡例・技術情報
│   └── +not-found.tsx           # 404 ページ
├── components/
│   └── SleepChart.tsx           # 日別睡眠時間バーチャート
├── lib/
│   ├── api.ts                   # Vercel API クライアント（parseText / analyzeSleep）
│   ├── storage.ts               # AsyncStorage CRUD（ローカルデータ管理・個別削除対応）
│   ├── stats.ts                 # ローカル統計計算（就寝↔起床ペアリング含む）
│   └── theme.ts                 # カラー・テーマ定数
├── assets/
│   └── images/                  # アプリアイコン・スプラッシュ画面
├── app.json                     # Expo 設定
├── package.json
└── tsconfig.json
```

## 変更履歴

### v2.2.0 (2026-07-07)

- **入力フォーマットを「カテゴリー＋時刻」に固定**
  - `/api/parse` のプロンプトを改訂し、「就寝/昼寝/起床」＋「0:00〜23:59の時刻」の2要素のみを抽出する形式に統一
  - カテゴリーと時刻はどちらが先でもよい（例: 「23:00、就寝」「就寝、23:00」いずれも可）
  - 就寝→起床のように時系列が矛盾する場合、起床側を自動的に翌日と判定するロジックを追加
  - 記録タブの入力欄プレースホルダーとヒントを新フォーマットに合わせて更新
- **AI睡眠分析機能を追加**
  - 新規エンドポイント `/api/analyze` — Gemini 2.5 Flash が過去30日間の睡眠記録を分析
  - 平均睡眠時間・平均就寝/起床時刻・生活リズムの規則性スコア（0〜100）・推定睡眠負債を算出
  - 具体的な気づき（insights）と改善提案（recommendations）を日本語で生成
  - 統計タブに「AI睡眠分析」セクションを追加（ボタン押下で分析実行、結果をカード表示）
  - 記録が2件未満の場合は分析を行わず、記録を促す定型メッセージを返す

### v2.1.0 (2026-07-06)

- **音声認識機能（expo-speech-recognition）を廃止**し、テキスト入力専用に変更
  - マイクボタン、音声認識イベントハンドラ、権限リクエストをすべて削除
  - `expo-speech-recognition` パッケージを依存関係から削除
  - `RECORD_AUDIO` パスーミッション、マイク関連のinfoPlistを削除
  - 記録タブのアイコンをマイクからペン（create-outline）に変更
- **カレンダーに個別削除機能を追加**
  - 日詳細画面で各レコードに削除ボタン（✕）を表示
  - 削除前に確認ダイアログを表示
  - `storage.ts`の`deleteRecord()`関数をカレンダー画面から呼び出し

### v2.0.0 (2026-07-05)

- **Google Calendar API連携を廃止**し、アプリ内ローカルストレージ（AsyncStorage）に切り替え
- 新規「カレンダー」タブ追加（月間ビュー、カラー ドット表示、日タップで詳細）
- 統計計算をクライアント側に移行（Vercel `/api/stats` 不要）
- データ管理機能追加（全削除、レコード数表示）
- データ保存・統計計算をGoogle Calendar APIからAsyncStorage + クライアント計算に変更
- イベントカラーをGoogle Calendar colorIdから独自カラー定義に変更

### v1.0.0

- 初期リリース
- Google Calendar API v3 連携
- 音声認識 + Gemini 2.5 Flash 解析
- 睡眠統計ダッシュボード

## ライセンス

MIT
