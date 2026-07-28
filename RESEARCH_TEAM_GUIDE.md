# Research Team Handover — Vendor Intelligence

How to run markets in the **deployed Streamlit app** (frontend only).

You work only in the web UI — market name, geography, market structure brief, run, then download results.

---

## What this system does

- Discovers and classifies **companies** in a market using search + LLM + **company website scraping**
- Follows **your** market definition, sections, and include/exclude rules
- Produces landscape exports (**Excel / Word**) for review

**Garbage in → wrong boundary out.** The clearer your brief, the closer the list is to what you meant.

---

## How to search a market

### Step-by-step in the app

1. **Sign in** with your `@coherentmarketinsights.com` email (OTP).
2. **Step 1 — Market & Geography**
   - Enter a plain market title (e.g. `Remote Elderly Health Monitoring Market`).
   - Set geography (`Global`, `North America`, etc.).
   - Click **Next**.
3. **Step 2 — Market structure** (most important)
   - Prefer writing a full value-chain brief (or **Generate with AI, then review** and edit).
   - For every section include: Function, Core entities (with a few well-known example companies), Business model, and Market sizing (`INCLUDE` / `INCLUDE PARTIALLY` / `EXCLUDE`).
   - End with a clear **Which entities to INCLUDE / EXCLUDE** block.
   - Add **search phrases** under `MANUAL SEARCH ANCHORS` — the queries you would type yourself (or already typed when researching this market).

     ```text
     MANUAL SEARCH ANCHORS (use these discovery intents):
     - remote elderly monitoring platform software
     - RPM dashboard provider hospitals
     - senior fall detection wearable manufacturer
     - ambient monitoring system aging in place
     ```

     **Note — if you already have a prior CMI dataset / workbook for this market:** use the same market title and geography as that work, align INCLUDE / EXCLUDE with how that list was sized, name key companies from that list under the matching **Core entities**, and paste the **actual search queries you used at the time** into `MANUAL SEARCH ANCHORS` (not only new guesses). Keep one market definition — do not mix two report scopes. After the run, compare by section / role first, then name-by-name.

4. **Step 3 — Review & Run**
   - Confirm market, geo, and sections.
   - Start the run and **let it finish** (do not stop mid-way).
5. **After the run**
   - Download Excel / Word.
   - Human-review roles and edge cases before anything client-facing.
   - If coverage is thin, tighten the brief (sharper sections + anchors) and re-run once.

### Tips

- Start from real product nouns (kits, platforms, sensors, modems…), not only the umbrella market name.
- 3–6 sections is usually enough; too many spreads the search thin.
- Naming a few real companies under **Core entities** helps the system understand each section.

---

## Rules for every run

### Golden rules

1. **Do not stop a run mid-way** unless it is clearly stuck or failing. Stopping produces incomplete or empty outputs. Prefer finishing, then re-run with a tighter brief.
2. **One clear brief beats a vague market name.** Prefer full sections + INCLUDE / EXCLUDE, not a 3-word title alone.
3. **Put your search language in the brief.** The system only knows the queries you write down.
4. **Be specific for the LLM.** Short, concrete sentences. Name products, buyers, and market edges. Avoid fluff and contradictory include/exclude.
5. **Review AI-generated structure before Run.** Edit aggressively — drafts are a starting point, not truth.

### Writing a good brief

The system turns your Market Structure text into scope, search prompts, and classification rules. Write for a careful junior analyst who has never seen this market.

**Do**

- State **Market** and **Geography** on the first lines.
- One short **definition**: what is bought/sold, by whom, for what use case.
- List **functional entities / sections** (usually 3–6), each with Function / Core entities / Business model / Market sizing.
- End with an explicit **INCLUDE / EXCLUDE** block for sizing.
- Use industry vocabulary (assay kit, VSAT modem, PERS hub…), not only the umbrella name.
- Call out adjacent traps (“Exclude general consumer fitness wearables”, “Exclude pure hospital EHR”).

**Don’t**

