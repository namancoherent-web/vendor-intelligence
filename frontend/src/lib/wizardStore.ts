export type WizardSnapshot = {
  step: 1 | 2 | 3;
  market: string;
  geography: string;
  briefMode: "write" | "generate" | "describe";
  sections: Array<{ name: string; content: string }>;
  briefText: string;
  /** Market+geo the sections/brief were drafted for — drop structure if this drifts. */
  structureKey?: string;
  cap: "focused" | "standard" | "broad";
  view: "wizard" | "run" | "history";
};

function storageKey(email: string): string {
  return `vi_wizard:${email.trim().toLowerCase()}`;
}

export function loadWizard(email: string): WizardSnapshot | null {
  if (typeof window === "undefined" || !email) return null;
  try {
    const raw = window.localStorage.getItem(storageKey(email));
    if (!raw) return null;
    const data = JSON.parse(raw) as Partial<WizardSnapshot>;
    const step = Number(data.step);
    if (![1, 2, 3].includes(step)) return null;
    const sections = Array.isArray(data.sections)
      ? data.sections
          .map((s) => ({
            name: String(s?.name || ""),
            content: String(s?.content || ""),
          }))
          .filter((s) => s.name || s.content)
      : [];
    return {
      step: step as 1 | 2 | 3,
      market: String(data.market || ""),
      geography: String(data.geography || "global") || "global",
      briefMode:
        data.briefMode === "generate" || data.briefMode === "describe"
          ? data.briefMode
          : "write",
      sections: sections.length ? sections : [{ name: "", content: "" }],
      briefText: String(data.briefText || ""),
      structureKey: String(data.structureKey || ""),
      cap:
        data.cap === "standard" || data.cap === "broad" ? data.cap : "focused",
      view:
        data.view === "run" || data.view === "history" ? data.view : "wizard",
    };
  } catch {
    return null;
  }
}

export function structureKeyFor(market: string, geography: string): string {
  return `${market.trim().toLowerCase()}|${(geography || "global").trim().toLowerCase() || "global"}`;
}

export function saveWizard(email: string, snap: WizardSnapshot): void {
  if (typeof window === "undefined" || !email) return;
  try {
    window.localStorage.setItem(storageKey(email), JSON.stringify(snap));
  } catch {
    /* quota / private mode */
  }
}

export function clearWizard(email: string): void {
  if (typeof window === "undefined" || !email) return;
  try {
    window.localStorage.removeItem(storageKey(email));
  } catch {
    /* ignore */
  }
}
