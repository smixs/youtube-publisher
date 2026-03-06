#!/usr/bin/env python3
"""
YouTube Publisher — full pipeline: Drive → YouTube → Transcribe → Metadata
Usage: python3 publish.py "https://drive.google.com/file/d/FILE_ID/view" [options]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))

# Google OAuth: check skill dir first, then workspace, then env
def _find_file(name, env_var=None):
    """Find a config file: skill dir → workspace/scripts → env var."""
    candidates = [
        SKILL_DIR / name,
        SKILL_DIR / "config" / name,
        SCRIPT_DIR / name,
        Path(WORKSPACE) / "scripts" / name,
    ]
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    for p in candidates:
        if p.exists():
            return str(p)
    return None

CLIENT_JSON = _find_file("google-oauth-client.json", "GOOGLE_OAUTH_CLIENT")
TOKENS_JSON = _find_file("google-oauth-tokens.json", "GOOGLE_OAUTH_TOKENS")

# API keys: env var → file in skill dir → file in workspace
def _read_key(env_var, *filenames):
    """Read API key from env var or fallback to file."""
    val = os.environ.get(env_var, "")
    if val:
        return val
    for fname in filenames:
        for d in [SKILL_DIR / "config", SKILL_DIR, SCRIPT_DIR, Path(WORKSPACE) / "scripts"]:
            p = d / fname
            if p.exists():
                return p.read_text().strip()
    return ""

DEEPGRAM_KEY = _read_key("DEEPGRAM_API_KEY", "deepgram-api-key.txt", "deepgram.key")
FIREWORKS_KEY = _read_key("FIREWORKS_API_KEY", "fireworks-api-key.txt", "fireworks.key")
CHUNK_DURATION = 900  # 15 minutes


def get_access_token():
    if not TOKENS_JSON or not os.path.exists(TOKENS_JSON):
        sys.exit("❌ google-oauth-tokens.json not found. See SKILL.md → Setup for instructions.")
    if not CLIENT_JSON or not os.path.exists(CLIENT_JSON):
        sys.exit("❌ google-oauth-client.json not found. See SKILL.md → Setup for instructions.")
    with open(TOKENS_JSON) as f:
        tokens = json.load(f)
    with open(CLIENT_JSON) as f:
        client = json.load(f)["installed"]

    data = urllib.parse.urlencode({
        "refresh_token": tokens["refresh_token"],
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "grant_type": "refresh_token"
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp["access_token"]


def extract_file_id(url):
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
        r"^([a-zA-Z0-9_-]{20,})$"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return url


def download_from_drive(file_id, output_dir, token):
    print(f"📥 Getting file metadata...")
    req = urllib.request.Request(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=name,size,mimeType"
    )
    req.add_header("Authorization", f"Bearer {token}")
    meta = json.loads(urllib.request.urlopen(req).read())

    name = meta.get("name", "video.mp4")
    size_mb = int(meta.get("size", 0)) / 1024 / 1024
    print(f"📄 {name} ({size_mb:.1f} MB, {meta.get('mimeType')})")

    output_path = os.path.join(output_dir, "source.mp4")
    print(f"📥 Downloading {size_mb:.0f} MB...")

    req = urllib.request.Request(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    )
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r, open(output_path, "wb") as f:
        shutil.copyfileobj(r, f)

    actual_size = os.path.getsize(output_path) / 1024 / 1024
    print(f"✅ Downloaded: {actual_size:.1f} MB")
    return output_path, name


def get_video_duration(video_path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def upload_to_youtube(video_path, token, privacy="unlisted", category="28"):
    print(f"📤 Uploading to YouTube ({privacy})...")

    metadata = {
        "snippet": {
            "title": "Processing...",
            "description": "Video is being processed. Title and description will be updated shortly.",
            "categoryId": category
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False
        }
    }

    meta_bytes = json.dumps(metadata).encode()
    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    req = urllib.request.Request(init_url, data=meta_bytes, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    req.add_header("X-Upload-Content-Type", "video/mp4")
    file_size = os.path.getsize(video_path)
    req.add_header("X-Upload-Content-Length", str(file_size))

    resp = urllib.request.urlopen(req)
    upload_url = resp.headers["Location"]

    with open(video_path, "rb") as f:
        req = urllib.request.Request(upload_url, data=f.read(), method="PUT")
        req.add_header("Content-Type", "video/mp4")
        req.add_header("Content-Length", str(file_size))
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())

    video_id = result["id"]
    print(f"✅ Uploaded: https://youtube.com/watch?v={video_id}")
    return video_id


def extract_audio(video_path, output_dir):
    audio_path = os.path.join(output_dir, "audio.mp3")
    print("🎵 Extracting audio (64kbps mono)...")
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "libmp3lame", "-ab", "64k", "-ar", "16000", "-ac", "1",
        audio_path, "-y"
    ], capture_output=True)
    size_mb = os.path.getsize(audio_path) / 1024 / 1024
    print(f"✅ Audio: {size_mb:.1f} MB")
    return audio_path


def split_audio(audio_path, output_dir, duration):
    num_chunks = int(duration // CHUNK_DURATION) + 1
    chunks = []
    for i in range(num_chunks):
        chunk_path = os.path.join(output_dir, f"chunk-{i}.mp3")
        start = i * CHUNK_DURATION
        subprocess.run([
            "ffmpeg", "-i", audio_path,
            "-ss", str(start), "-t", str(CHUNK_DURATION),
            "-c", "copy", chunk_path, "-y"
        ], capture_output=True)
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
            chunks.append((i, chunk_path))
    print(f"✅ Split into {len(chunks)} chunks")
    return chunks


def transcribe_chunk_fireworks(args):
    """Transcribe via Fireworks Whisper v3 Turbo — fast and cheap."""
    idx, chunk_path = args
    import io
    boundary = f"----FormBoundary{int(time.time()*1000)}"
    
    with open(chunk_path, "rb") as f:
        audio_data = f.read()
    
    body = io.BytesIO()
    # file field
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="file"; filename="chunk-{idx}.mp3"\r\n'.encode())
    body.write(b"Content-Type: audio/mp3\r\n\r\n")
    body.write(audio_data)
    body.write(b"\r\n")
    # model field
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="model"\r\n\r\n')
    body.write(b"whisper-v3-turbo\r\n")
    # language field
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="language"\r\n\r\n')
    body.write(b"ru\r\n")
    # response_format = verbose_json for timestamps
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="response_format"\r\n\r\n')
    body.write(b"verbose_json\r\n")
    # timestamp_granularities
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="timestamp_granularities[]"\r\n\r\n')
    body.write(b"segment\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    
    body_bytes = body.getvalue()
    
    req = urllib.request.Request(
        "https://audio-turbo.us-virginia-1.direct.fireworks.ai/v1/audio/transcriptions",
        data=body_bytes,
        method="POST"
    )
    req.add_header("Authorization", f"Bearer {FIREWORKS_KEY}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    return idx, result


def transcribe_chunk_deepgram(args):
    """Transcribe via Deepgram Nova-3."""
    idx, chunk_path = args

    with open(chunk_path, "rb") as f:
        audio_data = f.read()

    req = urllib.request.Request(
        "https://api.deepgram.com/v1/listen?model=nova-3&language=ru&smart_format=true&paragraphs=true&utterances=true&utt_split=0.8",
        data=audio_data,
        method="POST"
    )
    req.add_header("Authorization", f"Token {DEEPGRAM_KEY}")
    req.add_header("Content-Type", "audio/mp3")

    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    return idx, result


_TRANSCRIBER = "auto"  # set by main()

def transcribe_chunk(args):
    """Route to Fireworks or Deepgram based on --transcriber flag."""
    if _TRANSCRIBER == "fireworks" or (_TRANSCRIBER == "auto" and FIREWORKS_KEY):
        return transcribe_chunk_fireworks(args)
    elif _TRANSCRIBER == "deepgram" or (_TRANSCRIBER == "auto" and DEEPGRAM_KEY):
        return transcribe_chunk_deepgram(args)
    else:
        print("❌ No transcription API key set (FIREWORKS_API_KEY or DEEPGRAM_API_KEY)")
        return args[0], None


def merge_transcripts(results, chunk_duration=CHUNK_DURATION):
    paragraphs = []
    for idx, data in sorted(results, key=lambda x: x[0]):
        if data is None:
            continue
        offset = idx * chunk_duration

        # Fireworks Whisper format: {"segments": [{"start": ..., "text": ...}]}
        if "segments" in data:
            for seg in data["segments"]:
                start_sec = seg.get("start", 0) + offset
                text = seg.get("text", "").strip()
                if text:
                    paragraphs.append((start_sec, text))
        # Deepgram format: {"results": {"channels": [...]}}
        elif "results" in data:
            paras = (data.get("results", {}).get("channels", [{}])[0]
                     .get("alternatives", [{}])[0]
                     .get("paragraphs", {}).get("paragraphs", []))
            for para in paras:
                start_sec = para.get("start", 0) + offset
                sentences = [s.get("text", "") for s in para.get("sentences", [])]
                text = " ".join(sentences)
                paragraphs.append((start_sec, text))
        # Fallback: just text field (simple Whisper response)
        elif "text" in data:
            paragraphs.append((offset, data["text"].strip()))

    return paragraphs


def format_timestamp(seconds):
    """Format seconds to YouTube timestamp.
    Under 1h: MM:SS
    Over 1h: H:MM:SS
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def generate_metadata(paragraphs, source_name=""):
    """Generate title, description, timestamps from transcript."""
    # Build full text for analysis
    full_text = "\n".join([f"[{format_timestamp(ts)}] {text}" for ts, text in paragraphs])

    # Extract key topic changes for timestamps
    timestamps = []
    timestamps.append((0, "Начало"))

    # Find topic boundaries by scanning for key phrases
    last_ts = 0
    for ts, text in paragraphs:
        if ts - last_ts < 180:  # Min 3 min between timestamps
            continue
        text_lower = text.lower()
        if any(k in text_lower for k in [
            "давайте", "следующ", "перейдем", "разберем", "покажу",
            "расскажу", "вопрос", "тема", "итог", "еще один",
            "важный момент", "главн", "интересн"
        ]):
            # Take first ~60 chars as topic label
            label = text[:80].rstrip()
            if len(text) > 80:
                label = label.rsplit(" ", 1)[0] + "..."
            timestamps.append((ts, label))
            last_ts = ts

    # Format timestamps block
    ts_block = "\n".join([f"{format_timestamp(ts)} {label}" for ts, label in timestamps])

    return full_text, ts_block


