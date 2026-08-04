"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, formatElapsed, type JobStatus, type Me } from "@/lib/api";
import { clearWizard, loadWizard, saveWizard, structureKeyFor } from "@/lib/wizardStore";
import styles from "./page.module.css";

type Cap = "focused" | "standard" | "broad";
type Step = 1 | 2 | 3;
type BriefMode = "write" | "generate" | "describe";

type SectionRow = { name: string; content: string };

const CAP_OPTIONS: { id: Cap; title: string; blurb: string }[] = [
  { id: "focused", title: "Focused", blurb: "~40–50 companies · faster" },
  { id: "standard", title: "Standard", blurb: "~80–100 companies" },
  { id: "broad", title: "Broad", blurb: "Largest sweep · longest run" },
];

const EMAIL_DOMAIN = "@coherentmarketinsights.com";

const PROFILE_PLACEHOLDER =
  "Function · core entities (example companies) · business model · market-sizing note (include / exclude)…";

const OVERVIEW_PLACEHOLDER =
  "e.g. This market covers … Participants range from … through … to …. For sizing, focus on … while … are counted separately.";

export default function HomePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [boot, setBoot] = useState(true);
  const [email, setEmail] = useState("");
  const [authError, setAuthError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);

  const [step, setStep] = useState<Step>(1);
  const [market, setMarket] = useState("");
  const [geography, setGeography] = useState("global");
  const [briefMode, setBriefMode] = useState<BriefMode>("write");
  const [sections, setSections] = useState<SectionRow[]>([{ name: "", content: "" }]);
  const [briefText, setBriefText] = useState("");
  const [structureKey, setStructureKey] = useState("");
  const [cap, setCap] = useState<Cap>("focused");
  const [wizError, setWizError] = useState("");
  const [wizInfo, setWizInfo] = useState("");
  const [sectionsBusy, setSectionsBusy] = useState(false);
  const [draftKey, setDraftKey] = useState(0);
  const [briefEditing, setBriefEditing] = useState(false);
  const [interpreted, setInterpreted] = useState<{
    sections: string[];
    definition: string;
    exclude: string[];
  } | null>(null);
  const [interpretBusy, setInterpretBusy] = useState(false);

  const [job, setJob] = useState<JobStatus | null>(null);
  const [jobBusy, setJobBusy] = useState(false);
  const [view, setView] = useState<"wizard" | "run" | "history">("wizard");
  const [historyTab, setHistoryTab] = useState<"yours" | "cloud">("yours");

  const [owned, setOwned] = useState<Array<Record<string, unknown>>>([]);
  const [cloud, setCloud] = useState<Array<Record<string, unknown>>>([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [downloadUrls, setDownloadUrls] = useState<Record<string, string>>({});
  const [downloadSlug, setDownloadSlug] = useState("");
  const [previewSlug, setPreviewSlug] = useState("");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [preview, setPreview] = useState<{
    slug: string;
    headers: string[];
    sections: Array<{ name: string; rows: Array<Record<string, string>> }>;
    company_count: number;
  } | null>(null);
  const [stopAt, setStopAt] = useState<number | null>(null);
  const [capacityReason, setCapacityReason] = useState<string | null>(null);
  const [instanceFull, setInstanceFull] = useState(false);

  const refreshCapacity = useCallback(async () => {
    try {
      const res = await api<{
        instance_full: boolean;
        reason: string | null;
      }>("/api/capacity");
      setInstanceFull(Boolean(res.instance_full));
      setCapacityReason(res.reason || null);
      return res;
    } catch {
      return null;
    }
  }, []);

  const refreshMe = useCallback(async () => {
    try {
      const user = await api<Me>("/api/auth/me");
      setMe(user);
      return user;
    } catch {
      setMe(null);
      return null;
    }
  }, []);

  useEffect(() => {
    (async () => {
      const user = await refreshMe();
      if (user) {
        const run = new URLSearchParams(window.location.search).get("run");
        const saved = loadWizard(user.email);
        if (saved) {
          setStep(saved.step);
          setMarket(saved.market);
          setGeography(saved.geography);
          setBriefMode(saved.briefMode);
          const key = structureKeyFor(saved.market, saved.geography);
          const savedKey = (saved.structureKey || "").trim();
          if (!savedKey || savedKey === key) {
            setSections(saved.sections);
            setBriefText(saved.briefText);
            setStructureKey(key);
          } else {
            setSections([{ name: "", content: "" }]);
            setBriefText("");
            setStructureKey("");
          }
          setCap(saved.cap);
        }
        if (run) {
          try {
            const j = await api<JobStatus>(`/api/jobs/${run}`);
            const live = Boolean(j.running && !j.cancelled && !j.cancel_requested);
            if (live) {
              // Still running (e.g. after deploy) — reconnect to the same job.
              setJob(j);
              setView("run");
            } else if (j.has_result && !j.cancelled) {
              // Finished successfully — show results.
              setJob(j);
              setView("run");
            } else {
              // User clicked Stop (or failed) — do not resume as a live run.
              setJob(null);
              setView(saved?.view === "history" ? "history" : "wizard");
              const u = new URL(window.location.href);
              u.searchParams.delete("run");
              window.history.replaceState({}, "", u.toString());
            }
          } catch {
            setView(saved?.view === "history" ? "history" : "wizard");
          }
        } else {
          try {
            const active = await api<{ job: JobStatus | null }>("/api/jobs");
            if (
              active.job?.running &&
              (!active.job.owner_email ||
                active.job.owner_email.toLowerCase() === user.email.toLowerCase())
            ) {
              setJob(active.job);
              setView("run");
              const u = new URL(window.location.href);
              u.searchParams.set("run", active.job.run_id);
              window.history.replaceState({}, "", u.toString());
            } else if (saved?.view === "history") {
              setView("history");
            } else {
              setView("wizard");
            }
          } catch {
            setView(saved?.view === "history" ? "history" : "wizard");
          }
        }
      }
      setBoot(false);
      if (user) void refreshCapacity();
    })();
  }, [refreshMe, refreshCapacity]);

  // Only poll capacity on Step 1 — banner shows solely when this instance is full.
  useEffect(() => {
    if (boot || !me || view !== "wizard" || step !== 1) return;
    void refreshCapacity();
    const id = window.setInterval(() => void refreshCapacity(), 15000);
    return () => window.clearInterval(id);
  }, [boot, me, view, step, refreshCapacity]);

  // Persist wizard so refresh / hard refresh restores Step 2/3 instead of Step 1.
  useEffect(() => {
    if (!me?.email || boot) return;
    saveWizard(me.email, {
      step,
      market,
      geography,
      briefMode,
      sections,
      briefText,
      structureKey,
      cap,
      view: view === "run" ? "wizard" : view,
    });
  }, [me?.email, boot, step, market, geography, briefMode, sections, briefText, structureKey, cap, view]);

  useEffect(() => {
    if (!job?.running || view !== "run") return;
    const id = window.setInterval(async () => {
      try {
        const j = await api<JobStatus>(`/api/jobs/${job.run_id}`);
        // Never let multi-instance polls jump the bar backwards.
        setJob((prev) => {
          if (!prev || prev.run_id !== j.run_id) return j;
          const phase = Math.max(Number(prev.phase) || 0, Number(j.phase) || 0);
          const progress_pct = Math.max(
            Number(prev.progress_pct) || 0,
            Number(j.progress_pct) || 0,
          );
          const elapsed_seconds = Math.max(
            Number(prev.elapsed_seconds) || 0,
            Number(j.elapsed_seconds) || 0,
          );
          return {
            ...j,
            phase,
            progress_pct,
            elapsed_seconds,
            phase_label:
              j.phase >= (prev.phase || 0) ? j.phase_label : prev.phase_label,
          };
        });
        if (j.running && (j.cancel_requested || stopAt)) {
          const age = stopAt
            ? (Date.now() - stopAt) / 1000
            : j.cancel_requested_at
              ? Date.now() / 1000 - Number(j.cancel_requested_at)
              : 0;
          if (age >= 8) {
            const forced = await api<JobStatus>(
              `/api/jobs/${job.run_id}/stop?force=true`,
              { method: "POST" },
            );
            setJob(forced);
            setStopAt(null);
            setWizInfo("");
          }
        }
        if (!j.running) {
          setStopAt(null);
          setWizInfo("");
          if (j.slug) {
            try {
              const d = await api<{ urls: Record<string, string> }>(
                `/api/runs/${encodeURIComponent(j.slug)}/downloads`,
              );
              setDownloadUrls(d.urls || {});
              setDownloadSlug(j.slug);
            } catch {
              /* ignore */
            }
          }
        }
      } catch {
        /* ignore transient */
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [job?.run_id, job?.running, view, stopAt]);

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setAuthError("");
    setAuthBusy(true);
    try {
      let local = email.trim().toLowerCase().replace(/\s+/g, "");
      if (local.includes("@")) {
        const [userPart, domainPart = ""] = local.split("@", 2);
        if (domainPart && `@${domainPart}` !== EMAIL_DOMAIN) {
          throw new Error(`Use your ${EMAIL_DOMAIN} work account`);
        }
        local = userPart;
      }
      local = local.replace(/^@+/, "").replace(/[^a-z0-9._+-]/g, "");
      if (!local) {
        throw new Error("Enter your work username (before @)");
      }
      const normalized = `${local}${EMAIL_DOMAIN}`;
      await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: normalized }),
      });
      await refreshMe();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setAuthBusy(false);
    }
  }

  async function onLogout() {
    if (me?.email) clearWizard(me.email);
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setMe(null);
    setJob(null);
    setView("wizard");
    setStep(1);
    setMarket("");
    setGeography("global");
    setBriefMode("write");
    setSections([{ name: "", content: "" }]);
    setBriefText("");
    setStructureKey("");
    setCap("focused");
    setWizError("");
    setWizInfo("");
    window.history.replaceState({}, "", "/");
  }

  function startNewSearch() {
    if (me?.email) clearWizard(me.email);
    setJob(null);
    setView("wizard");
    setStep(1);
    setMarket("");
    setGeography("global");
    setBriefMode("write");
    setSections([{ name: "", content: "" }]);
    setBriefText("");
    setStructureKey("");
    setCap("focused");
    setWizError("");
    setWizInfo("");
    setDownloadUrls({});
    window.history.replaceState({}, "", "/");
  }

  async function draftSections() {
    if (!market.trim()) {
      setWizError("Enter a market first.");
      return;
    }
    setSectionsBusy(true);
    setWizError("");
    setWizInfo("");
    try {
      const res = await api<{
        sections: Array<string | { name?: string; content?: string }>;
      }>("/api/brief/sections", {
        method: "POST",
        body: JSON.stringify({ market: market.trim(), geography: geography.trim() || "global" }),
      });
      const cards: SectionRow[] = [];
      for (const row of res.sections || []) {
        if (typeof row === "string") {
          const name = row.trim();
          if (name) cards.push({ name, content: "" });
          continue;
        }
        const name = String(row?.name || "").trim();
        const content = String(row?.content || "").trim();
        if (name) cards.push({ name, content });
      }
      if (!cards.length) {
        throw new Error("AI returned no sections. Try again in a moment.");
      }
      setSections(cards);
      setDraftKey((k) => k + 1);
      setStructureKey(structureKeyFor(market, geography));
      const withNotes = cards.filter((c) => c.content).length;
      setWizInfo(
        withNotes
          ? `Drafted ${cards.length} sections with what-to-profile notes — review and edit, then continue.`
          : `Drafted ${cards.length} section names — add what-to-profile notes, then continue.`,
      );
    } catch (err) {
      setWizError(err instanceof Error ? err.message : "Could not draft sections");
    } finally {
      setSectionsBusy(false);
    }
  }

  async function draftFullBrief() {
    if (!market.trim()) {
      setWizError("Enter a market first.");
      return;
    }
    setSectionsBusy(true);
    setWizError("");
    setWizInfo("");
    try {
      const res = await api<{ brief: string }>("/api/brief/generate", {
        method: "POST",
        body: JSON.stringify({ market: market.trim(), geography: geography.trim() || "global" }),
      });
      const text = (res.brief || "").trim();
      if (!text) {
        throw new Error("Could not generate a draft. Switch to 'Write it myself'.");
      }
      setBriefText(text);
      setStructureKey(structureKeyFor(market, geography));
      setWizInfo("AI draft ready — review, edit if needed, then continue.");
    } catch (err) {
      setWizError(err instanceof Error ? err.message : "Could not draft brief");
    } finally {
      setSectionsBusy(false);
    }
  }

  function clearStructureDraft() {
    setSections([{ name: "", content: "" }]);
    setBriefText("");
    setStructureKey("");
    setInterpreted(null);
    setDraftKey((k) => k + 1);
    setWizInfo("");
  }

  function onMarketChange(value: string) {
    const prev = market;
    setMarket(value);
    if (value.trim().toLowerCase() === prev.trim().toLowerCase()) return;
    // Any market change invalidates previous Write/Generate/Describe drafts.
    if (sections.some((s) => s.name.trim() || s.content.trim()) || briefText.trim() || structureKey) {
      clearStructureDraft();
    }
  }

  function onGeographyChange(value: string) {
    const prev = geography;
    setGeography(value);
    if ((value || "global").trim().toLowerCase() === (prev || "global").trim().toLowerCase()) return;
    if (sections.some((s) => s.name.trim() || s.content.trim()) || briefText.trim() || structureKey) {
      clearStructureDraft();
    }
  }

  function goStep2() {
    setWizError("");
    setWizInfo("");
    if (!market.trim()) {
      setWizError("Market is required.");
      return;
    }
    const key = structureKeyFor(market, geography);
    if (structureKey && structureKey !== key) {
      clearStructureDraft();
    }
    setStep(2);
  }

  function goStep3() {
    setWizError("");
    setWizInfo("");
    if (briefMode === "write") {
      const clean = sections.filter((s) => s.name.trim());
      if (!clean.length) {
        setWizError("Add at least one section name.");
        return;
      }
    } else if (!briefText.trim()) {
      setWizError(
        briefMode === "generate"
          ? "Generate or paste a market structure brief to continue."
          : "Write a short overview to continue.",
      );
      return;
    }
    setInterpreted(null);
    setStep(3);
  }

  // Step 3: interpret free-form / AI brief into sections (same as Streamlit review).
  useEffect(() => {
    if (boot || step !== 3 || view !== "wizard") return;
    if (briefMode === "write") {
      setInterpreted(null);
      return;
    }
    const brief = briefText.trim();
    if (!brief) return;
    let cancelled = false;
    (async () => {
      setInterpretBusy(true);
      setWizError("");
      try {
        const res = await api<{
          sections: string[];
          definition: string;
          exclude: string[];
        }>("/api/brief/interpret", {
          method: "POST",
          body: JSON.stringify({
            brief,
            market: market.trim(),
            geography: geography.trim() || "global",
          }),
        });
        if (!cancelled) {
          setInterpreted({
            sections: res.sections || [],
            definition: res.definition || "",
            exclude: res.exclude || [],
          });
        }
      } catch (err) {
        if (!cancelled) {
          setInterpreted({ sections: [], definition: "", exclude: [] });
          setWizError(err instanceof Error ? err.message : "Could not interpret brief");
        }
      } finally {
        if (!cancelled) setInterpretBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [boot, step, view, briefMode, briefText, market, geography]);

  // If market/geo no longer matches the draft they came from, wipe Step 2 structure.
  useEffect(() => {
    if (boot || !structureKey) return;
    const key = structureKeyFor(market, geography);
    if (key !== structureKey) {
      clearStructureDraft();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional market/geo guard
  }, [boot, market, geography, structureKey]);

  function buildBriefAndSections(): { brief: string; sections: string[] } {
    if (briefMode === "describe" || briefMode === "generate") {
      return { brief: briefText.trim(), sections: [] };
    }
    const clean = sections.filter((s) => s.name.trim());
    const lines: string[] = [];
    for (const row of clean) {
      lines.push(row.name.trim());
      if (row.content.trim()) lines.push(row.content.trim());
      lines.push("");
    }
    return {
      brief: lines.join("\n").trim(),
      sections: clean.map((s) => s.name.trim()),
    };
  }

  async function startJob() {
    setJobBusy(true);
    setWizError("");
    try {
      const built = buildBriefAndSections();
      const j = await api<JobStatus>("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          market: market.trim(),
          geography: geography.trim() || "global",
          cap,
          brief: built.brief,
          sections: built.sections,
        }),
      });
      setJob(j);
      setView("run");
      const u = new URL(window.location.href);
      u.searchParams.set("run", j.run_id);
      window.history.replaceState({}, "", u.toString());
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not start run";
      // Capacity / own-run banners live on Step 1 — not Step 3.
      if (/at capacity|already have a landscape running|other people's landscapes/i.test(msg)) {
        setWizError("");
        setStep(1);
        const ownRun = /already have a landscape running/i.test(msg);
        if (ownRun) {
          setInstanceFull(false);
          setCapacityReason(null);
          setWizInfo(msg.replace(/\*\*/g, ""));
          // Attach YOUR active job so Current run works.
          try {
            const active = await api<{ job: JobStatus | null }>("/api/jobs");
            if (
              active.job?.running &&
              active.job.owner_email?.toLowerCase() === me?.email?.toLowerCase()
            ) {
              setJob(active.job);
              const u = new URL(window.location.href);
              u.searchParams.set("run", active.job.run_id);
              window.history.replaceState({}, "", u.toString());
            }
          } catch {
            /* ignore */
          }
        } else {
          setInstanceFull(true);
          setCapacityReason(msg.replace(/\*\*/g, ""));
          setWizInfo(
            "This server is full with other people's runs. Wait a few minutes, then Start again.",
          );
        }
        void refreshCapacity();
      } else {
        setWizError(msg);
      }
    } finally {
      setJobBusy(false);
    }
  }

  async function stopJob(force = false) {
    if (!job) return;
    setJobBusy(true);
    setWizError("");
    if (!force) setStopAt(Date.now());
    try {
      const path = force
        ? `/api/jobs/${job.run_id}/stop?force=true`
        : `/api/jobs/${job.run_id}/stop`;
      const j = await api<JobStatus>(path, { method: "POST" });
      setJob(j);
      setStopAt(null);
      if (j.cancelled || !j.running) {
        setWizInfo("Run stopped.");
        const u = new URL(window.location.href);
        u.searchParams.delete("run");
        window.history.replaceState({}, "", u.toString());
      } else {
        setWizInfo("Stopping the run…");
      }
    } catch (err) {
      setWizError(err instanceof Error ? err.message : "Stop failed");
    } finally {
      setJobBusy(false);
    }
  }

  function goToStep(n: Step) {
    if (view !== "wizard") return;
    setWizError("");
    setWizInfo("");
    // Allow free navigation among completed steps; block jumping ahead without market.
    if (n >= 2 && !market.trim()) {
      setWizError("Enter a market in Step 1 first.");
      setStep(1);
      return;
    }
    if (n === 3) {
      if (briefMode === "write" && !sections.some((s) => s.name.trim())) {
        setWizError("Add sections in Step 2 before Review & run.");
        setStep(2);
        return;
      }
      if (briefMode !== "write" && !briefText.trim()) {
        setWizError("Complete Step 2 before Review & run.");
        setStep(2);
        return;
      }
    }
    setStep(n);
  }

  async function loadHistory(tab: "yours" | "cloud" = "yours") {
    setHistoryBusy(true);
    setHistoryTab(tab);
    setView("history");
    setPreview(null);
    setDownloadUrls({});
    setDownloadSlug("");
    try {
      const res = await api<{
        owned: Array<Record<string, unknown>>;
        cloud: Array<Record<string, unknown>>;
      }>("/api/runs");
      setOwned(res.owned || []);
      setCloud(res.cloud || []);
    } catch (err) {
      setWizError(err instanceof Error ? err.message : "Could not load history");
    } finally {
      setHistoryBusy(false);
    }
  }

  // A 401 here means the browser's session cookie is missing/invalid right now - it does NOT
  // mean the run failed (the run may have completed hours or days earlier under a session that
  // has since ended). Re-check the real session via refreshMe() and say so clearly, instead of
  // dumping the raw "Not signed in" string into the same banner used for actual run errors,
  // which used to render alongside an unrelated "Complete" result card and read as contradictory.
  async function handleAuthOrOtherError(err: unknown, fallback: string) {
    if (err instanceof ApiError && err.status === 401) {
      await refreshMe();
      setWizError("Your session has ended. Please sign in again to view or download this result.");
      return;
    }
    setWizError(err instanceof Error ? err.message : fallback);
  }

  async function openDownloads(slug: string) {
    setWizError("");
    setDownloadSlug(slug);
    try {
      const d = await api<{ urls: Record<string, string> }>(
        `/api/runs/${encodeURIComponent(slug)}/downloads`,
      );
      setDownloadUrls(d.urls || {});
      if (!Object.keys(d.urls || {}).length) {
        setWizError("No downloadable files found for this run.");
      }
    } catch (err) {
      await handleAuthOrOtherError(err, "Could not get downloads");
      setDownloadUrls({});
    }
  }

  async function openPreview(slug: string) {
    setWizError("");
    setPreviewBusy(true);
    setPreviewSlug(slug);
    try {
      const data = await api<{
        slug: string;
        headers: string[];
        sections: Array<{ name: string; rows: Array<Record<string, string>> }>;
        company_count: number;
      }>(`/api/runs/${encodeURIComponent(slug)}/preview`);
      setPreview(data);
      await openDownloads(slug);
    } catch (err) {
      setPreview(null);
      await handleAuthOrOtherError(err, "Could not open preview");
    } finally {
      setPreviewBusy(false);
    }
  }

  function runSlugFromRow(row: Record<string, unknown>): string {
    const direct = String(row.slug || "").trim();
    if (direct) return direct;
    const runId = String(row.run_id || "");
    if (runId.startsWith("gcs:")) return runId.slice(4);
    const csv = String(row.csv_file || "");
    if (csv) {
      const base = csv.replace(/\\/g, "/").split("/").pop() || "";
      return base.replace(/\.csv$/i, "");
    }
    return "";
  }

  if (boot) {
    return (
      <main className={styles.shell}>
        <p className={styles.muted}>Loading…</p>
      </main>
    );
  }

  if (!me) {
    return (
      <main className={styles.hero}>
        <div className={styles.heroGlow} aria-hidden />
        <div className={styles.heroInner}>
          <p className={styles.brandMark}>Coherent Market Insights</p>
          <h1 className={styles.brandTitle}>Vendor Intelligence</h1>
          <p className={styles.heroLead}>
            Map competitors, value-chain segments, and market structure — then download
            Excel and Word briefs when the run finishes.
          </p>
          <form className={styles.loginForm} onSubmit={onLogin}>
            <label className={styles.label} htmlFor="email">
              Work username
            </label>
            <div className={styles.emailRow}>
              <input
                id="email"
                type="text"
                className={styles.input}
                placeholder="your.name"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
              />
              <span className={styles.emailDomain} aria-hidden>
                {EMAIL_DOMAIN}
              </span>
            </div>
            <p className={styles.capacityTip}>
              Only type the part before @ — everyone signs in with {EMAIL_DOMAIN}
            </p>
            {authError ? <p className={styles.error}>{authError}</p> : null}
            <button className={styles.primaryBtn} type="submit" disabled={authBusy}>
              {authBusy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <div>
          <p className={styles.brandMarkCompact}>Vendor Intelligence</p>
          <p className={styles.muted}>{me.email}</p>
        </div>
        <nav className={styles.nav}>
          {!job?.running ? (
            <button type="button" className={styles.ghostBtn} onClick={startNewSearch}>
              New search
            </button>
          ) : null}
          <button
            type="button"
            className={styles.ghostBtn}
            onClick={() => void loadHistory("yours")}
          >
            Your runs
          </button>
          <button
            type="button"
            className={styles.ghostBtn}
            onClick={() => void loadHistory("cloud")}
          >
            Cloud files
          </button>
          {job ? (
            <button type="button" className={styles.ghostBtn} onClick={() => setView("run")}>
              Current run
            </button>
          ) : null}
          <button type="button" className={styles.ghostBtn} onClick={() => void onLogout()}>
            Sign out
          </button>
        </nav>
      </header>

      {wizError && !/at capacity/i.test(wizError) ? (
        <p className={styles.errorBanner}>{wizError}</p>
      ) : null}
      {wizInfo ? <p className={styles.infoBanner}>{wizInfo}</p> : null}

      {view === "wizard" ? (
        <section className={styles.panel}>
          <div className={styles.steps}>
            {([1, 2, 3] as Step[]).map((n) => (
              <button
                key={n}
                type="button"
                className={n === step ? styles.stepOn : styles.step}
                onClick={() => goToStep(n)}
              >
                Step {n}
              </button>
            ))}
          </div>

          {step === 1 ? (
            <div className={styles.block}>
              <h2>Market & geography</h2>
              <p className={styles.muted}>Name the landscape you want mapped.</p>
              {instanceFull && capacityReason ? (
                <p className={styles.warnBanner}>{capacityReason}</p>
              ) : null}
              <label className={styles.label} htmlFor="market">
                Market
              </label>
              <input
                id="market"
                className={styles.input}
                value={market}
                onChange={(e) => onMarketChange(e.target.value)}
                placeholder="e.g. Digital Pathology Software"
              />
              <label className={styles.label} htmlFor="geo">
                Geography
              </label>
              <input
                id="geo"
                className={styles.input}
                value={geography}
                onChange={(e) => onGeographyChange(e.target.value)}
                placeholder="global"
              />
              <div className={styles.rowEnd}>
                <button type="button" className={styles.primaryBtn} onClick={goStep2}>
                  Next
                </button>
              </div>
            </div>
          ) : null}

          {step === 2 ? (
            <div className={styles.block}>
              <h2>Step 2 — Market structure</h2>
              <p className={styles.muted}>
                Market: <strong>{market}</strong> · {geography || "global"}
              </p>
              <p className={styles.lead}>
                What are the different entities in the value chain based on functionality, and which
                should be considered for the <strong>market-sizing</strong> activity?
              </p>
              <p className={styles.hint}>
                Pick one path: fill section cards yourself, let AI draft a full brief to review, or
                paste a free-form overview.
              </p>
              <div className={styles.radioCol}>
                <label>
                  <input
                    type="radio"
                    checked={briefMode === "write"}
                    onChange={() => setBriefMode("write")}
                  />{" "}
                  Write it myself (default)
                </label>
                <label>
                  <input
                    type="radio"
                    checked={briefMode === "generate"}
                    onChange={() => setBriefMode("generate")}
                  />{" "}
                  Generate with AI, then review
                </label>
                <label>
                  <input
                    type="radio"
                    checked={briefMode === "describe"}
                    onChange={() => setBriefMode("describe")}
                  />{" "}
                  Describe it in your own words
                </label>
              </div>

              {briefMode === "write" ? (
                <>
                  <p className={styles.hint}>
                    Edit section names and describe what to profile under each.
                  </p>
                  <div className={styles.row}>
                    <button
                      type="button"
                      className={styles.secondaryBtn}
                      disabled={sectionsBusy}
                      onClick={() => void draftSections()}
                    >
                      {sectionsBusy ? "Drafting…" : "↻ Re-draft sections with AI"}
                    </button>
                    <button
                      type="button"
                      className={styles.secondaryBtn}
                      onClick={() => setSections((s) => [...s, { name: "", content: "" }])}
                    >
                      ➕ Add a section
                    </button>
                  </div>
                  {sectionsBusy ? (
                    <p className={styles.draftingNote} role="status" aria-live="polite">
                      Drafting the value-chain sections for this market… You can keep editing while
                      it runs; results will replace these fields when ready.
                    </p>
                  ) : null}
                  <div key={draftKey}>
                    {sections.map((row, i) => (
                      <div key={`${draftKey}-${i}`} className={styles.sectionCard}>
                        <label className={styles.label}>Section {i + 1} name</label>
                        <input
                          className={styles.input}
                          value={row.name}
                          placeholder="e.g. Device-Agnostic Platform Providers"
                          onChange={(e) => {
                            const next = [...sections];
                            next[i] = { ...next[i], name: e.target.value };
                            setSections(next);
                            setStructureKey(structureKeyFor(market, geography));
                          }}
                        />
                        <p className={styles.hint}>
                          Value-chain segment name — then short bullets: what this segment does,
                          example companies, and INCLUDE / EXCLUDE for sizing.
                        </p>
                        <label className={styles.label}>What to profile under section {i + 1}</label>
                        <textarea
                          className={styles.textarea}
                          rows={5}
                          placeholder={PROFILE_PLACEHOLDER}
                          value={row.content}
                          onChange={(e) => {
                            const next = [...sections];
                            next[i] = { ...next[i], content: e.target.value };
                            setSections(next);
                            setStructureKey(structureKeyFor(market, geography));
                          }}
                        />
                      </div>
                    ))}
                  </div>
                </>
              ) : null}

              {briefMode === "generate" ? (
                <>
                  <div className={styles.row}>
                    <button
                      type="button"
                      className={styles.primaryBtn}
                      disabled={sectionsBusy}
                      onClick={() => {
                        setBriefEditing(false);
                        void draftFullBrief();
                      }}
                    >
                      {sectionsBusy ? "Drafting…" : "✨ Generate structure with AI"}
                    </button>
                  </div>
                  {sectionsBusy ? (
                    <p className={styles.draftingNote} role="status" aria-live="polite">
                      Drafting the value-chain structure with AI…
                    </p>
                  ) : null}
                  {!briefText && !sectionsBusy ? (
                    <p className={styles.muted}>
                      Click <strong>Generate structure with AI</strong> to draft the value chain.
                    </p>
                  ) : null}
                  {briefText ? (
                    <>
                      <p className={styles.lead}>
                        <strong>AI-generated market structure — review it:</strong>
                      </p>
                      <textarea
                        className={styles.textarea}
                        rows={16}
                        value={briefText}
                        readOnly={!briefEditing}
                        onChange={(e) => setBriefText(e.target.value)}
                      />
                      <p className={styles.hint}>
                        {briefEditing
                          ? "Numbered functional entities with Function / Core entities / Business model / Include-exclude sizing notes."
                          : "Review the draft, then Edit or Use as-is."}
                      </p>
                      <div className={styles.rowBetween}>
                        <button
                          type="button"
                          className={styles.secondaryBtn}
                          onClick={() => setStep(1)}
                        >
                          ← Back
                        </button>
                        <div className={styles.row}>
                          {!briefEditing ? (
                            <button
                              type="button"
                              className={styles.secondaryBtn}
                              onClick={() => setBriefEditing(true)}
                            >
                              ✏️ Edit it
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className={styles.primaryBtn}
                            onClick={() => {
                              setBriefEditing(false);
                              goStep3();
                            }}
                          >
                            {briefEditing ? "Save & continue →" : "✅ Use as-is → continue"}
                          </button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className={styles.rowBetween}>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={() => setStep(1)}
                      >
                        ← Back
                      </button>
                    </div>
                  )}
                </>
              ) : null}

              {briefMode === "describe" ? (
                <>
                  <label className={styles.label} htmlFor="overview">
                    Market overview
                  </label>
                  <textarea
                    id="overview"
                    className={styles.textarea}
                    rows={12}
                    placeholder={OVERVIEW_PLACEHOLDER}
                    value={briefText}
                    onChange={(e) => setBriefText(e.target.value)}
                  />
                  <p className={styles.hint}>
                    1–3 short paragraphs covering scope, participant types, and sizing
                    include/exclude rules.
                  </p>
                  <div className={styles.rowBetween}>
                    <button type="button" className={styles.secondaryBtn} onClick={() => setStep(1)}>
                      ← Back
                    </button>
                    <button type="button" className={styles.primaryBtn} onClick={goStep3}>
                      Next →
                    </button>
                  </div>
                </>
              ) : null}

              {briefMode === "write" ? (
                <div className={styles.rowBetween}>
                  <button type="button" className={styles.secondaryBtn} onClick={() => setStep(1)}>
                    ← Back
                  </button>
                  <button type="button" className={styles.primaryBtn} onClick={goStep3}>
                    Next →
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 3 ? (
            <div className={styles.block}>
              <h2>Step 3 — Review & run</h2>
              <div className={styles.metricRow}>
                <div className={styles.metric}>
                  <span className={styles.metricLabel}>Market</span>
                  <strong>{market || "—"}</strong>
                </div>
                <div className={styles.metric}>
                  <span className={styles.metricLabel}>Geography</span>
                  <strong>{geography || "global"}</strong>
                </div>
              </div>
              <p className={styles.hint}>
                Results save as Excel + Word. Coverage only changes how many companies we search
                for — quality settings stay the same.
              </p>

              <label className={styles.label}>How many companies?</label>
              <div className={styles.capGrid}>
                {CAP_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={cap === opt.id ? styles.capOn : styles.cap}
                    onClick={() => setCap(opt.id)}
                  >
                    <strong>{opt.title}</strong>
                    <span>{opt.blurb}</span>
                  </button>
                ))}
              </div>
              <p className={styles.hint}>
                Fewer companies = faster run. Excel/Word quality rules are unchanged.
              </p>

              <h3 className={styles.reviewHeading}>Sections to profile</h3>
              {briefMode === "write" ? (
                <ul className={styles.reviewList}>
                  {sections
                    .filter((s) => s.name.trim())
                    .map((s, i) => (
                      <li key={`${s.name}-${i}`}>
                        <strong>{s.name}</strong>
                        {s.content.trim() ? (
                          <pre className={styles.reviewNote}>{s.content.trim()}</pre>
                        ) : null}
                      </li>
                    ))}
                </ul>
              ) : interpretBusy ? (
                <p className={styles.draftingNote} role="status">
                  Interpreting your market structure…
                </p>
              ) : interpreted?.sections?.length ? (
                <>
                  <ul className={styles.reviewList}>
                    {interpreted.sections.map((s) => (
                      <li key={s}>
                        <strong>{s}</strong>
                      </li>
                    ))}
                  </ul>
                  {interpreted.definition ? (
                    <p className={styles.infoBanner}>{interpreted.definition}</p>
                  ) : null}
                  {interpreted.exclude?.length ? (
                    <p className={styles.hint}>
                      Exclude / consolidate: {interpreted.exclude.join(", ")}
                    </p>
                  ) : null}
                </>
              ) : (
                <p className={styles.muted}>
                  No explicit sections detected — profiling the market generally.
                </p>
              )}

              {briefMode !== "write" && briefText.trim() ? (
                <details className={styles.reviewBrief}>
                  <summary>Full structure brief</summary>
                  <pre>{briefText.trim()}</pre>
                </details>
              ) : null}

              <div className={styles.rowBetween}>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  onClick={() => {
                    setWizInfo("");
                    setStep(2);
                  }}
                >
                  ← Back
                </button>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  disabled={jobBusy || interpretBusy}
                  onClick={() => void startJob()}
                >
                  {jobBusy ? "Starting…" : "Start run"}
                </button>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {view === "run" && job ? (
        <section className={styles.panel}>
          <h2>{job.query || market || "Landscape run"}</h2>
          <p className={styles.muted}>
            {job.country} · {job.cap} · {job.phase_label} · {formatElapsed(job.elapsed_seconds)}
          </p>
          <div className={styles.progressTrack}>
            <div
              className={styles.progressFill}
              style={{
                width: `${job.running ? job.progress_pct : job.has_result ? 100 : job.progress_pct}%`,
              }}
            />
          </div>
          <p className={styles.progressLabel}>
            {job.running
              ? job.cancel_requested || stopAt
                ? "Stopping…"
                : `${job.progress_pct}%`
              : job.cancelled
                ? "Stopped"
                : job.error
                  ? "Failed"
                  : "Complete"}
          </p>
          {job.error ? <p className={styles.error}>{job.error}</p> : null}
          <div className={styles.row}>
            {job.running ? (
              <button
                type="button"
                className={styles.dangerBtn}
                disabled={jobBusy || Boolean(job.cancel_requested || stopAt)}
                onClick={() => void stopJob()}
              >
                {job.cancel_requested || stopAt ? "Stopping…" : "⏹ Stop run"}
              </button>
            ) : null}
            {!job.running && job.slug ? (
              <>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  onClick={() => void openDownloads(job.slug)}
                >
                  Refresh downloads
                </button>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  disabled={previewBusy}
                  onClick={() => void openPreview(job.slug)}
                >
                  {previewBusy && previewSlug === job.slug ? "Loading preview…" : "Open preview tables"}
                </button>
                <button type="button" className={styles.ghostBtn} onClick={startNewSearch}>
                  New search
                </button>
              </>
            ) : null}
          </div>
          {!job.running && Object.keys(downloadUrls).length > 0 && downloadSlug === job.slug ? (
            <div className={styles.downloads}>
              <h3>Downloads</h3>
              <div className={styles.row}>
                {Object.entries(downloadUrls).map(([kind, url]) => (
                  <a
                    key={kind}
                    className={styles.downloadLink}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    ⬇ {kind === "xlsx" ? "Excel" : kind === "docx" ? "Word" : "CSV"}
                  </a>
                ))}
              </div>
            </div>
          ) : null}
          {preview && preview.slug === job.slug ? (
            <div className={styles.previewBox}>
              <h3>Preview · {preview.company_count} companies</h3>
              {preview.sections.map((sec) => (
                <div key={sec.name} className={styles.previewSection}>
                  <h4>{sec.name}</h4>
                  <div className={styles.tableWrap}>
                    <table>
                      <thead>
                        <tr>
                          {preview.headers.map((h) => (
                            <th key={h}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sec.rows.map((row, idx) => (
                          <tr key={idx}>
                            {preview.headers.map((h) => (
                              <td key={h}>{row[h] || ""}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {view === "history" ? (
        <section className={styles.panel}>
          <div className={styles.steps}>
            <button
              type="button"
              className={historyTab === "yours" ? styles.stepOn : styles.step}
              onClick={() => setHistoryTab("yours")}
            >
              Your runs
            </button>
            <button
              type="button"
              className={historyTab === "cloud" ? styles.stepOn : styles.step}
              onClick={() => setHistoryTab("cloud")}
            >
              Cloud files
            </button>
          </div>
          {historyTab === "cloud" ? (
            <p className={styles.muted}>
              Team shared storage — finished Excel/Word from everyone on this app.
            </p>
          ) : (
            <p className={styles.muted}>Only landscapes you started while signed in as you.</p>
          )}
          {historyBusy ? <p className={styles.muted}>Loading…</p> : null}

          {historyTab === "yours" ? (
            <>
              <h2>Search history — reopen past landscapes</h2>
              <p className={styles.hint}>
                Pick a previous market run to preview companies and download Excel / Word again.
              </p>
              <h3>Your previous searches</h3>
              <ul className={styles.list}>
                {owned.length === 0 ? (
                  <li className={styles.muted}>
                    No saved landscapes yet. After a successful run, it will appear here so you can
                    reopen and download Excel / Word again.
                  </li>
                ) : null}
                {owned.map((row, i) => {
                  const slug = runSlugFromRow(row);
                  const when = String(row.ran_at || "").slice(0, 16).replace("T", " ");
                  const n = row.companies_exported;
                  const nTxt = n != null ? `${n} companies` : "done";
                  return (
                    <li key={`${slug}-${i}`} className={styles.historyItem}>
                      <div>
                        <strong>{String(row.query || row.market || slug)}</strong>
                        <p className={styles.muted}>
                          {String(row.country || "global")} · {nTxt}
                          {when ? ` · ${when} UTC` : ""}
                        </p>
                      </div>
                      {slug ? (
                        <div className={styles.row}>
                          <button
                            type="button"
                            className={styles.secondaryBtn}
                            disabled={previewBusy}
                            onClick={() => void openPreview(slug)}
                          >
                            Open preview tables
                          </button>
                          <button
                            type="button"
                            className={styles.ghostBtn}
                            onClick={() => void openDownloads(slug)}
                          >
                            Downloads
                          </button>
                        </div>
                      ) : null}
                      {downloadSlug === slug && Object.keys(downloadUrls).length > 0 ? (
                        <div className={styles.downloadsInline}>
                          {Object.entries(downloadUrls).map(([kind, url]) => (
                            <a
                              key={kind}
                              className={styles.downloadLink}
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              ⬇ {kind === "xlsx" ? "Excel" : kind === "docx" ? "Word" : "CSV"}
                            </a>
                          ))}
                        </div>
                      ) : null}
                      {preview && preview.slug === slug ? (
                        <div className={styles.previewBox}>
                          <h4>Preview · {preview.company_count} companies</h4>
                          {preview.sections.map((sec) => (
                            <div key={sec.name} className={styles.previewSection}>
                              <strong>{sec.name}</strong>
                              <div className={styles.tableWrap}>
                                <table>
                                  <thead>
                                    <tr>
                                      {preview.headers.map((h) => (
                                        <th key={h}>{h}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {sec.rows.map((r, idx) => (
                                      <tr key={idx}>
                                        {preview.headers.map((h) => (
                                          <td key={h}>{r[h] || ""}</td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </>
          ) : (
            <>
              <h2>Cloud storage files — all finished Excel / Word</h2>
              <p className={styles.hint}>
                Every completed landscape uploaded to cloud storage appears here. Use this if Search
                history or the live run view is empty after a page reload.
              </p>
              <div className={styles.row}>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  disabled={historyBusy}
                  onClick={() => void loadHistory("cloud")}
                >
                  Refresh list
                </button>
              </div>
              <ul className={styles.list}>
                {cloud.length === 0 ? (
                  <li className={styles.muted}>No finished files in cloud storage yet.</li>
                ) : null}
                {cloud.map((row, i) => {
                  const slug = runSlugFromRow(row);
                  const when = String(row.ran_at || "").slice(0, 16).replace("T", " ");
                  const bits = [
                    row.xlsx_file || row.has_xlsx ? "Excel" : "",
                    row.docx_file || row.has_docx ? "Word" : "",
                    row.csv_file || row.has_csv ? "CSV" : "",
                  ].filter(Boolean);
                  return (
                    <li key={`${slug}-cloud-${i}`} className={styles.historyItem}>
                      <div>
                        <strong>{String(row.query || row.name || slug)}</strong>
                        <p className={styles.muted}>
                          {String(row.country || "global")} · {bits.join(", ") || "files"}
                          {when ? ` · ${when} UTC` : ""}
                        </p>
                      </div>
                      {slug ? (
                        <div className={styles.row}>
                          <button
                            type="button"
                            className={styles.secondaryBtn}
                            disabled={previewBusy}
                            onClick={() => void openPreview(slug)}
                          >
                            Open preview tables
                          </button>
                          <button
                            type="button"
                            className={styles.ghostBtn}
                            onClick={() => void openDownloads(slug)}
                          >
                            Downloads
                          </button>
                        </div>
                      ) : null}
                      {downloadSlug === slug && Object.keys(downloadUrls).length > 0 ? (
                        <div className={styles.downloadsInline}>
                          {Object.entries(downloadUrls).map(([kind, url]) => (
                            <a
                              key={kind}
                              className={styles.downloadLink}
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              ⬇ {kind === "xlsx" ? "Excel" : kind === "docx" ? "Word" : "CSV"}
                            </a>
                          ))}
                        </div>
                      ) : null}
                      {preview && preview.slug === slug ? (
                        <div className={styles.previewBox}>
                          <h4>Preview · {preview.company_count} companies</h4>
                          {preview.sections.map((sec) => (
                            <div key={sec.name} className={styles.previewSection}>
                              <strong>{sec.name}</strong>
                              <div className={styles.tableWrap}>
                                <table>
                                  <thead>
                                    <tr>
                                      {preview.headers.map((h) => (
                                        <th key={h}>{h}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {sec.rows.map((r, idx) => (
                                      <tr key={idx}>
                                        {preview.headers.map((h) => (
                                          <td key={h}>{r[h] || ""}</td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </section>
      ) : null}
    </main>
  );
}
