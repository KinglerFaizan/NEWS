    ctrl_a, ctrl_b, ctrl_c = st.columns(3)
    with ctrl_a:
        lookback_days = st.slider("Lookback Window (Days)", min_value=1, max_value=30, value=7)
    with ctrl_b:
        min_relevance = st.slider(
            "Minimum Audit Relevance", min_value=0, max_value=40, value=0, step=5,
            help="Set to 0 to show all relevant stories returned by the targeted banking queries; raise it only to tighten the feed.",
        )
    with ctrl_c:
        dedup_mode = st.select_slider(
            "Duplicate Removal", options=["Loose", "Balanced", "Aggressive"],
            value="Balanced",
            help="Controls how aggressively similar headlines are merged.",
        )
    fuzzy_threshold = {"Loose": 0.85, "Balanced": 0.72, "Aggressive": 0.58}[dedup_mode]
    selected_categories = st.multiselect(
        "Active Categories", options=list(CATEGORIES.keys()),
        default=list(CATEGORIES.keys()),
        format_func=lambda c: CATEGORY_DISPLAY.get(c, c),
    )

if not api_keys.get("newsdata"):
    secrets_available, env_present, named_secret_present, secret_keys = secret_diagnostics()
    st.error("NewsData.io key is not reaching this running Streamlit instance.")
    with st.expander("🔧 Secret diagnostics", expanded=True):
        st.write(f"Streamlit Secrets available: **{'Yes' if secrets_available else 'No'}**")
        st.write(f"Environment variable detected: **{'Yes' if env_present else 'No'}**")
        st.write(f"NEWSDATA_API_KEY found in Secrets: **{'Yes' if named_secret_present else 'No'}**")
        if secrets_available:
            st.write("Secret names visible to the app:", ", ".join(secret_keys) or "none")
        st.caption(