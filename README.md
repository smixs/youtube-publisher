# 🎬 YouTube Publisher

**[🇷🇺 Читать на русском](README.ru.md)**

<p align="center">
  <img src=".github/cover.jpg" alt="YouTube Publisher" width="600">
</p>

> An AI agent skill that turns "upload this recording to YouTube" into a fully automated pipeline.  
> Works with Claude Code, Codex, Gemini CLI, [OpenClaw](https://github.com/openclaw/openclaw), or any agent with terminal access.  
> Your agent downloads from Drive, uploads to YouTube, transcribes, generates timestamps and metadata — you just say the word.

---

## The Problem

You recorded a meeting, a lecture, a workshop. It's sitting in Google Drive. Now what?

You download a 2GB file, drag it into YouTube Studio, wait for the upload, try to come up with a decent title, scrub through an hour of video to place timestamps, write a description, copy-paste everything, publish, delete the local file. That's 30-60 minutes of mind-numbing work per recording — and you have dozens of them every month.

## The Solution

Tell your agent:

> *"Upload last Friday's recording to YouTube"*

The skill handles the entire pipeline:

- ⬇️ **Downloads** from Google Drive (no local file juggling)
- 📤 **Uploads** to YouTube (resumable, handles large files)
- 🎤 **Transcribes** audio via Fireworks Whisper or Deepgram Nova-3
- ⏱️ **Generates timestamps** from topic boundaries
- 📝 **Creates title & description** from transcript content
- 🧹 **Cleans up** all temp files automatically

**~5 minutes for a 1-hour video.** Zero manual work. The agent does everything.

## Install

### With Any AI Agent

The skill is two things: `SKILL.md` (instructions) and `scripts/` (code). Copy them into your agent's workspace:

```bash
git clone https://github.com/smixs/youtube-publisher.git

# Claude Code / Codex / Gemini CLI — into your project
mkdir -p skills/youtube-publisher
cp youtube-publisher/SKILL.md skills/youtube-publisher/
cp -r youtube-publisher/scripts skills/youtube-publisher/

# OpenClaw
cp -r youtube-publisher/{SKILL.md,scripts} ~/.openclaw/workspace/skills/youtube-publisher/
```

That's it — `SKILL.md` + `scripts/`. Everything else in this repo (README, LICENSE, .github) is packaging for GitHub, not part of the skill.

The agent reads `SKILL.md`, understands the pipeline, and runs it. Just say:
- *"залей запись созвона на ютуб"*
- *"upload this Drive recording"*
- *"транскрибируй и опубликуй"*

### As a Standalone CLI

The skill includes a Python script that works independently:

```bash
python3 scripts/publish.py "https://drive.google.com/file/d/abc123/view"
```

## Setup

### 1. Google OAuth (required)

You need OAuth credentials for Google Drive (download) and YouTube (upload):

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → enable **Google Drive API** and **YouTube Data API v3**
3. Create OAuth 2.0 credentials (Desktop app) → download JSON
4. Rename to `google-oauth-client.json`, place in the skill's root or `scripts/` folder
5. Run `python3 scripts/setup_oauth.py` to authorize (saves tokens next to client file)

Required scopes: `drive.readonly`, `youtube.upload`, `youtube`

### 2. Transcription API Key (at least one)

**Fireworks AI** (recommended: $0.0009/min — a 1-hour video costs 5 cents)
```bash
export FIREWORKS_API_KEY=your_key
# or save to skills/youtube-publisher/fireworks-api-key.txt
```

**Deepgram Nova-3** (alternative: $0.0077/min, great quality)
```bash
export DEEPGRAM_API_KEY=your_key
# or save to skills/youtube-publisher/deepgram-api-key.txt
```

### 3. ffmpeg

```bash
sudo apt install ffmpeg   # Ubuntu/Debian
brew install ffmpeg        # macOS
```

## How the Skill Works

The agent reads `SKILL.md` and follows the pipeline step by step:

```
Google Drive → Download → Upload to YouTube → Extract audio →
Split into 15-min chunks → Transcribe in parallel (6 workers) →
Merge transcript → Generate timestamps → Update YouTube metadata →
Clean up temp files
```

### Key Details

- Audio extracted at 64kbps mono, 16kHz (optimized for speech, ~1MB/min)
- Chunks transcribed in parallel, merged with time offsets
- Timestamps placed at topic boundaries (minimum 3-min gaps)
- YouTube auto-links timestamps as clickable chapters

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--privacy` | `unlisted` | `public`, `unlisted`, or `private` |
| `--language` | `ru` | Language code for transcription |
| `--transcriber` | `auto` | `auto`, `fireworks`, or `deepgram` |
| `--skip-upload` | — | Only transcribe, don't upload |
| `--video-id` | — | Update existing video metadata |
| `--title` | — | Override auto-generated title |

## Credential Lookup Order

The script searches for credentials in this order:

1. Skill root → `skills/youtube-publisher/`
2. Scripts dir → `skills/youtube-publisher/scripts/`
3. Workspace → `~/.openclaw/workspace/scripts/`
4. Environment variables

## Requirements

- **Python 3.8+** (stdlib only, no pip packages)
- **ffmpeg** on PATH
- **Google Cloud project** with Drive + YouTube APIs
- **Transcription key** (Fireworks or Deepgram)

## Limitations

- Source must be in Google Drive (no local file upload yet)
- YouTube daily upload quota: 6 videos
- Timestamp generation is heuristic (works best for structured content)
- Title/description generation is basic — agent review recommended

> **Optional add-on — separate from the YouTube pipeline**: when a source isn't a video headed for YouTube, e.g. you want to read a **web page** (including in-page video/attachments) or **several local files** into Markdown to pull material for a title/description or to check a short local recording, [cue-omni-reader](https://github.com/sensedeal/cue-skills/tree/main/cue-omni-reader) is an independent path: web pages + authorized local documents/audio/video → Markdown, multiple local files at once. Your existing Fireworks/Deepgram transcription and YouTube publishing are unaffected. Install: `npx skills add sensedeal/cue-skills --skill cue-omni-reader` (MIT; may bill).

## License

MIT

## Author

[Serge Shima](https://github.com/smixs) · [TDI Group](https://tdigroup.uz) · [AI Masters](https://aimasters.me)
