# 🎬 YouTube Publisher

**[🇷🇺 Читать на русском](README.ru.md)**

> One command. Google Drive link in → published YouTube video out.  
> With transcript, timestamps, and metadata. Fully automated.

---

## The Problem

You recorded a meeting, a lecture, a podcast. It's sitting in Google Drive. Now what?

1. Download the 2GB file to your machine
2. Open YouTube Studio, wait for upload
3. Think of a title, write a description
4. Manually scrub through the video to create timestamps
5. Copy-paste everything, hit publish
6. Delete the local file to free up space

**That's 30-60 minutes of boring work per video.** Multiply by dozens of recordings per month.

## The Solution

```bash
python3 scripts/publish.py "https://drive.google.com/file/d/abc123/view"
```

That's it. The script:

- ⬇️ **Downloads** from Google Drive (no local file juggling)
- 📤 **Uploads** directly to YouTube (resumable, handles large files)
- 🎤 **Transcribes** audio via Fireworks Whisper or Deepgram Nova-3
- ⏱️ **Generates timestamps** from topic boundaries
- 📝 **Creates title & description** from transcript content
- 🧹 **Cleans up** all temp files automatically

**Time: ~5 minutes for a 1-hour video** (mostly upload/transcribe, zero manual work).

## Quick Start

### 1. Clone

```bash
git clone https://github.com/smixs/youtube-publisher.git
cd youtube-publisher
```

### 2. Set Up Google OAuth

You need OAuth credentials for Google Drive (download) and YouTube (upload):

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or use an existing one)
3. Enable **Google Drive API** and **YouTube Data API v3**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Download the JSON file
5. Rename it to `google-oauth-client.json` and place in the `config/` folder
6. Run the auth flow once to generate `google-oauth-tokens.json`:

```bash
python3 scripts/setup_oauth.py
```

Required scopes:
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube`

### 3. Set Up Transcription

You need at least one transcription API key:

**Option A — Fireworks AI** (recommended: faster, $0.015/min)
```bash
export FIREWORKS_API_KEY=your_key_here
# or save to config/fireworks-api-key.txt
```

**Option B — Deepgram** (alternative: great quality)
```bash
export DEEPGRAM_API_KEY=your_key_here
# or save to config/deepgram-api-key.txt
```

### 4. Install ffmpeg

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

### 5. Run

```bash
python3 scripts/publish.py "https://drive.google.com/file/d/YOUR_FILE_ID/view"
```

## Usage

```bash
# Basic — upload as unlisted, auto-detect transcriber
python3 scripts/publish.py "DRIVE_URL"

# Public video with specific language
python3 scripts/publish.py "DRIVE_URL" --privacy public --language en

# Transcribe only, no YouTube upload
python3 scripts/publish.py "DRIVE_URL" --skip-upload

# Update metadata on existing video
python3 scripts/publish.py "DRIVE_URL" --video-id dQw4w9WgXcQ --title "My Video"

# Force specific transcription backend
python3 scripts/publish.py "DRIVE_URL" --transcriber deepgram

# Keep temp files for debugging
python3 scripts/publish.py "DRIVE_URL" --keep-files
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--privacy` | `unlisted` | `public`, `unlisted`, or `private` |
| `--language` | `ru` | Language code for transcription |
| `--transcriber` | `auto` | `auto`, `fireworks`, or `deepgram` |
| `--skip-upload` | — | Only transcribe, don't upload |
| `--video-id` | — | Update existing video instead of uploading |
| `--title` | — | Override auto-generated title |
| `--keep-files` | — | Don't delete temp files |
| `--category` | `28` | YouTube category ID |

## How It Works

```
Google Drive          YouTube             Transcription
     │                   │                     │
     ▼                   ▼                     ▼
 Download ──→ Upload ──→ Extract ──→ Split ──→ Transcribe
   .mp4       video      audio     15-min      (parallel)
                │        .mp3      chunks         │
                │                                  ▼
                │                            Merge + Generate
                │                            timestamps & meta
                │                                  │
                ▼                                  ▼
           Update video ◄──────────────── title, description,
           metadata                       tags, timestamps
                │
                ▼
           Clean up temp files
```

### Transcription Pipeline

- Audio extracted at 64kbps mono, 16kHz (optimized for speech, ~1MB/min)
- Split into 15-minute chunks for parallel processing (6 workers)
- Each chunk transcribed independently, then merged with time offsets
- Timestamps generated from topic boundaries (minimum 3-min gaps)

### Timestamp Format

| Duration | Format | Example |
|----------|--------|---------|
| Under 1 hour | `MM:SS` | `05:30`, `45:12` |
| 1 hour+ | `H:MM:SS` | `1:00:01`, `1:25:30` |

YouTube auto-links these in the description as chapters.

## API Key Lookup Order

The script searches for credentials in this order:

1. **Skill root** — `youtube-publisher/google-oauth-client.json`
2. **Config dir** — `youtube-publisher/config/google-oauth-client.json`
3. **Workspace** — `~/.openclaw/workspace/scripts/google-oauth-client.json`
4. **Environment variable** — `GOOGLE_OAUTH_CLIENT` (path to file)

Same order for API keys:
- `FIREWORKS_API_KEY` env → `config/fireworks-api-key.txt`
- `DEEPGRAM_API_KEY` env → `config/deepgram-api-key.txt`

## As an OpenClaw Skill

This repo is also an [OpenClaw](https://github.com/openclaw/openclaw) agent skill. Install it:

```bash
openclaw skill install youtube-publisher
```

Or copy the `SKILL.md` and `scripts/` to your workspace `skills/youtube-publisher/` directory.

The agent handles the full pipeline when you say things like:
- *"залей это видео на YouTube"*
- *"upload this Drive recording"*
- *"транскрибируй и опубликуй"*

## Requirements

- **Python 3.8+** (no pip packages needed — uses stdlib only)
- **ffmpeg** — audio extraction and splitting
- **Google Cloud project** with Drive API + YouTube Data API v3
- **At least one transcription key** (Fireworks or Deepgram)

## Limitations

- Source must be in Google Drive (no local file upload yet)
- YouTube daily upload quota: 6 videos
- Timestamp generation is heuristic-based (works best for structured content)
- Title/description generation is basic — agent or manual review recommended

## License

MIT

## Author

[Serge Shima](https://github.com/smixs) · [TDI Group](https://tdigroup.uz) · [AI Masters](https://aimasters.me)
