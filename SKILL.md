---
name: youtube-publisher
description: >
  End-to-end video publishing pipeline: download from Google Drive, upload to YouTube,
  transcribe audio via Deepgram or Fireworks Whisper, generate title/description/timestamps,
  clean up temp files. Use when: "залей на YouTube", "опубликуй видео", "upload to YouTube",
  "видео из Drive на YouTube", "meet recording to YouTube", "транскрибируй и залей",
  "publish video", "upload recording". NOT for: video editing, adding intros/effects,
  non-Drive video sources, YouTube channel management, or live streaming.
---

# YouTube Publisher

Drive → YouTube → Transcript → Metadata → Cleanup.

## Setup

### 1. Google OAuth (required for Drive download + YouTube upload)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → enable **Google Drive API** and **YouTube Data API v3**
3. Create OAuth 2.0 credentials (Desktop app) → download as `google-oauth-client.json`
4. Run the authorization flow to get `google-oauth-tokens.json` with scopes:
   - `https://www.googleapis.com/auth/drive.readonly`
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube`

Place both files in one of these locations (checked in order):
- Skill root: `youtube-publisher/google-oauth-client.json`
- Config dir: `youtube-publisher/config/google-oauth-client.json`
- Workspace: `~/.openclaw/workspace/scripts/google-oauth-client.json`
- Env vars: `GOOGLE_OAUTH_CLIENT` and `GOOGLE_OAUTH_TOKENS` (paths to files)

### 2. Transcription API key (at least one required)

**Option A — Fireworks Whisper v3 Turbo** (preferred: faster, cheaper, $0.0009/min):
- Set `FIREWORKS_API_KEY` env var, or
- Save key to `youtube-publisher/config/fireworks-api-key.txt`

**Option B — Deepgram Nova-3** (fallback: good quality, smart_format):
- Set `DEEPGRAM_API_KEY` env var, or
- Save key to `youtube-publisher/config/deepgram-api-key.txt`

### 3. ffmpeg (required)

Must be on PATH. Install: `apt install ffmpeg` / `brew install ffmpeg`.

## Procedure

### Step 1: Extract file ID from Drive URL

Parse the Google Drive URL. Extract file ID from pattern `/file/d/{ID}/`.
If user provides a raw file ID, use it directly.

### Step 2: Download video from Google Drive

1. Refresh OAuth access token
2. Fetch file metadata (name, size, mimeType) via Drive API v3
3. Download file via `?alt=media` endpoint to temp dir
4. Log file name and size

### Step 3: Upload to YouTube

1. Create resumable upload session via YouTube Data API v3
2. Set initial metadata: placeholder title, privacy status from user (default: `unlisted`)
3. Upload video file
4. Save returned `video_id`
5. Log YouTube URL: `https://youtube.com/watch?v={video_id}`

### Step 4: Extract audio

```bash
ffmpeg -i source.mp4 -vn -acodec libmp3lame -ab 64k -ar 16000 -ac 1 audio.mp3 -y
```

64kbps mono, 16kHz — optimized for speech transcription, minimal file size.

### Step 5: Split into chunks

Split audio into 15-minute segments for parallel transcription:

```bash
ffmpeg -i audio.mp3 -ss {start} -t 900 -c copy chunk-{i}.mp3 -y
```

### Step 6: Transcribe (Fireworks or Deepgram)

**Fireworks Whisper v3 Turbo** (default if `FIREWORKS_API_KEY` set):
```
POST https://audio-turbo.us-virginia-1.direct.fireworks.ai/v1/audio/transcriptions
model=whisper-v3-turbo, language={lang}, response_format=verbose_json
```

**Deepgram Nova-3** (fallback if only `DEEPGRAM_API_KEY` set):
```
POST https://api.deepgram.com/v1/listen?model=nova-3&language={lang}&smart_format=true&paragraphs=true
```

Override with `--transcriber fireworks|deepgram`.
Chunks transcribed in parallel (6 workers). Merge with time offset: `chunk_index × 900` seconds.

### Step 7: Generate timestamps

Extract topic boundaries from transcript. Rules:

- Minimum 3 minutes between timestamps
- First timestamp MUST be `0:00`
- **Format under 1 hour:** `MM:SS` (e.g., `05:30`, `45:12`)
- **Format 1 hour and over:** `H:MM:SS` (e.g., `1:00:01`, `1:25:30`)
- **NEVER** write `60:01` or `75:30` — convert to `1:00:01`, `1:15:30`

### Step 8: Update YouTube metadata

Update video via YouTube Data API v3 `PUT /videos?part=snippet`:
- Title: generate from transcript content (concise, descriptive)
- Description: summary + timestamps block + relevant links
- Tags: extract key topics
- Category: `28` (Science & Technology) unless user specifies otherwise
- Language: from user or auto-detect

### Step 9: Clean up temp files

**MANDATORY. No large files left behind.**

```bash
rm -rf /tmp/yt-publisher-*/
```

Verify: `find /tmp -maxdepth 1 \( -name "*.mp4" -o -name "*.mp3" \) -size +1M` should return nothing.

## Script

Full automated pipeline:

```bash
python3 scripts/publish.py "DRIVE_URL" [--privacy unlisted] [--language ru] [--transcriber auto|fireworks|deepgram]
```

Options:
- `--privacy` — `public`, `unlisted` (default), `private`
- `--language` — language code for transcription (default: `ru`)
- `--transcriber` — force backend: `auto` (default), `fireworks`, `deepgram`
- `--skip-upload` — transcribe only, don't upload to YouTube
- `--video-id` — update existing video metadata instead of uploading new
- `--title` — override auto-generated title
- `--keep-files` — don't delete temp media files after processing

## Error Handling

- **OAuth expired:** refresh token automatically; if refresh fails, ask user to re-authorize
- **Drive 404:** file not shared or wrong ID — ask user to check sharing settings
- **YouTube quota exceeded:** daily upload limit is 6 videos — inform user, retry tomorrow
- **Transcription timeout:** retry failed chunk once; if still fails, skip and note gap
- **Large files (>2GB):** warn user about upload time; use chunked upload

## Timestamp Format Reference

- `0` → `0:00`
- `330` → `05:30`
- `2712` → `45:12`
- `3601` → `1:00:01`
- `4530` → `1:15:30`
- `7200` → `2:00:00`