- Don’t write only `Molecular Diagnostics Market` and press Run.
- Don’t dump unstructured notes with no sections.
- Don’t say INCLUDE and EXCLUDE for the same thing.
- Don’t use marketing fluff with no boundary.
- Don’t list 20 sections you never intend to profile.
- Don’t paste entire 50-page reports — summarize the **rules** and **anchors**.

### Brief skeleton

```text
Market: <exact market name>
Geography: <Global | North America | …>

Definition: <2–4 sentences — product, buyer, use case, boundary.>

FUNCTIONAL ENTITIES IN THE VALUE CHAIN (segments to profile):

1. <Section name>
   - Function: …
   - Core entities: … (e.g. Company A, Company B)
   - Business model: …
   - Market sizing: INCLUDE | INCLUDE PARTIALLY | EXCLUDE — <reason>

2. <Section name>
   …

MANUAL SEARCH ANCHORS:
- <query you would type yourself>
- <another query>
- …

Which entities to INCLUDE in market sizing?
INCLUDE: …
INCLUDE PARTIALLY: …
EXCLUDE: … (buyers, pure resellers, double-counted wholesale, wrong market)

Sizing principle: <one sentence — what spend you count and what you refuse to double-count.>
```

### Sections: INCLUDE vs EXCLUDE

| Mark as | When |
|--------|------|
| **INCLUDE** | Sells finished products/services that belong in *this* market size. |
| **INCLUDE PARTIALLY** | Only part of revenue is in-scope. |
| **EXCLUDE** | End users/buyers, pure resellers, financing/care delivery, true cross-industry commodities, or revenue already counted elsewhere (double-count). |

**Do**

- Profile the **full value chain** in sections even if some are EXCLUDE for sizing.
- Keep section titles short (2–6 words); put detail under Function / Core entities.
- When unsure for a real product maker in this market → **INCLUDE**.

**Don’t**

- Don’t EXCLUDE reagents/consumables/software that are branded products *of this market* just because they “feel upstream.”
- Don’t EXCLUDE a segment and still expect those companies as core landscape players.
- Don’t use company names as section titles — use roles (`Instruments & Platforms`).

### Running the app

**Do**

1. Market & Geography → Structure → Review & Run.  
2. Leave the tab open; let the job finish.  
3. Download Excel / Word; keep a copy of the brief that produced the run.  
4. For a second pass, tighten the brief rather than stopping mid-run.

**Don’t**

- Don’t hit **Stop run** unless the job is hung.  
- Don’t start several heavy runs at once in the same browser/app session.  
- Don’t treat the progress bar as a precision ETA.

### Reviewing results

**Do**

- Check whether a missing company was correctly left out by your EXCLUDE rules.
- Check role / section labels before flagging a name as wrong.
- Re-run once with sharper SEARCH ANCHORS if coverage is short.
- Human-review before publish.

**Don’t**

- Don’t publish unreviewed AI classifications without a human pass.

---

## Checklist (every serious run)

- [ ] Market name + geography are correct  
- [ ] Sections cover the value chain you care about  
- [ ] INCLUDE / EXCLUDE matches how you size this market  
- [ ] Manual search anchors are in the brief (including prior desk-search queries if you have them)  
- [ ] A few real example companies named under Core entities for each major section  
- [ ] No contradictory include/exclude  
- [ ] You will let the run finish  
- [ ] You will human-review Excel before client-facing use  

---

## Quick do / don’t

| Do | Don’t |
|----|--------|
| Write specific, sectioned briefs | Run on a market name only |
| Put search queries you care about into the brief | Assume the system knows unspoken search habits |
| Align INCLUDE/EXCLUDE with sizing rules | Exclude product makers then expect them back |
| Let runs complete | Stop midway and treat output as final |
| Edit AI-generated structure | Blind trust “Generate structure with AI” |
| One market definition per run | Mix two report definitions in one brief |
| Name real companies under Core entities in the brief | Use vague sections with no examples |
| Human-review before publish | Ship raw export as the final company universe |

---

When in doubt: **write a tighter brief and re-run** — that almost always improves results more than fighting a weak first scope mid-pipeline.
