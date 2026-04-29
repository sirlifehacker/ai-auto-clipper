# AI Auto Clipper

Python-based viral video clipper system for turning long-form YouTube videos into reviewed, vertical short-form clips.

This repository is intentionally scaffolded as a modular project. Most integrations are placeholders with TODOs so each module can be built, tested, and replaced independently.

## Planned Workflow

1. Accept one YouTube URL or a list of URLs.
2. Download source videos with `yt-dlp`.
3. Extract transcripts with Whisper or faster-whisper.
4. Analyze transcript and visual signals with a Gemini / Vertex AI-ready abstraction.
5. Select candidate 35-60 second clips based on viral potential.
6. Trim and crop clips to vertical format with FFmpeg.
7. Preview and approve clips in Streamlit.
8. Send selected clips to After Effects via MCP for overlays, motion graphics, and VFX.
9. Upload finished clips to Google Drive.
10. Log clip metadata and status in Notion.

## Project Structure

```text
.
├── data/
│   ├── clips/           # Rendered local clips
│   ├── downloads/       # Downloaded source videos
│   ├── jobs/            # SQLite database or JSON job state
│   └── transcripts/     # Transcript artifacts
├── src/
│   └── clipper/
│       ├── analysis/       # AI scoring and clip selection
│       ├── download/       # YouTube download logic
│       ├── integrations/   # After Effects MCP, Drive, Notion
│       ├── models/         # Shared dataclasses and domain types
│       ├── pipeline/       # End-to-end orchestration
│       ├── processing/     # FFmpeg trim/crop/render logic
│       ├── state/          # Local job persistence
│       └── transcription/  # Whisper/faster-whisper adapters
├── ui/
│   └── streamlit_app.py # Preview/review UI skeleton
├── .env.example
├── requirements.txt
└── README.md
```

## Installation (Windows — no coding required)

1. **Download or clone this repository** to a folder on your computer.
2. **Double-click `install.bat`** — it will:
   - Check that Python 3.11+ is installed (and tell you where to get it if not)
   - Create an isolated Python environment (`.venv`)
   - Install all dependencies automatically
   - Open `.env` in Notepad so you can add your API keys
3. **Fill in your API keys** in the `.env` file that opens (see Configuration below).
4. **Double-click `Start AI Auto Clipper.bat`** to launch the app — it opens automatically in your browser.

> To stop the app, press any key in the launcher window or close it.

## Configuration

Copy `.env.example` to `.env` (the installer does this automatically) and fill in:

| Key | Where to get it |
|-----|----------------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) |
| `GOOGLE_CLOUD_PROJECT` | Your GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to your service account JSON file |

## Developer Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

## Direct Gemini Video Analysis

`src/ai/video_analyzer.py` supports direct multimodal video analysis with Gemini Flash through Vertex AI. This is designed to inspect the video file itself for expressive faces, gestures, scene changes, on-screen text, visual risks, and short-form potential.

For local testing without credentials, keep:

```env
VIDEO_ANALYZER_PROVIDER=mock
```

For Vertex AI:

```env
VIDEO_ANALYZER_PROVIDER=vertex
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
VERTEX_VIDEO_MODEL=gemini-1.5-flash
GCS_TEMP_BUCKET=your-temporary-video-bucket
```

Long videos may exceed direct request limits. When that happens, the analyzer uploads the source video to `GCS_TEMP_BUCKET` and passes the `gs://` URI to Vertex AI. If the video is too large and no bucket is configured, the module falls back to the mock analyzer rather than extracting frames across the full video.

Output is saved beside the raw source video:

```text
data/raw/{video_id}/visual_analysis.json
```

## Build Order

1. Implement YouTube download in `src/clipper/download/youtube.py`.
2. Implement transcription in `src/clipper/transcription/transcriber.py`.
3. Implement AI clip scoring in `src/clipper/analysis/analyzer.py`.
4. Implement FFmpeg render logic in `src/clipper/processing/ffmpeg.py`.
5. Expand the Streamlit review flow in `ui/streamlit_app.py`.
6. Add After Effects MCP, Google Drive, and Notion integrations.
7. Upgrade JSON job state in `src/clipper/state/store.py` to SQLite if richer querying is needed.

## Notes

- Keep provider-specific code behind small adapter classes.
- Keep durable job state in `data/jobs` so failed jobs can resume.
- Avoid putting API keys or OAuth secrets in source control.
- Do not extract frames across entire long videos as the default visual analysis strategy. If frame extraction is added later, use it only around transcript-selected candidate moments.
