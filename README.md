# GEO Auditor

**Why AI search engines ignore your business — and exactly what to fix.**

Most businesses rank well on Google and are completely invisible inside AI answers (ChatGPT, Perplexity, Claude, Gemini). They have no way to know this, and no way to diagnose why. This tool is the diagnostic.

> Existing GEO tools audit websites. This tool audits **why AI chooses (or doesn't choose) your business** when answering real user questions. Those are different problems. The first produces a technical checklist. The second produces a moment of recognition.

---

## What it does

Enter a business URL. Get back:

1. **A live visibility score** — how many AI engines actually mention you right now, across real queries
2. **Why you're invisible** — which of three root causes is failing, with evidence for each finding
3. **Copy-pasteable fixes** — not advice, actual `robots.txt` blocks, JSON-LD schema markup, and written sentences to paste immediately

---

## Run it in under 5 minutes

```bash
git clone <repo>
cd geo_auditor
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add GEMINI_API_KEY (required) and GROQ_API_KEY (strongly recommended)

python main.py <url> "<business name>" "<category>" "<location>"
```

**Examples:**

```bash
python main.py https://qpiai.tech "QPiAI" "quantum computing" "India"
python main.py https://notion.so "Notion" "productivity software" "San Francisco"
python main.py https://zepto.com "Zepto" "quick commerce grocery" "India"
```

The report saves as a standalone HTML file in the project directory. Open it in any browser.

---

## API keys

| Key                  | Required?            | Free tier                                                | Purpose                                                                                   |
| -------------------- | -------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`     | **Required**         | Yes — [aistudio.google.com](https://aistudio.google.com) | Live visibility test (Gemini) + all LLM-based checks (Entity Authority, Answer Readiness) |
| `GROQ_API_KEY`       | Strongly recommended | Yes — [console.groq.com](https://console.groq.com)       | Training data visibility test + competitor name extraction                                |
| `PERPLEXITY_API_KEY` | Optional             | No (paid)                                                | Additional live search visibility test                                                    |

If `GROQ_API_KEY` is missing, the Llama 3 visibility test and competitor extraction are skipped and labeled as unavailable in the report. If `PERPLEXITY_API_KEY` is missing, that test is skipped and labeled as a mock.

---

## Architecture

```
geo_auditor/
├── main.py                   # Entry point + score computation
├── requirements.txt
├── .env.example
├── checks/
│   ├── crawlability.py       # Check 1 — deterministic HTTP checks, no LLM
│   ├── ai_authority.py       # Check 2 — Gemini (search-grounded) + Wikipedia API
│   ├── answer_readiness.py   # Check 3 — Gemini + regex analysis
│   └── llm_utils.py          # Shared Gemini call helper (retry, available flag, JSON mode)
├── visibility/
│   └── live_test.py          # Multi-model visibility test (Gemini + Groq + Perplexity)
├── schemas/
│   ├── entity_salience.py    # Pydantic schema for salience check output
│   ├── quotability.py        # Pydantic schema for quotability check output
│   └── concept_coverage.py   # Pydantic schema for concept coverage output
└── report/
    └── generator.py          # Jinja2 HTML report template
```

### The `llm_utils` design

All Gemini calls go through `checks/llm_utils.py`, which provides:

- **Retry with exponential backoff** on `429 RESOURCE_EXHAUSTED` (free tier hits this; zero retry was the root cause of most bugs in early versions)
- **`available: bool` on every response** — so callers can distinguish "genuinely low score" from "API call failed." Fixes are only generated from sub-checks that actually ran
- **JSON mode helper** — strips code fences, validates against Pydantic schemas, reports parse failures as `available=False` instead of raising

Model: `gemini-2.5-flash` (free tier, Google Search grounding supported)

---

## The three checks

### Why three and not twelve

The assignment brief says: _"Three checks done properly beat twelve that tick boxes."_ So I picked three that map directly to the three failure stages in the AI citation pipeline, backed by Zhang Kai et al. (2026) — an empirical study of 602 prompts and 21,143 citations across ChatGPT, Google AIO, and Perplexity.

---

### Check 1: Crawlability (20% of final score)

**Can AI bots physically access and read this site?**

The gateway check. If AI crawlers are blocked or the page can't be fetched, the score for every other check is irrelevant. The geo-citation-lab dataset had a 76.44% fetch success rate — meaning ~24% of cited pages couldn't even be read.

**What it checks (all deterministic HTTP fetches, no LLM):**

- `robots.txt` — are GPTBot, ClaudeBot, PerplexityBot blocked or allowed?
- `sitemap.xml` — does one exist and is it valid?
- `llms.txt` — does one exist? (emerging standard, like robots.txt but for AI context)

**Output:** exact `robots.txt` lines to paste, a generated `llms.txt` file for their domain

---

### Check 2: Entity Authority (35% of final score)

**Do independent authoritative sources confirm this entity exists — and associate it with the right topic?**

Renamed from "AI Authority" — what this check actually measures is whether LLMs _know who you are_, not whether your site has good backlinks. Three sub-checks run inside this one:

**Corroboration** — Wikipedia presence (Wikipedia API, deterministic), news mentions (Gemini + Google Search grounding), directory listings (Gemini + search)

**Knowledge graph consistency** — is the entity name used consistently across LinkedIn, Crunchbase, news sources, and the website itself? Inconsistency splits the AI's authority signal across multiple perceived entities.

**Entity Salience** ← the non-obvious check most GEO tools miss entirely

A business can be crawlable and corroborated and still be invisible. The reason: AI associates it with the _wrong topic cluster_. IIIT Dharwad appears everywhere — for engineering admissions. Never for quantum computing. So when someone asks "quantum universities in India," it's invisible despite having both a Wikipedia page and news mentions.

We ask Gemini (with search): _what does the web currently associate this business with?_ Then we check whether that matches the target category. If not, we show the gap and generate the exact content vocabulary needed to close it.

**Why 35%:** Zhang Kai et al. show Official + News + Vertical sources account for 79–87% of all AI citations across all three platforms. Source identity is a strong _entry condition_ — you can't be absorbed if you're never selected.

**Score renormalization:** if any sub-check is unavailable (rate limit, API error), its weight is redistributed across the sub-checks that ran. The report shows "N of 5 sub-checks unavailable this run" rather than silently penalizing the score.

---

### Check 3: Answer Readiness (45% of final score)

**Is the content structured so AI can actually extract and use it in an answer?**

Once a business enters the citation pool, _absorption_ determines whether AI uses the page or just references it weakly. This is where most businesses silently fail.

**Sub-checks (mix of regex analysis and Gemini):**

- **Structure** — word count, H2/H3 heading count. Top-quartile AI-cited pages have 12.46x more headings and 11.44x more words than bottom-quartile pages (Zhang Kai et al.)
- **Evidence density** — statistics (+61.5% absorption uplift), definitions (+57.3%), comparisons (+55.3%). Fixed regex catches three number formats: hyphenated (`64-qubit`), multipliers (`96x`), and unit-suffixed (`300 qubits`, `50%`)
- **Q&A format penalty** — FAQ format _alone_ hurts absorption by -5.7% (Zhang Kai et al., 23,745 data points). Most GEO guides recommend adding FAQ pages. This check flags when a business has done so without adding the underlying evidence density
- **Schema markup** — deterministic HTML parse for `Organization`, `LocalBusiness`, `Product` JSON-LD
- **Quotability** — Gemini analyzes whether the page contains one standalone, attributable sentence AI can quote. If not, it generates one based on what it can infer about the business
- **Concept coverage** — Gemini (with search) identifies what vocabulary competitors who _are_ cited use, then checks how much of it appears on this page. Missing concepts = missed retrieval queries

**Why 45%:** This is where the most actionable fixes live, and where the research shows the biggest variance. All fixes go directly into the business's own content — no external dependencies.

---

## What's real vs mocked

| Component                                     | Status                                           | Method                                                |
| --------------------------------------------- | ------------------------------------------------ | ----------------------------------------------------- |
| `robots.txt` / `sitemap.xml` / `llms.txt`     | **Real**                                         | Deterministic HTTP fetch                              |
| Wikipedia presence                            | **Real**                                         | Wikipedia REST API                                    |
| News mentions                                 | **Real**                                         | Gemini + Google Search grounding                      |
| Directory listings                            | **Real**                                         | Gemini + Google Search grounding                      |
| Entity salience                               | **Real**                                         | Gemini + Google Search grounding                      |
| Name consistency                              | **Real**                                         | Gemini + Google Search grounding                      |
| Schema markup detection                       | **Real**                                         | BeautifulSoup HTML parse                              |
| Evidence density (numbers, defs, comparisons) | **Real**                                         | Regex (no LLM)                                        |
| Quotability scoring + sentence generation     | **Real**                                         | Gemini (no search)                                    |
| Concept coverage vs competitors               | **Real**                                         | Gemini + Google Search grounding                      |
| Competitor name extraction                    | **Real if GROQ_API_KEY set**                     | Groq / Llama 3.3 (structured JSON output)             |
| Live visibility — Gemini                      | **Real**                                         | Gemini + Google Search grounding                      |
| Live visibility — Llama 3 (training data)     | **Real if GROQ_API_KEY set, else skipped**       | Groq / Llama 3.3 (no web search — tests model memory) |
| Live visibility — Perplexity                  | **Real if PERPLEXITY_API_KEY set, else skipped** | Perplexity API                                        |

Any unavailable check is labeled explicitly in the report — the word "Unable to compute" with the reason, never a confident-looking finding built on no evidence.

---

## What I cut and why

**No Anthropic API** — requires paid credits. Gemini free tier (via `google-genai`) provides equivalent capability including Google Search grounding. The architecture is identical; only the client and tool format differ.

**No Perplexity as a required dependency** — requires paid credits. It's supported as an optional platform if the key is present, labeled as unavailable otherwise. Zhang Kai et al. show Perplexity cites the broadest source set (16.35 avg citations/prompt), which makes it useful for visibility testing, but the audit's core checks don't depend on it.

**No auth / billing / accounts** — single-session tool. No state to persist.

**No database** — results write to HTML + JSON locally.

**No Docker / CI / tests** — out of scope per the brief.

**No adversarial text sequences** — Kumar & Lakkaraju (Harvard, 2024) demonstrate LLM rankings can be manipulated by injecting adversarial token sequences into product pages. We don't build this. The output is gibberish to human visitors, model-version-specific, and ethically equivalent to black-hat SEO. We build the honest diagnostic.

**No full-site crawl** — homepage + /about only. A deep crawl blurs findings and multiplies LLM API calls on a free tier. Narrow and deep, same principle as the check design.

**No "more checks"** — entity salience, answer gap, and retrieval coverage were considered as separate checks. They're merged into Check 2 (salience → Entity Authority) and Check 3 (concept coverage → Answer Readiness). Three deep checks, not six shallow ones.

---

## What I'd build next (with another week)

1. **Longitudinal tracking** — repeat the same audit weekly, show visibility trend over time. Zhang Kai et al. explicitly note a one-time snapshot is incomplete; model behavior changes.
2. **Competitor benchmarking** — run the audit on 3 competitors side by side. The most powerful product moment is showing the owner exactly which competitor "owns" their topic in AI answers and why.
3. **Platform-specific reports** — ChatGPT and Google AIO show different absorption signals (ChatGPT: LLM relevance; Google: embedding similarity; Perplexity: heading count + length). The research supports platform-specific optimization advice, not one universal recipe.
4. **`llms.txt` auto-generator** — 5-question interview with the founder, outputs a complete, accurate `llms.txt` ready to publish.
5. **Query-specific mode** — let the user define the exact queries they want to appear for, test visibility against those directly.

---

## Research basis

- Zhang Kai, He Xinyue & Yao Jingang (2026). _From Citation Selection to Citation Absorption: A Measurement Framework for GEO Across AI Search Platforms._ arXiv:2604.25707. [602 prompts, 21,143 citations, 72 features across ChatGPT, Google AIO, Perplexity — primary empirical basis for all check weights and sub-check design]
- Kumar, A. & Lakkaraju, H. (2024). _Manipulating Large Language Models to Increase Product Visibility._ Harvard. arXiv:2404.07981. [Context for why this problem is commercially significant, and why we don't build the adversarial approach]
- Primary field research: extended conversations with ChatGPT on how it selects and weights sources, using the QPiAI / IIIT Dharwad quantum computing case as a live example — the direct source of the entity salience check design and the hub-vs-node framing used throughout the report