def update_youtube_metadata(video_id, title, description, token, category="28", tags=None):
    print("📝 Updating YouTube metadata...")
    metadata = {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category,
            "defaultLanguage": "ru"
        }
    }
    if tags:
        metadata["snippet"]["tags"] = tags

    meta_bytes = json.dumps(metadata).encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/videos?part=snippet",
        data=meta_bytes, method="PUT"
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f"✅ Updated: {result['snippet']['title']}")
    return result


def main():
    parser = argparse.ArgumentParser(description="YouTube Publisher: Drive → YouTube → Transcript → Metadata")
    parser.add_argument("url", help="Google Drive URL or file ID")
    parser.add_argument("--privacy", default="unlisted", choices=["public", "unlisted", "private"])
    parser.add_argument("--category", default="28", help="YouTube category ID (28=Science&Tech)")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--keep-files", action="store_true", help="Keep temp files after processing")
    parser.add_argument("--title", help="Override auto-generated title")
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload, only transcribe")
    parser.add_argument("--video-id", help="Update existing YouTube video instead of uploading")
    parser.add_argument("--transcriber", default="auto", choices=["auto", "fireworks", "deepgram"],
                        help="Transcription backend (default: auto — Fireworks if key available, else Deepgram)")
    args = parser.parse_args()

    work_dir = tempfile.mkdtemp(prefix="yt-publisher-")
    print(f"📁 Working directory: {work_dir}")

    try:
        token = get_access_token()

        # Step 1: Download from Drive
        file_id = extract_file_id(args.url)
        video_path, source_name = download_from_drive(file_id, work_dir, token)

        # Step 2: Get duration
        duration = get_video_duration(video_path)
        mins = int(duration // 60)
        print(f"⏱ Duration: {mins} minutes")

        # Step 3: Upload to YouTube
        if args.video_id:
            video_id = args.video_id
            print(f"📺 Using existing video: {video_id}")
        elif not args.skip_upload:
            video_id = upload_to_youtube(video_path, token, args.privacy, args.category)
        else:
            video_id = None

        # Step 4: Extract audio
        audio_path = extract_audio(video_path, work_dir)

        # Step 5: Split into chunks
        chunks = split_audio(audio_path, work_dir, duration)

        # Step 6: Transcribe all chunks in parallel
        global _TRANSCRIBER
        _TRANSCRIBER = args.transcriber
        backend = "Fireworks Whisper" if (args.transcriber == "fireworks" or (args.transcriber == "auto" and FIREWORKS_KEY)) else "Deepgram Nova-3"
        print(f"🎤 Transcribing {len(chunks)} chunks via {backend}...")
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(transcribe_chunk, chunks))
        print("✅ Transcription complete")

        # Step 7: Merge transcripts
        paragraphs = merge_transcripts(results)

        # Step 8: Generate metadata
        full_text, ts_block = generate_metadata(paragraphs, source_name)

        # Save transcript
        transcript_path = os.path.join(work_dir, "transcript.txt")
        with open(transcript_path, "w") as f:
            f.write(full_text)
        print(f"📄 Transcript saved: {transcript_path}")

        # Save timestamps
        ts_path = os.path.join(work_dir, "timestamps.txt")
        with open(ts_path, "w") as f:
            f.write(ts_block)
        print(f"⏱ Timestamps saved: {ts_path}")

        # Print results
        print(f"\n{'='*60}")
        print(f"📺 Video: https://youtube.com/watch?v={video_id}" if video_id else "📺 Upload skipped")
        print(f"📄 Transcript: {transcript_path}")
        print(f"⏱ Timestamps:\n{ts_block}")
        print(f"{'='*60}")
        print(f"\n💡 Review transcript and timestamps, then update metadata:")
        print(f"   python3 {__file__} --video-id {video_id} --title 'Your Title' '{args.url}'" if video_id else "")

    finally:
        if not args.keep_files:
            # Clean ALL temp files — no binaries on VPS
            for f in os.listdir(work_dir):
                p = os.path.join(work_dir, f)
                if f.endswith((".mp4", ".mp3")):
                    os.remove(p)
            # Also clean any stray files in /tmp from manual runs
            import glob
            for pattern in ["meet-*.mp4", "meet-*.mp3", "meet-chunk-*.mp3",
                            "meet-transcript-*.json", "meet-full-transcript.txt"]:
                for f in glob.glob(os.path.join("/tmp", pattern)):
                    os.remove(f)
            print(f"🧹 Cleaned ALL temp media")
            print(f"📄 Transcript kept in {work_dir}")
            if video_id:
                print(f"\n💡 Next steps: review transcript, update title/description on YouTube")
                print(f"   Agent will handle metadata update and notes if configured.")


if __name__ == "__main__":
    main()
