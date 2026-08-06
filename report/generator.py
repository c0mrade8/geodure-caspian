"""
Report generator — turns audit results into a clean HTML report.
Written for a business owner, not an SEO consultant.
Design: clean, diagnostic, consultant-style narrative.
"""

import os
from jinja2 import Template
from datetime import datetime


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GEO Audit — {{ business_name }}</title>
<style>
  :root {
    --ink: #0f0f0f;
    --muted: #6b7280;
    --border: #e5e7eb;
    --red: #dc2626;
    --amber: #d97706;
    --green: #16a34a;
    --red-bg: #fef2f2;
    --amber-bg: #fffbeb;
    --green-bg: #f0fdf4;
    --accent: #1d4ed8;
    --accent-light: #eff6ff;
    --surface: #fafafa;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Georgia', serif;
    color: var(--ink);
    background: #fff;
    line-height: 1.65;
    font-size: 16px;
  }

  .container { max-width: 860px; margin: 0 auto; padding: 48px 32px; }

  /* ── Header ── */
  .report-header {
    border-bottom: 2px solid var(--ink);
    padding-bottom: 24px;
    margin-bottom: 40px;
  }
  .report-header .label {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
  }
  .report-header h1 {
    font-size: 28px;
    font-weight: normal;
    letter-spacing: -0.02em;
  }
  .report-header .meta {
    font-size: 13px;
    color: var(--muted);
    margin-top: 6px;
    font-family: 'Courier New', monospace;
  }

  /* ── Opening: the moment of realization ── */
  .verdict {
    background: var(--ink);
    color: #fff;
    padding: 36px 40px;
    margin-bottom: 40px;
    border-radius: 4px;
  }
  .verdict .verdict-label {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #9ca3af;
    margin-bottom: 12px;
  }
  .verdict .verdict-headline {
    font-size: 22px;
    font-weight: normal;
    line-height: 1.4;
    margin-bottom: 20px;
  }
  .verdict .visibility-number {
    font-size: 64px;
    font-weight: bold;
    font-family: 'Courier New', monospace;
    line-height: 1;
    color: {% if visibility_pct < 30 %}#f87171{% elif visibility_pct < 60 %}#fbbf24{% else %}#4ade80{% endif %};
    margin-bottom: 4px;
  }
  .verdict .visibility-label { color: #9ca3af; font-size: 13px; }

  .platform-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 24px;
  }
  .platform-chip {
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
    padding: 10px 14px;
    font-size: 13px;
    font-family: 'Courier New', monospace;
  }
  .platform-chip .name { color: #d1d5db; font-size: 11px; margin-bottom: 2px; }
  .platform-chip .status { font-weight: bold; }
  .platform-chip .cited { color: #4ade80; }
  .platform-chip .not-cited { color: #f87171; }
  .platform-chip .mock { color: #9ca3af; font-style: italic; }

  .competitors-hook {
    background: rgba(248,113,113,0.12);
    border: 1px solid rgba(248,113,113,0.35);
    border-radius: 4px;
    padding: 16px 20px;
    margin: 20px 0 24px 0;
    font-size: 14px;
    color: #fecaca;
  }
  .competitors-hook .hook-label {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #f87171;
    margin-bottom: 6px;
  }
  .competitors-hook strong { color: #fff; }

  .unavailable-note {
    background: #f9fafb;
    border: 1px dashed var(--border);
    border-radius: 4px;
    padding: 12px 16px;
    font-size: 12.5px;
    color: var(--muted);
    margin-top: 10px;
  }
  .unavailable-note strong { color: var(--ink); }

  .impact-tag {
    display: inline-block;
    font-family: 'Courier New', monospace;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 20px;
    background: var(--green-bg);
    color: var(--green);
    margin-top: 6px;
    margin-right: 6px;
  }
  .impact-tag.low-confidence { background: var(--amber-bg); color: var(--amber); }

  /* ── Section headings ── */
  .section {
    margin-bottom: 48px;
  }
  .section-label {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
  }
  .section h2 {
    font-size: 22px;
    font-weight: normal;
    letter-spacing: -0.01em;
    margin-bottom: 20px;
  }

  /* ── Score summary ── */
  .score-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
    margin-bottom: 32px;
  }
  .score-card {
    border: 1px solid var(--border);
    padding: 20px;
    border-radius: 4px;
  }
  .score-card .check-name {
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }
  .score-card .check-score {
    font-size: 32px;
    font-weight: bold;
    font-family: 'Courier New', monospace;
    line-height: 1;
  }
  .score-card .check-bar {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin-top: 10px;
  }
  .score-card .check-bar-fill {
    height: 4px;
    border-radius: 2px;
  }
  .score-card .check-weight {
    font-size: 11px;
    color: var(--muted);
    margin-top: 6px;
  }

  .score-high { color: var(--green); }
  .score-mid { color: var(--amber); }
  .score-low { color: var(--red); }
  .bar-high { background: var(--green); }
  .bar-mid { background: var(--amber); }
  .bar-low { background: var(--red); }

  /* ── Why section ── */
  .salience-box {
    background: var(--accent-light);
    border-left: 3px solid var(--accent);
    padding: 20px 24px;
    margin: 20px 0;
    border-radius: 0 4px 4px 0;
  }
  .salience-box h3 { font-size: 15px; margin-bottom: 12px; color: var(--accent); }
  .topic-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
  }
  .topic-chip {
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-family: 'Courier New', monospace;
  }
  .topic-chip.current { background: #fee2e2; color: var(--red); }
  .topic-chip.target { background: #dcfce7; color: var(--green); }
  .topic-chip.missing { background: #fef9c3; color: #854d0e; }

  /* ── Answer gap ── */
  .gap-table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 14px;
  }
  .gap-table th {
    text-align: left;
    padding: 10px 12px;
    background: var(--surface);
    border-bottom: 2px solid var(--border);
    font-size: 12px;
    font-family: 'Courier New', monospace;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .gap-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .gap-table .present { color: var(--green); }
  .gap-table .missing { color: var(--red); }

  /* ── Fixes ── */
  .fix-item {
    border: 1px solid var(--border);
    border-radius: 4px;
    margin-bottom: 20px;
    overflow: hidden;
  }
  .fix-header {
    padding: 16px 20px;
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }
  .fix-priority {
    background: var(--red);
    color: #fff;
    font-family: 'Courier New', monospace;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 2px;
    flex-shrink: 0;
    margin-top: 2px;
  }
  .fix-priority.medium { background: var(--amber); }
  .fix-title { font-size: 15px; font-weight: bold; margin-bottom: 4px; }
  .fix-detail { font-size: 13px; color: var(--muted); line-height: 1.5; }
  .fix-effort {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    color: var(--muted);
    margin-top: 4px;
  }
  .fix-code {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 16px 20px;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.6;
    border-top: 1px solid #333;
  }
  .fix-code-label {
    padding: 8px 20px;
    background: var(--surface);
    border-top: 1px solid var(--border);
    font-size: 11px;
    font-family: 'Courier New', monospace;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  /* ── Monday morning actions ── */
  .monday-grid { display: grid; grid-template-columns: auto 1fr; gap: 0; }
  .monday-day {
    padding: 14px 20px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    font-family: 'Courier New', monospace;
    font-size: 12px;
    text-transform: uppercase;
    color: var(--muted);
    white-space: nowrap;
    font-weight: bold;
  }
  .monday-action {
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
  }
  .monday-action .effort {
    font-size: 11px;
    color: var(--muted);
    font-family: 'Courier New', monospace;
    margin-top: 2px;
  }

  /* ── Footer ── */
  .report-footer {
    border-top: 1px solid var(--border);
    margin-top: 64px;
    padding-top: 24px;
    font-size: 12px;
    color: var(--muted);
    font-family: 'Courier New', monospace;
  }
  .data-note {
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 16px 20px;
    border-radius: 4px;
    font-size: 12px;
    color: var(--muted);
    margin-top: 32px;
  }
  .data-note strong { color: var(--ink); }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="report-header">
    <div class="label">GEO Audit Report</div>
    <h1>{{ business_name }}</h1>
    <div class="meta">{{ url }} · Generated {{ date }}</div>
  </div>

  <!-- Opening: The moment of realization -->
  <div class="verdict">
    <div class="verdict-label">Current AI Position</div>
    <div class="verdict-headline">
      {% if visibility_pct < 20 %}
        AI search engines don't know {{ business_name }} exists. When someone asks about {{ category }}, your competitors are recommended — not you.
      {% elif visibility_pct < 50 %}
        {{ business_name }} appears in only {{ visibility_pct }}% of relevant AI queries. Your competitors are capturing the attention you're missing.
      {% else %}
        {{ business_name }} has moderate AI visibility, but there's room to dominate your category.
      {% endif %}
    </div>

    <div class="visibility-number">{{ visibility_pct }}%</div>
    <div class="visibility-label">AI visibility across {{ total_tests }} queries and models</div>

    {% if top_competitors %}
    <div class="competitors-hook">
      <div class="hook-label">Cited instead of {{ business_name }}</div>
      When AI engines were asked about {{ category }}, they named <strong>{{ top_competitors | join(", ") }}</strong> — not you.
    </div>
    {% endif %}

    <div class="platform-grid">
      {% for name, data in platforms.items() %}
      <div class="platform-chip">
        <div class="name">{{ name }}</div>
        {% if data.mock %}
          <div class="status mock">Not tested (no API key)</div>
        {% elif data.unavailable %}
          <div class="status mock">Unable to test — {{ data.error_reason or "endpoint unavailable" }}</div>
        {% elif data.mentioned > 0 %}
          <div class="status cited">✓ Cited in {{ data.mentioned }}/{{ data.total }} queries</div>
        {% else %}
          <div class="status not-cited">✗ Not cited</div>
        {% endif %}
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- Score Summary -->
  <div class="section">
    <div class="section-label">Root Causes</div>
    <h2>Why AI ignores {{ business_name }}</h2>

    <div class="score-grid">
      {% set c1 = crawlability %}
      {% set c2 = ai_authority %}
      {% set c3 = answer_readiness %}

      {% for check, label, weight in [
          (c1, c1.check, "20% of score"),
          (c2, "Entity Authority", "35% of score"),
          (c3, c3.check, "45% of score")
      ] %}
      <div class="score-card">
        <div class="check-name">{{ label }}</div>
        {% set pct = (check.score / check.max * 100) | int %}
        <div class="check-score
          {% if pct >= 70 %}score-high
          {% elif pct >= 40 %}score-mid
          {% else %}score-low{% endif %}">
          {{ check.score }}<span style="font-size:16px;color:#9ca3af">/{{ check.max }}</span>
        </div>
        <div class="check-bar">
          <div class="check-bar-fill
            {% if pct >= 70 %}bar-high
            {% elif pct >= 40 %}bar-mid
            {% else %}bar-low{% endif %}"
            style="width: {{ pct }}%"></div>
        </div>
        <div class="check-weight">{{ weight }}</div>
      </div>
      {% endfor %}
    </div>

    <!-- Entity Salience: the non-obvious insight -->
    {% set salience = ai_authority.details.entity_salience %}
    {% if salience and salience.error %}
    <div class="unavailable-note">
      <strong>Entity association signal unavailable this run.</strong>
      Reason: {{ salience.error }}. This check could not run — it is not being counted as a negative finding, and does not affect the score above.
    </div>
    {% elif salience and salience.salience_match in ['low', 'none', 'medium'] %}
    <div class="salience-box">
      <h3>The real problem: AI associates you with the wrong topic</h3>
      <p style="font-size:14px; margin-bottom:12px;">
        {{ salience.gap_description or "AI currently associates your business with a different topic than your target category." }}
        This means even if you're crawlable and corroborated, you won't appear when someone asks about {{ category }}.
      </p>
      <div style="font-size:13px; color: #374151;">
        <strong>Currently associated with:</strong>
        <div class="topic-list">
          {% for t in salience.current_associations[:4] %}
          <span class="topic-chip current">{{ t }}</span>
          {% endfor %}
        </div>
      </div>
      <div style="font-size:13px; color: #374151; margin-top:12px;">
        <strong>Should be associated with:</strong>
        <div class="topic-list">
          <span class="topic-chip target">{{ category }}</span>
          {% for t in salience.missing_concepts[:3] %}
          <span class="topic-chip missing">{{ t }}</span>
          {% endfor %}
        </div>
      </div>
    </div>
    {% endif %}
  </div>

  <!-- Answer Gap -->
  {% set coverage = answer_readiness.details.concept_coverage %}
  {% if coverage and (coverage.covered_concepts or coverage.missing_concepts) %}
  <div class="section">
    <div class="section-label">Answer Gap Analysis</div>
    <h2>What your cited competitors have — that you don't</h2>
    <p style="color: var(--muted); font-size: 14px; margin-bottom: 20px;">
      LLMs don't retrieve websites — they retrieve content chunks. If a key concept isn't on your page,
      you won't appear for queries about that concept, even if you're the right answer.
    </p>
    <table class="gap-table">
      <thead>
        <tr>
          <th>Concept / Topic</th>
          <th>Competitors who ARE cited</th>
          <th>{{ business_name }}</th>
        </tr>
      </thead>
      <tbody>
        {% for concept in coverage.covered_concepts[:4] %}
        <tr>
          <td>{{ concept }}</td>
          <td class="present">✓ Covered</td>
          <td class="present">✓ Covered</td>
        </tr>
        {% endfor %}
        {% for concept in coverage.missing_concepts[:6] %}
        <tr>
          <td><strong>{{ concept }}</strong></td>
          <td class="present">✓ Covered</td>
          <td class="missing">✗ Missing</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% if coverage.most_impactful_missing %}
    <p style="font-size:13px; color: var(--red); margin-top: 8px;">
      ↑ Most impactful gap: "{{ coverage.most_impactful_missing }}"
    </p>
    {% endif %}
  </div>
  {% endif %}

  <!-- All Fixes: prioritized, copy-pasteable -->
  <div class="section">
    <div class="section-label">Monday Morning Fixes</div>
    <h2>What to do, in order of impact</h2>
    <p style="color: var(--muted); font-size: 14px; margin-bottom: 28px;">
      Every fix below includes copy-pasteable output. Start with Priority 1 — they have the highest impact for the least effort.
    </p>

    {% set all_fixes = [] %}
    {% for fix in crawlability.fixes %}{% set _ = all_fixes.append(fix) %}{% endfor %}
    {% for fix in ai_authority.fixes %}{% set _ = all_fixes.append(fix) %}{% endfor %}
    {% for fix in answer_readiness.fixes %}{% set _ = all_fixes.append(fix) %}{% endfor %}

    {% for fix in all_fixes | sort(attribute='priority') %}
    <div class="fix-item">
      <div class="fix-header">
        <div class="fix-priority {% if fix.priority > 1 %}medium{% endif %}">
          Priority {{ fix.priority }}
        </div>
        <div>
          <div class="fix-title">{{ fix.title }}</div>
          <div class="fix-detail">{{ fix.detail }}</div>
          {% if fix.effort %}
          <div class="fix-effort">Time required: {{ fix.effort }}</div>
          {% endif %}
          {% if fix.impact_points %}
          <span class="impact-tag {% if fix.confidence == 'low' %}low-confidence{% endif %}">
            Expected impact: +{{ fix.impact_points }} pts
            {% if fix.confidence %}· {{ fix.confidence | capitalize }} confidence{% endif %}
          </span>
          {% endif %}
        </div>
      </div>
      {% if fix.copy_paste %}
      <div class="fix-code-label">Copy-paste fix ↓</div>
      <div class="fix-code">{{ fix.copy_paste }}</div>
      {% endif %}
    </div>
    {% endfor %}
  </div>

  <!-- Data and methodology note -->
  <div class="data-note">
    <strong>Methodology note:</strong>
    Crawlability checks are deterministic HTTP fetches.
    Entity Authority and Answer Readiness use {{ analysis_engine or "Gemini, with web search grounding" }} for analysis.
    Live visibility tests run real queries across AI platforms — any mocked or unavailable results are labeled as such, never presented as a negative finding.
    Research basis: Zhang Kai, He Xinyue & Yao Jingang (2026), "From Citation Selection to Citation Absorption"
    (602 prompts, 21,143 citations across ChatGPT, Google AIO, Perplexity).
    {% if unavailable_count %}
    <br><br><strong>Run completeness:</strong> {{ unavailable_count }} of {{ total_checks }} sub-checks could not be completed this run
    (rate limits or endpoint errors) and were excluded from scoring rather than counted as failures.
    {% endif %}
  </div>

  <div class="report-footer">
    GEO Auditor · {{ date }} · {{ url }}
  </div>

</div>
</body>
</html>"""


# Stopgap filter until competitor extraction is fixed at the source (LLM-based
# extraction instead of regex). This is a safety net, not the real fix — see README.
_COMPETITOR_STOPWORDS = {
    "here", "india", "today", "this", "that", "these", "those", "instead",
    "company", "companies", "ignore", "they", "them", "unlike", "other",
    "others", "the", "and", "with", "for", "from", "using", "including",
    "such", "some", "many", "our", "your", "their",
}


def _clean_competitors(names: list) -> list:
    cleaned = []
    seen = set()
    for item in names or []:
        if isinstance(item, dict):
            name = item["name"]
        else:
            name = item
        key = name.strip().lower()
        if not key or key in _COMPETITOR_STOPWORDS:
            continue
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name.strip())
    return cleaned


def generate(results: dict, output_path: str) -> str:
    """Render the HTML report from audit results."""
    template = Template(TEMPLATE)

    visibility = results["visibility"]
    platforms = visibility.get("platforms", {})

    # Run-completeness: count sub-checks across ai_authority/answer_readiness
    # that errored out, so the report can say so plainly instead of letting
    # a 0-score stand in for "we couldn't measure this."
    unavailable_count = 0
    total_checks = 0
    for section in (results["ai_authority"], results["answer_readiness"]):
        for sub in section.get("details", {}).values():
            total_checks += 1
            if isinstance(sub, dict) and sub.get("error"):
                unavailable_count += 1

    html = template.render(
        business_name=results["business_name"],
        url=results["url"],
        date=datetime.now().strftime("%d %B %Y"),
        visibility_pct=visibility["visibility_pct"],
        total_tests=visibility["total_tests"],
        top_competitors=_clean_competitors(visibility.get("top_competitors", [])),
        platforms=platforms,
        category=results["category"],
        crawlability=results["crawlability"],
        ai_authority=results["ai_authority"],
        answer_readiness=results["answer_readiness"],
        geo_score=results["geo_score"],
        analysis_engine=results.get("analysis_engine"),
        unavailable_count=unavailable_count,
        total_checks=total_checks,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path