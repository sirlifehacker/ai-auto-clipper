import json
import sys
import base64
from html import escape
from collections.abc import Callable
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from clipper.models import ClipCandidate, ClipStatus  # noqa: E402

RAW_DATA_DIR = Path("data/raw")
CANDIDATES_FILENAME = "ranked_clip_candidates.json"
APP_LOGO_PATH = Path("Clips Logo.png")
ProgressCallback = Callable[[str, str, int], None]


def inject_dashboard_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #F6F7FB;
            --card: #FFFFFF;
            --border: #E6E8EF;
            --text: #111827;
            --muted: #667085;
            --accent: #3B82F6;
            --accent-soft: #EAF2FF;
        }
        html, body, [data-testid="stAppViewContainer"] {
            background: var(--bg) !important;
            color: var(--text);
        }
        [data-testid="stHeader"], #MainMenu, footer {
            visibility: hidden;
            height: 0;
        }
        [data-testid="stSidebar"] {
            background: #FFFFFF;
            border-right: 1px solid var(--border);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding: 16px 12px 16px;
        }
        .block-container {
            padding-top: 16px;
            padding-bottom: 24px;
            max-width: 1400px;
        }
        .app-header {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .header-mark {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            object-fit: cover;
            border: 1px solid var(--border);
        }
        .dashboard-title {
            font-size: 2rem;
            line-height: 1.1;
            font-weight: 750;
            letter-spacing: -0.02em;
            margin: 0;
        }
        .section-title {
            font-size: 1.03rem;
            font-weight: 700;
            margin: 0 0 12px;
        }
        .muted {
            color: var(--muted);
            font-size: 0.85rem;
        }
        .soft-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
        }
        .clip-card {
            background: #FFFFFF;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 8px;
        }
        .clip-card.selected {
            border-color: var(--accent);
            background: var(--accent-soft);
        }
        .rank-badge {
            min-width: 28px;
            height: 28px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: #F9FAFB;
            color: #101828;
            font-size: 0.78rem;
            font-weight: 700;
            text-align: center;
            line-height: 28px;
        }
        .clip-title {
            font-size: 0.92rem;
            font-weight: 650;
            margin-bottom: 4px;
        }
        .clip-meta {
            color: var(--muted);
            font-size: 0.76rem;
        }
        .detail-label {
            color: var(--muted);
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 4px;
        }
        .score-total {
            background: #F9FAFB;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            text-align: center;
            font-weight: 700;
            color: #101828;
            font-size: 1.2rem;
        }
        .bar-row {
            display: grid;
            grid-template-columns: 112px 1fr 36px;
            align-items: center;
            gap: 8px;
            margin: 8px 0;
            font-size: 0.74rem;
            color: var(--muted);
            font-weight: 600;
        }
        .bar-track {
            height: 6px;
            border-radius: 999px;
            background: #E4E7EC;
            overflow: hidden;
        }
        .bar-fill {
            height: 100%;
            border-radius: 999px;
            background: #344054;
        }
        .sidebar-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 700;
            font-size: 1rem;
            margin-bottom: 16px;
        }
        .logo-mark {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            object-fit: cover;
            border: 1px solid var(--border);
        }
        .sidebar-section {
            color: var(--muted);
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
            margin: 16px 0 8px;
        }
        .nav-item {
            padding: 10px 10px;
            border-radius: 10px;
            color: #344054;
            font-weight: 600;
            font-size: 0.86rem;
            margin-bottom: 4px;
            border: 1px solid transparent;
        }
        .nav-item.active {
            background: #EEF4FF;
            color: #1D4ED8;
            border-color: #D1E0FF;
        }
        div[data-testid="stButton"] > button {
            border-radius: 10px;
            border: 1px solid var(--border);
            background: #FFFFFF;
            color: #344054;
            font-weight: 600;
            box-shadow: none;
        }
        div[data-testid="stButton"] > button:hover {
            border-color: #D0D5DD;
            background: #F9FAFB;
            color: #101828;
        }
        div[data-testid="stFormSubmitButton"] > button {
            border-radius: 10px;
            background: #101828;
            color: #FFFFFF;
            border: 1px solid #101828;
            font-weight: 650;
            box-shadow: none;
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: #101828;
            border-color: #101828;
            color: #FFFFFF;
            font-weight: 650;
        }
        input, textarea, [data-baseweb="select"] > div {
            background: #FFFFFF !important;
            border-color: var(--border) !important;
            border-radius: 10px !important;
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
        }
        input::placeholder, textarea::placeholder {
            color: #6B7280 !important;
            -webkit-text-fill-color: #6B7280 !important;
        }
        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea,
        [data-baseweb="select"] span,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
        }
        .insight-grid {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 12px;
            margin-top: 12px;
        }
        .insight-card {
            background: #FFFFFF;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            min-height: 120px;
        }
        .insight-card p {
            line-height: 1.45;
            margin-bottom: 0;
        }
        .preview-actions {
            margin-top: 12px;
        }
        .panel-title {
            font-size: 1.02rem;
            font-weight: 700;
            margin-bottom: 12px;
        }
        .status-chip {
            display: inline-flex;
            align-items: center;
            border: 1px solid #D1E9FF;
            color: #175CD3;
            background: #EFF8FF;
            border-radius: 999px;
            font-size: 0.73rem;
            padding: 4px 10px;
            font-weight: 600;
        }
        .clip-list-shell {
            background: #FFFFFF;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
        }
        .preview-shell {
            background: #FFFFFF;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
        }
        @media (max-width: 1100px) {
            .dashboard-title {
                font-size: 1.65rem;
            }
            .insight-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_shell() -> None:
    logo_src = logo_data_uri()
    st.sidebar.markdown(
        f"""
        <div class="sidebar-brand">
          <img class="logo-mark" alt="AI Auto Clipper logo" src="{logo_src}">
          <span>AI Auto Clipper</span>
        </div>
        <div class="nav-item">⬇ Download</div>
        <div class="nav-item">🎙 Transcribe</div>
        <div class="nav-item active">📊 Analyze</div>
        <div class="nav-item">✂ Clips</div>
        <div class="nav-item">👁 Review</div>
        <div class="nav-item">📤 Export</div>
        """,
        unsafe_allow_html=True,
    )


def logo_data_uri() -> str:
    if not APP_LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(APP_LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_plan_card() -> None:
    st.sidebar.markdown(
        """
        <div class="plan-card">
          <div style="font-weight: 850; margin-bottom: 0.25rem;">Pro Plan</div>
          <div class="muted">42 / 100 videos used</div>
          <div class="usage-track"><div class="usage-fill"></div></div>
          <div class="muted">Automation capacity resets monthly.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="AI Auto Clipper Review", layout="wide")
    inject_dashboard_css()
    render_sidebar_shell()
    render_youtube_ingestion()

    video_dirs = find_video_dirs()
    if not video_dirs:
        render_empty_state()
        return

    selected_dir = select_source_video(video_dirs)
    metadata = load_metadata(selected_dir)
    candidates_path = selected_dir / CANDIDATES_FILENAME
    candidates = load_candidates(candidates_path)

    render_dashboard_header(metadata, selected_dir)

    if not candidates:
        st.warning(f"No ranked clips found at {candidates_path}.")
        return

    selected_index = selected_clip_index(candidates)
    selected_candidate = candidates[selected_index]
    source_video_path = selected_dir / "source.mp4"

    render_clip_workspace(selected_index, selected_candidate, candidates, candidates_path, source_video_path)


def render_youtube_ingestion() -> None:
    st.sidebar.markdown('<div class="sidebar-section">New Project</div>', unsafe_allow_html=True)
    with st.sidebar.form("youtube_ingestion"):
        youtube_url = st.text_input("YouTube URL")
        max_candidates = st.number_input("Max clips", min_value=1, max_value=50, value=10, step=1)
        provider = st.selectbox("Analyzer provider", ["mock", "gemini"])
        render_raw_clips = st.checkbox("Render raw clip files after analysis", value=True)
        submitted = st.form_submit_button("Create Clips", type="primary")

    if not submitted:
        return

    if not youtube_url.strip():
        st.sidebar.error("Paste a YouTube URL first.")
        return

    progress_callback = build_sidebar_progress()
    try:
        progress_callback("Starting", "Preparing pipeline", 0)
        raw_video_dir = process_youtube_url(
            youtube_url.strip(),
            max_candidates=int(max_candidates),
            provider=provider,
            render_raw_clips=render_raw_clips,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        progress_callback("Failed", str(exc), 100)
        st.sidebar.error(f"Processing failed: {exc}")
        return

    progress_callback("Complete", f"Ready for review: {raw_video_dir.name}", 100)
    st.sidebar.success(f"Ready for review: {raw_video_dir.name}")
    st.rerun()


def build_sidebar_progress() -> ProgressCallback:
    progress_bar = st.sidebar.progress(0, text="Starting...")
    current_status = st.sidebar.empty()
    log_output = st.sidebar.empty()
    messages: list[str] = []

    def _report(stage: str, detail: str, percent: int) -> None:
        bounded_percent = max(0, min(100, int(percent)))
        label = f"{stage}: {detail}" if detail else stage
        progress_bar.progress(bounded_percent, text=label)
        current_status.info(f"**{stage}**\n\n{detail or 'Working...'}")
        if not messages or messages[-1] != label:
            messages.append(label)
        recent_messages = "\n".join(f"- {message}" for message in messages[-8:])
        log_output.markdown(f"#### Pipeline Progress\n{recent_messages}")

    return _report


def process_youtube_url(
    youtube_url: str,
    *,
    max_candidates: int,
    provider: str,
    render_raw_clips: bool,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    from clipper.analysis import find_clip_candidates, rank_candidates_with_video_analysis
    from clipper.download import download_video
    from clipper.processing.ffmpeg import trim_clip
    from clipper.transcription import transcribe_video, transcribe_youtube_captions

    report = progress_callback or (lambda stage, detail, percent: None)

    report("Downloading", "Fetching YouTube metadata", 2)
    download_result = download_video(
        youtube_url,
        progress_callback=lambda detail, percent: report(
            "Downloading",
            detail,
            _scale_progress(5, 25, percent),
        ),
    )
    raw_video_dir = Path(download_result["raw_dir"])
    source_video_path = Path(download_result["video_path"])
    metadata_path = raw_video_dir / "metadata.json"
    transcript_path = raw_video_dir / "transcript.json"
    candidates_path = raw_video_dir / "clip_candidates.json"
    ranked_candidates_path = raw_video_dir / CANDIDATES_FILENAME

    report("Transcribing", "Starting transcript generation", 26)
    transcript_result = transcribe_youtube_captions(
        youtube_url,
        str(raw_video_dir),
        progress_callback=lambda detail, percent: report(
            "Transcribing",
            detail,
            _scale_progress(26, 55, percent),
        ),
    )
    if transcript_result is None:
        report("Transcribing", "YouTube captions unavailable; falling back to faster-whisper", 26)
        transcribe_video(
            str(source_video_path),
            str(raw_video_dir),
            progress_callback=lambda detail, percent: report(
                "Transcribing",
                detail,
                _scale_progress(26, 55, percent),
            ),
        )
    report("Finding Clips", "Analyzing transcript for short-form moments", 56)
    find_clip_candidates(
        str(transcript_path),
        str(metadata_path),
        max_candidates=max_candidates,
        provider=provider,
        progress_callback=lambda detail, percent: report(
            "Finding Clips",
            detail.replace("candidate", "clip").replace("Candidate", "Clip"),
            _scale_progress(56, 68, percent),
        ),
    )

    report("Ranking", "Ranking clips from transcript analysis", 70)
    ranked_candidates = rank_candidates_with_video_analysis(
        str(candidates_path),
        None,
    )
    report("Ranking", f"Ranked {len(ranked_candidates)} clip(s)", 78)

    if render_raw_clips:
        raw_output_dir = Path("data/processed") / raw_video_dir.name / "clips"
        total_candidates = len(ranked_candidates)
        for index, candidate in enumerate(ranked_candidates, start=1):
            report(
                "Rendering",
                f"Trimming clip {index} of {total_candidates}: {candidate.suggested_clip_title}",
                _scale_progress(80, 98, (index - 1) / max(1, total_candidates) * 100),
            )
            trim_clip(str(source_video_path), candidate, str(raw_output_dir))
            report(
                "Rendering",
                f"Finished clip {index} of {total_candidates}",
                _scale_progress(80, 98, index / max(1, total_candidates) * 100),
            )
        save_candidates(ranked_candidates_path, ranked_candidates)
    else:
        save_candidates(ranked_candidates_path, ranked_candidates)

    return raw_video_dir


def _scale_progress(start: int, end: int, percent: float | None) -> int:
    if percent is None:
        return start
    bounded_percent = max(0.0, min(100.0, float(percent)))
    return int(start + (end - start) * (bounded_percent / 100.0))


def find_video_dirs() -> list[Path]:
    if not RAW_DATA_DIR.exists():
        return []
    return sorted(
        [path for path in RAW_DATA_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def select_source_video(video_dirs: list[Path]) -> Path:
    labels = {video_label(path): path for path in video_dirs}
    st.sidebar.markdown('<div class="sidebar-section">Current Project</div>', unsafe_allow_html=True)
    selected = st.sidebar.selectbox("Source video", list(labels.keys()))
    return labels[selected]


def video_label(video_dir: Path) -> str:
    metadata = load_metadata(video_dir)
    title = metadata.get("title") or video_dir.name
    return f"{title} ({video_dir.name})"


def load_metadata(video_dir: Path) -> dict:
    metadata_path = video_dir / "metadata.json"
    if not metadata_path.exists():
        return {"video_id": video_dir.name}
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def load_candidates(candidates_path: Path) -> list[ClipCandidate]:
    if not candidates_path.exists():
        return []
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        st.error(f"{candidates_path} must contain a JSON list.")
        return []
    return [ClipCandidate.model_validate(item) for item in payload]


def save_candidates(candidates_path: Path, candidates: list[ClipCandidate]) -> None:
    candidates_path.write_text(
        json.dumps([candidate.model_dump(mode="json") for candidate in candidates], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="soft-card" style="padding: 2rem;">
          <div class="dashboard-title">AI Auto Clipper</div>
          <p class="muted" style="margin-top: 0.75rem;">
            Add a YouTube URL from the sidebar to generate your first set of clips.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_header(metadata: dict, video_dir: Path) -> None:
    _ = metadata
    _ = video_dir
    logo_src = logo_data_uri()
    cols = st.columns([5, 1.6], gap="large")
    with cols[0]:
        st.markdown(
            f"""
            <div class="app-header">
              <div class="header-left">
                <img class="header-mark" alt="AI Auto Clipper logo" src="{logo_src}">
                <div>
                  <h1 class="dashboard-title">Analyze</h1>
                  <div class="muted" style="margin-top:4px;">Select top clips and review previews.</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        if st.button("Analyze New Video", type="primary", use_container_width=True, key="analyze_new_video_header"):
            st.info("Use the New Project form in the left sidebar to analyze a new video.")


def render_metadata(metadata: dict, video_dir: Path) -> None:
    st.subheader(metadata.get("title") or video_dir.name)
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        source_url = metadata.get("original_url") or metadata.get("url") or ""
        if source_url:
            st.link_button("Open Source URL", source_url)
        else:
            st.write("Source URL unavailable")
    with col2:
        st.metric("Duration", format_seconds(metadata.get("duration")))
    with col3:
        st.metric("Video ID", metadata.get("video_id") or video_dir.name)


def render_candidate_summary(candidates: list[ClipCandidate]) -> None:
    approved = sum(candidate.status == ClipStatus.APPROVED for candidate in candidates)
    rejected = sum(candidate.status == ClipStatus.REJECTED for candidate in candidates)
    final = sum(candidate.status == ClipStatus.FINAL for candidate in candidates)
    rendered = sum(
        bool(candidate.local_clip_path and Path(candidate.local_clip_path).exists())
        for candidate in candidates
    )
    high_potential = sum((candidate.final_score or candidate.scores.overall_score) >= 7 for candidate in candidates)
    uploaded = sum(bool(candidate.google_drive_url) for candidate in candidates)
    stats = [
        ("CC", len(candidates), "Clip Candidates"),
        ("HP", high_potential, "High Potential"),
        ("AP", approved, "Approved"),
        ("RD", rendered, "Rendered"),
        ("UP", uploaded, "Uploaded"),
    ]
    cols = st.columns(5)
    for col, (icon, value, label) in zip(cols, stats, strict=False):
        with col:
            st.markdown(
                f"""
                <div class="stat-card">
                  <div class="stat-icon">{icon}</div>
                  <div>
                    <div class="stat-number">{value}</div>
                    <div class="stat-label">{label}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_batch_actions(candidates: list[ClipCandidate], candidates_path: Path, source_video_path: Path) -> None:
    if st.button("Crop all clips to vertical", type="secondary"):
        crop_all_candidates(candidates, candidates_path, source_video_path)


def render_dashboard_actions(
    candidates: list[ClipCandidate],
    candidates_path: Path,
    source_video_path: Path,
    video_dir: Path,
) -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    cols = st.columns([1.15, 1.45, 5])
    with cols[0]:
        if st.button("Crop all clips", type="secondary"):
            crop_all_candidates(candidates, candidates_path, source_video_path)
    with cols[1]:
        render_visual_analysis_action(video_dir, candidates_path)


def render_visual_analysis_action(video_dir: Path, clips_path: Path) -> None:
    visual_analysis_path = video_dir / "visual_analysis.json"
    if visual_analysis_path.exists():
        st.caption("Visual analysis has been run for this video.")

    if not st.button("Run visual analysis and re-rank clips", type="secondary"):
        return

    source_video_path = video_dir / "source.mp4"
    metadata_path = video_dir / "metadata.json"
    transcript_path = video_dir / "transcript.json"
    if not source_video_path.exists():
        st.error(f"Source video not found: {source_video_path}")
        return
    if not metadata_path.exists() or not transcript_path.exists():
        st.error("Metadata or transcript is missing. Re-run clip generation first.")
        return

    try:
        from ai import analyze_video_with_gemini
        from clipper.analysis import rank_candidates_with_video_analysis

        with st.spinner("Running visual analysis with Gemini..."):
            analyze_video_with_gemini(str(source_video_path), str(metadata_path), str(transcript_path))
            rank_candidates_with_video_analysis(str(clips_path), str(visual_analysis_path))
    except Exception as exc:
        st.error(f"Visual analysis failed: {exc}")
        return

    st.success("Visual analysis complete. Clips were re-ranked.")
    st.rerun()


def selected_clip_index(candidates: list[ClipCandidate]) -> int:
    selected = int(st.session_state.get("selected_clip_index", 0))
    if selected < 0 or selected >= len(candidates):
        selected = 0
    return selected


def render_clip_workspace(
    selected_index: int,
    candidate: ClipCandidate,
    candidates: list[ClipCandidate],
    candidates_path: Path,
    source_video_path: Path,
) -> None:
    list_col, preview_col = st.columns([1, 1.45], gap="large")
    with list_col:
        render_clip_list(candidates, selected_index)
    with preview_col:
        render_clip_preview_panel(selected_index, candidate, len(candidates))
        with st.expander("Advanced Details", expanded=False):
            render_clip_details_panel(selected_index, candidate, candidates, candidates_path, source_video_path)


def render_clip_list(candidates: list[ClipCandidate], selected_index: int) -> None:
    st.markdown('<div class="clip-list-shell">', unsafe_allow_html=True)
    st.markdown('<div class="panel-title">Top Clips</div>', unsafe_allow_html=True)
    for index, candidate in enumerate(candidates):
        clip_path = (
            candidate.vertical_clip_path
            if candidate.vertical_clip_path and Path(candidate.vertical_clip_path).exists()
            else candidate.local_clip_path
        )
        card_class = "clip-card selected" if index == selected_index else "clip-card"
        st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
        row_cols = st.columns([0.5, 1.2, 2.7, 0.9], gap="small")
        with row_cols[0]:
            st.markdown(f'<div class="rank-badge">{index + 1}</div>', unsafe_allow_html=True)
        with row_cols[1]:
            # Clip paths are mp4 files, which st.image/PIL cannot decode.
            # Keep a lightweight visual placeholder in the list card.
            if clip_path and Path(clip_path).exists():
                st.markdown(
                    '<div style="height:56px;border:1px solid #E6E8EF;border-radius:8px;background:#F2F4F7;display:flex;align-items:center;justify-content:center;color:#667085;font-size:0.78rem;">Video</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div style="height:56px;border:1px solid #E6E8EF;border-radius:8px;background:#F9FAFB;display:flex;align-items:center;justify-content:center;color:#98A2B3;font-size:0.78rem;">No preview</div>',
                    unsafe_allow_html=True,
                )
        with row_cols[2]:
            st.markdown(
                f"""
                <div class="clip-title">{escape_html(candidate.suggested_clip_title or f"Clip {index + 1}")}</div>
                <div class="clip-meta">{int(candidate.duration_seconds)}s • Score {clip_score(candidate):.1f}</div>
                """,
                unsafe_allow_html=True,
            )
        with row_cols[3]:
            if st.button("Select", key=f"select_clip_{index}", use_container_width=True):
                st.session_state["selected_clip_index"] = index
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_clip_preview_panel(selected_index: int, candidate: ClipCandidate, total_candidates: int) -> None:
    score = clip_score(candidate)
    potential = "High Potential" if score >= 7 else "Ready"
    clip_path = (
        candidate.vertical_clip_path
        if candidate.vertical_clip_path and Path(candidate.vertical_clip_path).exists()
        else candidate.local_clip_path
    )
    clip_uri = Path(clip_path).resolve().as_uri() if clip_path and Path(clip_path).exists() else None
    st.markdown(
        f"""
        <div class="preview-shell">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px;">
            <div>
              <div class="panel-title" style="margin-bottom:4px;">Preview</div>
              <div class="muted">{escape_html(candidate.suggested_clip_title or "Untitled clip")} • {int(candidate.duration_seconds)}s</div>
            </div>
            <span class="status-chip">{potential}</span>
          </div>
        
        """,
        unsafe_allow_html=True,
    )
    if candidate.vertical_clip_path and Path(candidate.vertical_clip_path).exists():
        st.video(candidate.vertical_clip_path)
        st.caption("Vertical preview")
    elif candidate.local_clip_path and Path(candidate.local_clip_path).exists():
        st.video(candidate.local_clip_path)
        st.caption("Clip preview")
    else:
        st.info("No clip preview available yet.")

    action_cols = st.columns(2)
    with action_cols[0]:
        if clip_uri:
            st.link_button("Preview Full Clip", clip_uri, use_container_width=True)
        else:
            st.button("Preview Full Clip", use_container_width=True, disabled=True, key=f"preview_disabled_{selected_index}")
    with action_cols[1]:
        next_index = (selected_index + 1) % total_candidates
        if st.button("Next Clip", use_container_width=True, key=f"next_clip_{selected_index}"):
            st.session_state["selected_clip_index"] = next_index
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_clip_details_panel(
    index: int,
    candidate: ClipCandidate,
    candidates: list[ClipCandidate],
    candidates_path: Path,
    source_video_path: Path,
) -> None:
    st.markdown('<div class="section-title">Clip Details</div>', unsafe_allow_html=True)
    detail_cols = st.columns(2)
    with detail_cols[0]:
        st.markdown('<div class="detail-label">Start Time</div>', unsafe_allow_html=True)
        start_time = st.number_input(
            "Start Time",
            value=float(candidate.start_time),
            min_value=0.0,
            step=0.1,
            key=f"details_start_{index}",
            label_visibility="collapsed",
        )
    with detail_cols[1]:
        st.markdown('<div class="detail-label">End Time</div>', unsafe_allow_html=True)
        end_time = st.number_input(
            "End Time",
            value=float(candidate.end_time),
            min_value=float(start_time) + 0.1,
            step=0.1,
            key=f"details_end_{index}",
            label_visibility="collapsed",
        )

    duration = max(0.0, float(end_time) - float(start_time))
    st.markdown(f'<div class="muted" style="margin:0.45rem 0 0.85rem;">Duration: <b>{duration:.0f}s</b></div>', unsafe_allow_html=True)
    suggested_title = st.text_input("Suggested Title", value=candidate.suggested_clip_title, key=f"details_title_{index}")
    st.markdown('<div class="section-title" style="margin-top:0.9rem;">Why This Clip Was Chosen</div>', unsafe_allow_html=True)
    st.write(candidate.viral_reasoning or "No clip selection reasoning is available yet.")

    st.markdown('<div class="section-title" style="margin-top:1rem;">Viral Score Breakdown</div>', unsafe_allow_html=True)
    st.markdown(score_bar_html("Shock Value", candidate.scores.shock_value), unsafe_allow_html=True)
    st.markdown(score_bar_html("Emotional Impact", candidate.scores.emotional_intensity), unsafe_allow_html=True)
    st.markdown(score_bar_html("Curiosity Gap", candidate.scores.curiosity_gap), unsafe_allow_html=True)
    st.markdown(score_bar_html("Shareability", candidate.scores.shareability), unsafe_allow_html=True)
    st.markdown(score_bar_html("Clarity w/o Context", candidate.scores.clarity_without_context), unsafe_allow_html=True)
    st.markdown(score_bar_html("Hook Strength", candidate.scores.hook_strength), unsafe_allow_html=True)
    st.markdown(f'<div class="score-total">{clip_score(candidate):.1f} / 10</div>', unsafe_allow_html=True)

    editor_notes = st.text_area("Your Notes", value=candidate.editor_notes, key=f"details_notes_{index}", height=82)
    text_overlay_prompt = st.text_area(
        "Text Overlay Prompt",
        value=candidate.text_overlay_prompt,
        key=f"details_text_overlay_{index}",
        height=82,
    )
    vfx_prompt = st.text_area("VFX / Motion Prompt", value=candidate.vfx_prompt, key=f"details_vfx_{index}", height=82)

    updated_candidate = candidate.model_copy(
        update={
            "suggested_clip_title": suggested_title,
            "start_time": float(start_time),
            "end_time": float(end_time),
            "duration": round(duration, 2),
            "editor_notes": editor_notes,
            "text_overlay_prompt": text_overlay_prompt,
            "vfx_prompt": vfx_prompt,
        }
    )
    validation_errors = validate_candidate_timestamps(updated_candidate)
    if validation_errors:
        for error in validation_errors:
            st.error(error)

    if st.button("Save Details", key=f"details_save_{index}", use_container_width=True):
        if validation_errors:
            st.error("Fix timestamp errors before saving.")
        else:
            candidates[index] = updated_candidate
            save_candidates(candidates_path, candidates)
            st.success("Clip details saved.")
            st.rerun()

    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button("Approve", key=f"details_approve_{index}", use_container_width=True):
            candidates[index] = updated_candidate
            save_candidates(candidates_path, candidates)
            update_status(index, ClipStatus.APPROVED, candidates, candidates_path)
    with action_cols[1]:
        if st.button("Reject", key=f"details_reject_{index}", use_container_width=True):
            candidates[index] = updated_candidate
            save_candidates(candidates_path, candidates)
            update_status(index, ClipStatus.REJECTED, candidates, candidates_path)

    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button("Re-render Clip", key=f"details_rerender_{index}", use_container_width=True):
            rerender_candidate(index, updated_candidate, candidates, candidates_path, source_video_path)
    with action_cols[1]:
        if st.button("Send to After Effects", key=f"details_ae_{index}", use_container_width=True):
            candidates[index] = updated_candidate
            save_candidates(candidates_path, candidates)
            update_status(index, ClipStatus.AFTER_EFFECTS, candidates, candidates_path, note="Queued for After Effects.")


def render_candidate_card(
    index: int,
    candidate: ClipCandidate,
    candidates: list[ClipCandidate],
    candidates_path: Path,
) -> None:
    source_video_path = candidates_path.parent / "source.mp4"
    score = candidate.final_score if candidate.final_score is not None else candidate.scores.overall_score
    title = candidate.suggested_clip_title or f"Clip {index + 1}"
    with st.container(border=True):
        header_cols = st.columns([4, 1, 1])
        header_cols[0].subheader(title)
        header_cols[1].metric("Final Score", f"{score:.2f}")
        header_cols[2].markdown(f"**Status:** `{candidate.status.value}`")

        media_col, detail_col = st.columns([1, 2])
        with media_col:
            if candidate.vertical_clip_path and Path(candidate.vertical_clip_path).exists():
                st.video(candidate.vertical_clip_path)
                st.caption("Vertical preview")
            elif candidate.local_clip_path and Path(candidate.local_clip_path).exists():
                st.video(candidate.local_clip_path)
                st.caption("Raw clip preview")
            else:
                st.info("No clip preview available yet.")

            st.write(f"**Start:** {format_seconds(candidate.start_time)}")
            st.write(f"**End:** {format_seconds(candidate.end_time)}")
            st.write(f"**Duration:** {format_seconds(candidate.duration_seconds)}")
            if st.button("Crop to vertical", key=f"crop_{index}"):
                crop_candidate(index, candidate, candidates, candidates_path, source_video_path)

        with detail_col:
            render_scores(candidate)
            st.markdown("**Transcript excerpt**")
            st.write(candidate.transcript_excerpt)
            st.markdown("**Viral reasoning**")
            st.write(candidate.viral_reasoning)
            if candidate.visual_reasoning:
                st.markdown("**Visual reasoning**")
                st.write(candidate.visual_reasoning)
            if candidate.vertical_crop_notes:
                st.markdown("**Vertical crop notes**")
                st.write(candidate.vertical_crop_notes)

        with st.expander("Edit clip"):
            updated_candidate = render_candidate_editor(index, candidate)
            validation_errors = validate_candidate_timestamps(updated_candidate)
            if validation_errors:
                for error in validation_errors:
                    st.error(error)
            elif not is_recommended_duration(updated_candidate):
                st.warning("Recommended duration is 35-60 seconds. This clip is valid, but may perform less well.")

            if st.button("Save Edits", key=f"save_{index}", type="primary"):
                if validation_errors:
                    st.error("Fix timestamp errors before saving.")
                    return
                candidates[index] = updated_candidate
                save_candidates(candidates_path, candidates)
                st.success("Clip updated.")
                st.rerun()

            if st.button("Re-render clip", key=f"rerender_{index}"):
                if validation_errors:
                    st.error("Fix timestamp errors before re-rendering.")
                    return
                rerender_candidate(index, updated_candidate, candidates, candidates_path, source_video_path)

        action_cols = st.columns(4)
        if action_cols[0].button("Approve", key=f"approve_{index}"):
            update_status(index, ClipStatus.APPROVED, candidates, candidates_path)
        if action_cols[1].button("Reject", key=f"reject_{index}"):
            update_status(index, ClipStatus.REJECTED, candidates, candidates_path)
        if action_cols[2].button("Send to After Effects", key=f"ae_{index}"):
            update_status(index, ClipStatus.AFTER_EFFECTS, candidates, candidates_path, note="Queued for After Effects.")
        if action_cols[3].button("Mark as Final", key=f"final_{index}"):
            update_status(index, ClipStatus.FINAL, candidates, candidates_path)


def render_scores(candidate: ClipCandidate) -> None:
    score_cols = st.columns(4)
    score_cols[0].metric("Viral", f"{candidate.scores.overall_score:.2f}")
    score_cols[1].metric("Visual", format_optional_score(candidate.visual_score))
    score_cols[2].metric("Hook", f"{candidate.scores.hook_strength:.2f}")
    score_cols[3].metric("Share", f"{candidate.scores.shareability:.2f}")


def render_candidate_editor(index: int, candidate: ClipCandidate) -> ClipCandidate:
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("Clip title", value=candidate.suggested_clip_title, key=f"title_{index}")
        start_time = st.number_input("Start time", value=float(candidate.start_time), min_value=0.0, step=0.1, key=f"start_{index}")
        text_overlay_prompt = st.text_area(
            "Text overlay prompt",
            value=candidate.text_overlay_prompt,
            key=f"text_overlay_{index}",
            height=100,
        )
        editor_notes = st.text_area("Editor notes", value=candidate.editor_notes, key=f"notes_{index}", height=100)
    with col2:
        end_time = st.number_input(
            "End time",
            value=float(candidate.end_time),
            min_value=float(start_time) + 0.1,
            step=0.1,
            key=f"end_{index}",
        )
        viral_reasoning = st.text_area(
            "Viral reasoning",
            value=candidate.viral_reasoning,
            key=f"reasoning_{index}",
            height=130,
        )
        vfx_prompt = st.text_area("VFX prompt", value=candidate.vfx_prompt, key=f"vfx_{index}", height=100)

    return candidate.model_copy(
        update={
            "suggested_clip_title": title,
            "start_time": float(start_time),
            "end_time": float(end_time),
            "duration": round(float(end_time) - float(start_time), 2),
            "viral_reasoning": viral_reasoning,
            "text_overlay_prompt": text_overlay_prompt,
            "vfx_prompt": vfx_prompt,
            "editor_notes": editor_notes,
        }
    )


def update_status(
    index: int,
    status: ClipStatus,
    candidates: list[ClipCandidate],
    candidates_path: Path,
    note: str | None = None,
) -> None:
    candidate = candidates[index]
    notes = candidate.editor_notes
    if note and note not in notes:
        notes = f"{notes}\n{note}".strip()
    candidates[index] = candidate.model_copy(update={"status": status, "editor_notes": notes})
    save_candidates(candidates_path, candidates)
    st.success(f"Updated status to {status.value}.")
    st.rerun()


def rerender_candidate(
    index: int,
    candidate: ClipCandidate,
    candidates: list[ClipCandidate],
    candidates_path: Path,
    source_video_path: Path,
) -> None:
    render_candidate_clip(
        index,
        candidate,
        candidates,
        candidates_path,
        source_video_path,
        force_trim=True,
        success_message="Clip re-rendered and preview updated.",
    )


def crop_candidate(
    index: int,
    candidate: ClipCandidate,
    candidates: list[ClipCandidate],
    candidates_path: Path,
    source_video_path: Path,
) -> None:
    validation_errors = validate_candidate_timestamps(candidate)
    if validation_errors:
        for error in validation_errors:
            st.error(error)
        return

    render_candidate_clip(
        index,
        candidate,
        candidates,
        candidates_path,
        source_video_path,
        force_trim=False,
        success_message="Vertical crop rendered and preview updated.",
    )


def crop_all_candidates(candidates: list[ClipCandidate], candidates_path: Path, source_video_path: Path) -> None:
    if not source_video_path.exists():
        st.error(f"Source video not found: {source_video_path}")
        return

    cropped_count = 0
    skipped_count = 0
    try:
        with st.spinner("Cropping all clips to vertical..."):
            for candidate in candidates:
                if validate_candidate_timestamps(candidate):
                    skipped_count += 1
                    continue
                render_vertical_candidate(candidate, source_video_path, force_trim=False)
                cropped_count += 1
    except Exception as exc:
        st.error(f"Crop failed: {exc}")
        return

    save_candidates(candidates_path, candidates)
    message = f"Cropped {cropped_count} clip(s)."
    if skipped_count:
        message += f" Skipped {skipped_count} clip(s) with invalid timestamps."
    st.success(message)
    st.rerun()


def render_candidate_clip(
    index: int,
    candidate: ClipCandidate,
    candidates: list[ClipCandidate],
    candidates_path: Path,
    source_video_path: Path,
    *,
    force_trim: bool,
    success_message: str,
) -> None:
    if not source_video_path.exists():
        st.error(f"Source video not found: {source_video_path}")
        return

    try:
        with st.spinner("Rendering vertical clip with FFmpeg..."):
            render_vertical_candidate(candidate, source_video_path, force_trim=force_trim)
    except Exception as exc:
        st.error(f"Render failed: {exc}")
        return

    candidates[index] = candidate
    save_candidates(candidates_path, candidates)
    st.success(success_message)
    st.rerun()


def render_vertical_candidate(candidate: ClipCandidate, source_video_path: Path, *, force_trim: bool) -> ClipCandidate:
    from clipper.processing.ffmpeg import crop_to_vertical, trim_clip

    output_root = Path("data/processed") / candidate.source_video_id
    raw_output_dir = output_root / "clips"
    vertical_output_path = output_root / "vertical" / f"{clip_id(candidate)}_vertical.mp4"

    if force_trim or not candidate.local_clip_path or not Path(candidate.local_clip_path).exists():
        trim_clip(str(source_video_path), candidate, str(raw_output_dir))
    candidate.vertical_clip_path = crop_to_vertical(candidate.local_clip_path, str(vertical_output_path))
    return candidate


def validate_candidate_timestamps(candidate: ClipCandidate) -> list[str]:
    errors = []
    if candidate.start_time >= candidate.end_time:
        errors.append("Start time must be less than end time.")

    duration = candidate.end_time - candidate.start_time
    if duration < 20:
        errors.append("Duration must be at least 20 seconds.")
    if duration > 90:
        errors.append("Duration must be no more than 90 seconds.")
    return errors


def is_recommended_duration(candidate: ClipCandidate) -> bool:
    duration = candidate.end_time - candidate.start_time
    return 35 <= duration <= 60


def clip_id(candidate: ClipCandidate) -> str:
    title = "".join(char if char.isalnum() else "_" for char in candidate.suggested_clip_title or "clip")
    title = "_".join(part for part in title.lower().split("_") if part)
    start = int(round(candidate.start_time * 1000))
    end = int(round(candidate.end_time * 1000))
    return f"{candidate.source_video_id}_{start}_{end}_{title or 'clip'}"[:140].rstrip("_")


def render_next_steps(candidates: list[ClipCandidate]) -> None:
    approved = sum(candidate.status == ClipStatus.APPROVED for candidate in candidates)
    pending = sum(candidate.status == ClipStatus.CANDIDATE for candidate in candidates)
    ready_to_export = sum(candidate.status == ClipStatus.FINAL for candidate in candidates)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Next Steps</div>', unsafe_allow_html=True)
    cols = st.columns(3, gap="large")
    cards = [
        ("Review & Approve", "Approve the best clips to move to the next step.", f"{pending} pending"),
        ("Add Effects", "Send approved clips to After Effects via MCP.", f"{approved} approved"),
        ("Export & Upload", "Export final videos and upload to Google Drive.", f"{ready_to_export} ready"),
    ]
    for col, (title, body, count) in zip(cols, cards, strict=False):
        with col:
            st.markdown(
                f"""
                <div class="next-card">
                  <div class="section-title">{escape_html(title)}</div>
                  <p class="muted">{escape_html(body)}</p>
                  <div class="pill">{escape_html(count)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def clip_score(candidate: ClipCandidate) -> float:
    return float(candidate.final_score if candidate.final_score is not None else candidate.scores.overall_score)


def score_bar_html(label: str, score: float) -> str:
    safe_score = max(0.0, min(10.0, float(score)))
    width = safe_score * 10
    return f"""
    <div class="bar-row">
      <div>{escape_html(label)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:{width:.0f}%"></div></div>
      <div>{safe_score:.1f}</div>
    </div>
    """


def clip_tags(candidate: ClipCandidate) -> str:
    tags = []
    if candidate.scores.shareability >= 6:
        tags.append(("High shareability", "green"))
    if candidate.scores.hook_strength >= 6:
        tags.append(("Clear hook", ""))
    if candidate.scores.emotional_intensity >= 5:
        tags.append(("Emotional impact", ""))
    if candidate.scores.curiosity_gap >= 5:
        tags.append(("Strong retention", ""))
    if not tags:
        tags.append(("Ready to review", ""))
    return "".join(f'<span class="tag {css_class}">{escape_html(label)}</span>' for label, css_class in tags)


def format_duration_label(value: float | int | str | None) -> str:
    if value is None or value == "":
        return "Duration N/A"
    total_seconds = int(float(value))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"


def escape_html(value: object) -> str:
    return escape(str(value or ""))


def truncate_text(value: str, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rsplit(' ', 1)[0]}..."


def format_seconds(value: float | int | str | None) -> str:
    if value is None or value == "":
        return "N/A"
    seconds = float(value)
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def format_optional_score(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    main()
