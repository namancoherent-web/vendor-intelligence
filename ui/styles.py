"""Custom CSS for the Vendor Intelligence Streamlit app."""

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    font-family: 'DM Sans', system-ui, sans-serif;
}
/* Do NOT set font-family on [class*="css"] — that breaks Streamlit Material
   icons and shows raw names like "_arrow_right" on expanders. */
span[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-symbols-outlined,
.material-icons {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons", sans-serif !important;
    font-style: normal !important;
    font-weight: normal !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
}

.hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 45%, #0d9488 100%);
    border-radius: 16px;
    padding: 2rem 2.25rem;
    margin-bottom: 1.5rem;
    color: #f8fafc;
    box-shadow: 0 20px 40px rgba(15, 23, 42, 0.25);
}
.hero h1 {
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 0.5rem 0;
    letter-spacing: -0.02em;
}
.hero p {
    margin: 0;
    opacity: 0.9;
    font-size: 1.05rem;
    line-height: 1.5;
}
.metric-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.1rem 1.25rem;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
}
.metric-card .label {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
    font-weight: 600;
}
.metric-card .value {
    font-size: 1.75rem;
    font-weight: 700;
    color: #0f172a;
    margin-top: 0.25rem;
}
.phase-pill {
    display: inline-block;
    background: #f0fdfa;
    color: #0f766e;
    border: 1px solid #99f6e4;
    border-radius: 999px;
    padding: 0.25rem 0.75rem;
    font-size: 0.8rem;
    font-weight: 600;
    margin-right: 0.35rem;
    margin-bottom: 0.35rem;
}
.section-head {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f172a;
    background: linear-gradient(90deg, #f0fdfa 0%, #ffffff 100%);
    border-left: 4px solid #0d9488;
    border-radius: 0 8px 8px 0;
    padding: 0.55rem 0.9rem;
    margin: 1.4rem 0 0.5rem 0;
}
.section-head .count {
    color: #0d9488;
    font-weight: 600;
    font-size: 0.95rem;
}
.status-ok { color: #059669; font-weight: 600; }
.status-warn { color: #d97706; font-weight: 600; }
.status-fail { color: #dc2626; font-weight: 600; }
.log-box {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    background: #0f172a;
    color: #e2e8f0;
    border-radius: 10px;
    padding: 1rem;
    max-height: 420px;
    overflow-y: auto;
    white-space: pre-wrap;
    line-height: 1.45;
}
.sidebar-brand {
    font-size: 1.1rem;
    font-weight: 700;
    color: #0f172a;
    padding: 0.5rem 0 1rem 0;
    border-bottom: 2px solid #0d9488;
    margin-bottom: 1rem;
}
.result-card {
    border-left: 4px solid #0d9488;
    background: #f8fafc;
    border-radius: 0 10px 10px 0;
    padding: 0.85rem 1rem;
    margin-bottom: 0.5rem;
}
div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0d9488, #0f766e);
    border: none;
    font-weight: 600;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    border: none;
}
.format-hint {
    display: block;
    margin: -0.35rem 0 0.85rem 0;
    padding: 0.45rem 0.75rem;
    background: #f0fdfa;
    border: 1px dashed #99f6e4;
    border-radius: 8px;
    color: #0f766e;
    font-size: 0.82rem;
    line-height: 1.4;
}
.format-hint strong {
    color: #0f766e;
}
.notice-banner {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-left: 4px solid #f59e0b;
    border-radius: 10px;
    padding: 0.85rem 1.1rem;
    margin: 0 0 1.25rem 0;
    color: #78350f;
    font-size: 0.95rem;
    line-height: 1.45;
}
.notice-banner strong {
    color: #92400e;
}
.status-steps {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin: 0.75rem 0 1rem 0;
}
.status-step {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    padding: 0.4rem 0;
    font-size: 0.98rem;
    color: #64748b;
}
.status-step.active {
    color: #0f172a;
    font-weight: 600;
}
.status-step.done {
    color: #0f766e;
}
.status-step .icon {
    width: 1.4rem;
    text-align: center;
    flex-shrink: 0;
}
.status-current {
    margin-top: 0.65rem;
    padding: 0.65rem 0.85rem;
    background: #f0fdfa;
    border: 1px solid #99f6e4;
    border-radius: 8px;
    color: #0f766e;
    font-weight: 600;
}
</style>
"""
