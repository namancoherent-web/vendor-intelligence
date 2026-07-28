"""Streamlit email login gate (24h session in st.session_state).

Current production path: work-email only (domain-checked, no OTP/password).
Password + OTP signup/login is implemented below but not wired into
require_login() yet — enable once company SMTP is ready.

Session token is kept in:
  1) st.session_state
  2) URL ``?s=`` (survives refresh on the same tab)
  3) browser cookie ``vi_auth`` (survives new tabs until Log out / 24h expiry)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import quote, unquote

import streamlit as st
import streamlit.components.v1 as components

from vendor_intel.auth.db import init_db
from vendor_intel.auth.service import (
    AuthError,
    complete_signup,
    list_auth_events,
    login_step1_password,
    login_step2_otp,
    login_without_otp,
    logout,
    request_otp,
    signup_request_otp,
    validate_session,
    verify_signup_otp,
)

_AUTH_COOKIE = "vi_auth"


def _ensure_db() -> None:
    if st.session_state.get("_auth_db_ready"):
        return
    init_db()
    st.session_state["_auth_db_ready"] = True


def _session_max_age_seconds() -> int:
    try:
        hours = int(os.getenv("AUTH_SESSION_HOURS") or "24")
    except ValueError:
        hours = 24
    return max(1, hours) * 3600


def _token_from_url() -> str | None:
    return st.query_params.get("s")


def _write_token_to_url(token: str) -> None:
    st.query_params["s"] = token


def _clear_token_from_url() -> None:
    st.query_params.pop("s", None)


def _token_from_cookie() -> str | None:
    try:
        raw = st.context.cookies.get(_AUTH_COOKIE)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return unquote(str(raw))
    except Exception:
        return str(raw)


def _set_auth_cookie(token: str) -> None:
    """Persist session across new tabs (parent page cookie + localStorage).

    ``components.html`` runs in an iframe — must write to ``window.parent`` or
    the cookie never lands on the real Cloud Run origin.
    """
    if not token or len(token) > 3500:
        return
    # Avoid re-injecting the same cookie script every rerun.
    if st.session_state.get("_auth_cookie_set_for") == token:
        return
    max_age = _session_max_age_seconds()
    safe = quote(token, safe="")
    components.html(
        f"""
        <script>
        (function() {{
          try {{
            var p = window.parent;
            var loc = p.location;
            var secure = (loc.protocol === 'https:') ? '; Secure' : '';
            var cookie = "{_AUTH_COOKIE}={safe}; path=/; max-age={max_age}; SameSite=Lax" + secure;
            p.document.cookie = cookie;
            p.localStorage.setItem("{_AUTH_COOKIE}", "{safe}");
          }} catch (e) {{}}
        }})();
        </script>
        """,
        height=1,
        width=1,
    )
    st.session_state["_auth_cookie_set_for"] = token


def _clear_auth_cookie() -> None:
    components.html(
        f"""
        <script>
        (function() {{
          try {{
            var p = window.parent;
            var secure = (p.location.protocol === 'https:') ? '; Secure' : '';
            p.document.cookie = "{_AUTH_COOKIE}=; path=/; max-age=0; SameSite=Lax" + secure;
            p.localStorage.removeItem("{_AUTH_COOKIE}");
          }} catch (e) {{}}
        }})();
        </script>
        """,
        height=1,
        width=1,
    )
    st.session_state.pop("_auth_cookie_set_for", None)


def _bootstrap_session_from_storage() -> None:
    """New tab with no ``?s=``: restore token from parent localStorage into the URL once."""
    if st.session_state.get("auth_token") or _token_from_url() or _token_from_cookie():
        return
    if st.session_state.get("_auth_storage_bootstrapped"):
        return
    st.session_state["_auth_storage_bootstrapped"] = True
    components.html(
        f"""
        <script>
        (function() {{
          try {{
            var p = window.parent;
            var t = p.localStorage.getItem("{_AUTH_COOKIE}");
            if (!t) return;
            var url = new URL(p.location.href);
            if (url.searchParams.get("s")) return;
            url.searchParams.set("s", decodeURIComponent(t));
            p.location.replace(url.toString());
          }} catch (e) {{}}
        }})();
        </script>
        """,
        height=1,
        width=1,
    )


def current_user() -> dict | None:
    """Return session user dict if valid; clear state if expired."""
    token = (
        st.session_state.get("auth_token")
        or _token_from_url()
        or _token_from_cookie()
    )
    if not token:
        return None
    try:
        _ensure_db()
        user = validate_session(token)
        # session_state is empty on a fresh reload even though the URL had a
        # valid token — repopulate it so the rest of the app (and the "Log
        # out" button) can keep reading from session_state as before.
        if not st.session_state.get("auth_token"):
            st.session_state["auth_token"] = token
            st.session_state["auth_email"] = user.email
            st.session_state["auth_user_id"] = user.user_id
            st.session_state["auth_role"] = user.role
            st.session_state["auth_expires_at"] = user.expires_at.isoformat()
        # Always keep ?s= in the URL so a WebSocket reconnect / refresh still
        # authenticates (otherwise Streamlit can look "logged out" mid-run).
        if _token_from_url() != token:
            _write_token_to_url(token)
        # Keep cookie in sync so a brand-new tab stays signed in.
        _set_auth_cookie(token)
        return {
            "user_id": user.user_id,
            "email": user.email,
            "role": user.role,
            "expires_at": user.expires_at,
        }
    except AuthError:
        for k in ("auth_token", "auth_email", "auth_user_id", "auth_role", "auth_expires_at"):
            st.session_state.pop(k, None)
        _clear_token_from_url()
        _clear_auth_cookie()
        return None


def _store_session(info) -> None:
    st.session_state["auth_token"] = info.token
    st.session_state["auth_email"] = info.email
    st.session_state["auth_user_id"] = info.user_id
    st.session_state["auth_role"] = info.role
    st.session_state["auth_expires_at"] = info.expires_at.isoformat()
    st.session_state["auth_step"] = "email"
    st.session_state.pop("auth_pending_email", None)
    _write_token_to_url(info.token)
    _set_auth_cookie(info.token)


def require_login() -> dict | None:
    """
    Show work-email sign-in until authenticated.
    Returns user dict when signed in; otherwise None (caller should stop rendering).
    """
    _ensure_db()
    # New tab often has no ?s= — restore from localStorage before showing Sign in.
    _bootstrap_session_from_storage()
    user = current_user()
    if user:
        _render_session_bar(user)
        return user

    # Email-only until SMTP + password/OTP are ready for production.
    _render_email_only_form()
    return None


def _render_email_only_form() -> None:
    """Domain-checked work email → session. No password, no OTP (no SMTP needed)."""
    st.markdown(
        '<div class="hero"><h1>Sign in</h1>'
        "<p>Enter your Coherent work email to continue. "
        "Sessions last 24 hours (stays signed in on new tabs until you log out).</p></div>",
        unsafe_allow_html=True,
    )
    email = st.text_input(
        "Work email",
        placeholder="username@coherentmarketinsights.com",
        key="login_email",
    )
    if st.button("Sign in", type="primary", width="stretch"):
        try:
            info = login_without_otp(email)
            _store_session(info)
            st.rerun()
        except AuthError as e:
            st.error(e.message)
        except Exception as e:
            st.error(f"Auth database unavailable: {e}")


# ---------------------------------------------------------------------------
# Password + OTP flows — kept for later (wire back into require_login when
# company SMTP is configured). Not used by the current email-only gate.
# ---------------------------------------------------------------------------

def _render_login_flow() -> None:
    step = st.session_state.get("login_step", "password")
    email_default = st.session_state.get("login_pending_email", "")

    if step == "password":
        email = st.text_input(
            "Work email",
            value=email_default,
            placeholder="username@coherentmarketinsights.com",
            key="login_email",
        )
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Continue", type="primary", width="stretch", key="login_continue"):
            try:
                login_step1_password(email, password)
                st.session_state["login_pending_email"] = email.strip().lower()
                st.session_state["login_step"] = "otp"
                st.success("Code sent — check your email.")
                st.rerun()
            except AuthError as e:
                st.error(e.message)
            except Exception as e:
                st.error(f"Auth database unavailable: {e}")
        return

    st.markdown(f"Code sent to **{st.session_state.get('login_pending_email', '')}**")
    code = st.text_input("6-digit code", max_chars=6, placeholder="123456", key="login_otp")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back", width="stretch", key="login_back"):
            st.session_state["login_step"] = "password"
            st.rerun()
    with c2:
        if st.button("Verify & log in", type="primary", width="stretch", key="login_verify"):
            try:
                info = login_step2_otp(st.session_state.get("login_pending_email", ""), code)
                _store_session(info)
                for k in ("login_step", "login_pending_email"):
                    st.session_state.pop(k, None)
                st.rerun()
            except AuthError as e:
                st.error(e.message)
    if st.button("Resend code", key="login_resend"):
        try:
            request_otp(st.session_state.get("login_pending_email", ""))
            st.success("A new code was sent.")
        except AuthError as e:
            st.error(e.message)


def _render_signup_flow() -> None:
    step = st.session_state.get("signup_step", "email")
    email_default = st.session_state.get("signup_pending_email", "")

    if step == "email":
        email = st.text_input(
            "Work email",
            value=email_default,
            placeholder="username@coherentmarketinsights.com",
            key="signup_email",
        )
        st.caption(
            "Recommended format: `username@coherentmarketinsights.com` "
            "(only this domain can sign up)."
        )
        if st.button("Send verification code", type="primary", width="stretch", key="signup_send"):
            try:
                signup_request_otp(email)
                st.session_state["signup_pending_email"] = email.strip().lower()
                st.session_state["signup_step"] = "otp"
                st.success("Code sent — check your email.")
                st.rerun()
            except AuthError as e:
                st.error(e.message)
            except Exception as e:
                st.error(f"Auth database unavailable: {e}")
        return

    if step == "otp":
        st.markdown(f"Code sent to **{st.session_state.get('signup_pending_email', '')}**")
        code = st.text_input("6-digit code", max_chars=6, placeholder="123456", key="signup_otp")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Back", width="stretch", key="signup_back"):
                st.session_state["signup_step"] = "email"
                st.rerun()
        with c2:
            if st.button("Verify email", type="primary", width="stretch", key="signup_verify"):
                try:
                    verify_signup_otp(st.session_state.get("signup_pending_email", ""), code)
                    st.session_state["signup_step"] = "password"
                    st.rerun()
                except AuthError as e:
                    st.error(e.message)
        if st.button("Resend code", key="signup_resend"):
            try:
                request_otp(st.session_state.get("signup_pending_email", ""))
                st.success("A new code was sent.")
            except AuthError as e:
                st.error(e.message)
        return

    st.markdown(f"Email verified: **{st.session_state.get('signup_pending_email', '')}**")
    pw1 = st.text_input("Choose a password", type="password", key="signup_pw1")
    pw2 = st.text_input("Confirm password", type="password", key="signup_pw2")
    st.caption("At least 8 characters.")
    if st.button("Create account", type="primary", width="stretch", key="signup_finish"):
        if pw1 != pw2:
            st.error("Passwords do not match.")
        else:
            try:
                info = complete_signup(st.session_state.get("signup_pending_email", ""), pw1)
                _store_session(info)
                for k in ("signup_step", "signup_pending_email"):
                    st.session_state.pop(k, None)
                st.rerun()
            except AuthError as e:
                st.error(e.message)


def _render_session_bar(user: dict) -> None:
    expires = user.get("expires_at")
    if isinstance(expires, datetime):
        exp_txt = expires.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    else:
        exp_txt = str(expires or "")
    left, right = st.columns([4, 1])
    with left:
        st.caption(f"Signed in as **{user['email']}** · session ends {exp_txt}")
    with right:
        if st.button("Log out", key="auth_logout"):
            token = st.session_state.get("auth_token")
            if token:
                try:
                    logout(token)
                except Exception:
                    pass
            for k in list(st.session_state.keys()):
                if k.startswith("auth_") or k in ("auth_token",):
                    st.session_state.pop(k, None)
            _clear_token_from_url()
            _clear_auth_cookie()
            st.rerun()

    if user.get("role") == "admin":
        with st.expander("Auth audit (admin)", expanded=False):
            try:
                events = list_auth_events(limit=50)
                st.dataframe(events, hide_index=True, width="stretch")
            except Exception as e:
                st.warning(str(e))
