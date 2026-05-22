"""Placeholder Streamlit application for med-graph-rag."""

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional placeholder dependency
    st = None


def main() -> None:
    """Run the placeholder UI application."""
    if st is None:
        print("med-graph-rag UI placeholder")
        return

    st.set_page_config(page_title="med-graph-rag")
    st.title("med-graph-rag")
    st.write("Placeholder UI for the project skeleton.")


if __name__ == "__main__":
    main()
