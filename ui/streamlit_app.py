import streamlit as st

from clipper.config import get_settings
from clipper.state import JobStore


@st.cache_data
def load_recent_jobs(_store: JobStore) -> list:
    return _store.list_recent()


def main() -> None:
    st.set_page_config(page_title="AI Auto Clipper", layout="wide")
    st.title("AI Auto Clipper")

    settings = get_settings()
    store = JobStore(settings)

    st.sidebar.header("Create Job")
    with st.sidebar.form("new_project_form"):
        urls_text = st.text_area(
            "YouTube URLs",
            placeholder="Paste one URL per line",
            key="sidebar_youtube_urls",
        )
        submitted = st.form_submit_button("Create Clip Job")

    if submitted:
        urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
        if not urls:
            st.sidebar.error("Add at least one YouTube URL.")
        else:
            # TODO: Trigger the pipeline from a background worker instead of blocking Streamlit.
            st.sidebar.info("Pipeline execution is not wired yet.")

    st.header("Review Queue")
    try:
        jobs = load_recent_jobs(store)
    except NotImplementedError:
        st.info("Local job storage is not implemented yet. Jobs will appear here once JobStore is wired.")
        return

    for job in jobs:
        with st.expander(f"Job {job.id} - {job.status}"):
            st.write(f"URLs: {', '.join(job.urls)}")
            for render in job.renders:
                st.subheader(render.candidate.title)
                st.video(str(render.local_path))
                st.write(render.candidate.rationale)
                st.write(f"Viral score: {render.candidate.viral_score}")
                # TODO: Add approve/reject buttons and persist review decisions.


if __name__ == "__main__":
    main()
