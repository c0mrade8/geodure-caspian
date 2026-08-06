"""
Check 3: Answer Readiness (45% of total score)
= Evidence Container Quality + Concept Coverage + Quotability

Why 45%: Once a business enters the citation pool (Check 2),
absorption is what determines if AI actually uses them in the answer.
Zhang Kai et al. show high-influence pages have:
  - 12.46x more headings than low-influence pages
  - 11.44x more words
  - +61.5% influence when containing statistics
  - +57.3% when containing definitions
  - Q&A format ALONE hurts absorption by -5.7%

This is the most actionable check — fixes go directly into the business's own content.
"""

import re
import json
import requests
from bs4 import BeautifulSoup
import anthropic


HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GEOAuditor/1.0)"}
TIMEOUT = 15


def fetch_page_content(url: str) -> dict:
    """Fetch and clean page content for analysis."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text).strip()

        return {
            "url": url,
            "raw_html": resp.text,
            "soup": soup,
            "text": text,
            "word_count": len(text.split()),
            "status_code": resp.status_code,
        }
    except Exception as e:
        return {"url": url, "text": "", "word_count": 0, "error": str(e)}


def check_structure(soup: BeautifulSoup, word_count: int) -> dict:
    """
    Check structural markers of a high-influence evidence container.
    Based on Zhang Kai et al. top vs bottom quartile comparison.
    """
    h1 = len(soup.find_all("h1"))
    h2 = len(soup.find_all("h2"))
    h3 = len(soup.find_all("h3"))
    total_headings = h1 + h2 + h3
    paragraphs = len(soup.find_all("p"))
    lists = len(soup.find_all(["ul", "ol"]))

    # Score word count (benchmark: >1000 is good, >2000 is strong)
    if word_count >= 2000:
        wc_points = 20
        wc_label = "Strong"
    elif word_count >= 1000:
        wc_points = 12
        wc_label = "Adequate"
    elif word_count >= 500:
        wc_points = 6
        wc_label = "Thin"
    else:
        wc_points = 0
        wc_label = "Very thin"

    # Score heading structure
    if total_headings >= 6:
        h_points = 15
        h_label = "Well structured"
    elif total_headings >= 3:
        h_points = 8
        h_label = "Lightly structured"
    else:
        h_points = 0
        h_label = "No structure"

    return {
        "word_count": word_count,
        "word_count_label": wc_label,
        "word_count_points": wc_points,
        "headings": {"h1": h1, "h2": h2, "h3": h3, "total": total_headings},
        "heading_label": h_label,
        "heading_points": h_points,
        "paragraphs": paragraphs,
        "lists": lists,
        "total_points": wc_points + h_points,
    }


def check_evidence_density(text: str) -> dict:
    """
    Check for evidence genres that boost AI absorption.
    Based on Zhang Kai et al. evidence genre uplift data:
      Numbers/stats: +61.5%
      Definitions:   +57.3%
      Comparisons:   +55.3%
    Q&A format alone: -5.7% (flag this)
    """
    # Numbers and statistics
    number_pattern = r'\b\d[\d,]*\s*(%|percent|million|billion|thousand|customers|users|years|countries|cities|products|employees|clients)\b'
    numbers_found = re.findall(number_pattern, text, re.IGNORECASE)

    # Definition markers
    definition_pattern = r'\b(is a|are a|defined as|refers to|means that|is the|is an)\b'
    definitions_found = re.findall(definition_pattern, text, re.IGNORECASE)

    # Comparison markers
    comparison_pattern = r'\b(unlike|compared to|versus|vs\.?|better than|different from|while|whereas|in contrast)\b'
    comparisons_found = re.findall(comparison_pattern, text, re.IGNORECASE)

    # Q&A format detection (flag — not a good signal alone)
    qa_pattern = r'\b(Q:|A:|FAQ|Frequently Asked|What is|How do|Why should)\b'
    qa_found = len(re.findall(qa_pattern, text, re.IGNORECASE))
    has_qa = qa_found > 3

    # Score
    num_points = 20 if len(numbers_found) >= 3 else (10 if len(numbers_found) >= 1 else 0)
    def_points = 10 if len(definitions_found) >= 3 else (5 if len(definitions_found) >= 1 else 0)
    cmp_points = 5 if len(comparisons_found) >= 2 else 0
    qa_penalty = -5 if has_qa and len(numbers_found) < 2 else 0  # Q&A without evidence = penalty

    total = max(0, num_points + def_points + cmp_points + qa_penalty)

    return {
        "numbers_count": len(numbers_found),
        "numbers_examples": list(set(numbers_found[:3])),
        "definitions_count": len(definitions_found),
        "comparisons_count": len(comparisons_found),
        "has_qa_format": has_qa,
        "qa_penalty_applied": qa_penalty < 0,
        "evidence_points": total,
        "breakdown": {
            "numbers": num_points,
            "definitions": def_points,
            "comparisons": cmp_points,
            "qa_penalty": qa_penalty,
        }
    }


def check_schema_markup(soup: BeautifulSoup, business_name: str, url: str) -> dict:
    """Check for schema.org structured data — helps AI identify entity type."""
    json_lds = soup.find_all("script", type="application/ld+json")
    found_types = []

    for script in json_lds:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if "@type" in item:
                        found_types.append(item["@type"])
            elif "@type" in data:
                found_types.append(data["@type"])
        except Exception:
            pass

    valuable_types = ["Organization", "LocalBusiness", "Product", "Service", "FAQPage", "WebSite"]
    found_valuable = [t for t in found_types if t in valuable_types]
    has_good_schema = len(found_valuable) > 0
    points = 15 if has_good_schema else 0

    return {
        "found_types": found_types,
        "found_valuable": found_valuable,
        "has_schema": has_good_schema,
        "points": points,
    }


def check_quotability(text: str, business_name: str, category: str, client: anthropic.Anthropic) -> dict:
    """
    Check if the page contains a clear, standalone, extractable sentence
    that an AI could quote directly in an answer about the business.

    This is the most direct test of absorption readiness.
    Zhang Kai et al. show semantic alignment (r=0.432) is the strongest
    single correlate of citation influence.
    """
    try:
        sample = text[:3000]  # Use first 3000 chars — most important content
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"""
Analyze this website content for "{business_name}" (category: {category}).

Content:
{sample}

Answer in this exact JSON format:
{{
  "has_quotable_sentence": true/false,
  "quotable_sentence": "the exact sentence if found, empty string if not",
  "reason": "why this is or isn't quotable",
  "generated_quotable_sentence": "a better quotable sentence you'd write for them based on what you can infer",
  "missing_elements": ["what's missing that would make this more quotable"]
}}

A good quotable sentence is: factual, standalone (makes sense without context),
mentions what the company is + what it does + something specific that makes it notable.
Bad example: "We are committed to excellence and innovation."
Good example: "Acme Corp is a Hyderabad-based B2B SaaS platform automating accounts payable
for 200+ mid-market manufacturers across India and Southeast Asia."
"""
            }]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)

        points = 10 if data.get("has_quotable_sentence") else 0

        return {
            "has_quotable_sentence": data.get("has_quotable_sentence", False),
            "quotable_sentence": data.get("quotable_sentence", ""),
            "reason": data.get("reason", ""),
            "generated_sentence": data.get("generated_quotable_sentence", ""),
            "missing_elements": data.get("missing_elements", []),
            "points": points,
        }
    except Exception as e:
        return {
            "has_quotable_sentence": False,
            "quotable_sentence": "",
            "generated_sentence": "",
            "missing_elements": [],
            "points": 0,
            "error": str(e),
        }


def check_concept_coverage(text: str, category: str, top_competitors: list[str], client: anthropic.Anthropic) -> dict:
    """
    The Retrieval Coverage insight — LLMs retrieve chunks, not whole websites.
    Check: does the content contain the vocabulary that LLMs are asked to retrieve?

    We compare this business's vocabulary against competitors who ARE cited.
    Missing concepts = the business won't show up for those queries even if crawlable.
    """
    try:
        competitor_str = ", ".join(top_competitors) if top_competitors else "industry leaders"
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=700,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    f"What are the 10 most important concepts, topics, and specific terms "
                    f"that define the '{category}' space? "
                    f"Look at what {competitor_str} talk about on their websites. "
                    f"Give me a list of the key vocabulary and concepts a business in this space MUST mention."
                )
            }]
        )
        competitor_concepts_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        # Now check which concepts appear in our page
        analysis = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": f"""
Key concepts for {category} space (from competitor research):
{competitor_concepts_text[:1000]}

Our website content:
{text[:2000]}

Which key concepts from the category ARE present in our content?
Which are MISSING?

Respond in this exact JSON format:
{{
  "covered_concepts": ["concept1", "concept2"],
  "missing_concepts": ["concept3", "concept4"],
  "coverage_score": 0-100,
  "most_impactful_missing": "the single most important missing concept"
}}
"""
            }]
        )
        raw = analysis.content[0].text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)

        coverage_score = data.get("coverage_score", 0)
        points = round((coverage_score / 100) * 10)

        return {
            "covered_concepts": data.get("covered_concepts", []),
            "missing_concepts": data.get("missing_concepts", []),
            "coverage_score": coverage_score,
            "most_impactful_missing": data.get("most_impactful_missing", ""),
            "points": points,
        }
    except Exception as e:
        return {
            "covered_concepts": [],
            "missing_concepts": [],
            "coverage_score": 0,
            "most_impactful_missing": "",
            "points": 0,
            "error": str(e),
        }


def generate_schema_markup(business_name: str, category: str, location: str,
                           url: str, description: str) -> str:
    """Generate copy-pasteable JSON-LD schema markup."""
    slug = url.rstrip("/")
    return f'''<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "{business_name}",
  "url": "{slug}",
  "description": "{description}",
  "address": {{
    "@type": "PostalAddress",
    "addressLocality": "{location or 'Your City'}",
    "addressCountry": "IN"
  }},
  "sameAs": [
    "https://linkedin.com/company/your-page",
    "https://crunchbase.com/organization/your-page"
  ]
}}
</script>'''


def run(url: str, business_name: str, category: str, location: str,
        top_competitors: list[str], client: anthropic.Anthropic) -> dict:
    """
    Run all Answer Readiness checks. Max score: 100.

    Sub-check breakdown:
      Structure (word count + headings):   35 pts
      Evidence density (stats/def/comp):   35 pts
      Schema markup:                       15 pts
      Quotable sentence:                   10 pts
      Concept coverage:                    10 pts (can push over if base is high)
    """
    print("  → Fetching homepage content...")
    page = fetch_page_content(url)

    if not page.get("text"):
        return {
            "check": "Answer Readiness",
            "score": 0,
            "max": 100,
            "error": "Could not fetch page content",
            "fixes": [],
        }

    soup = page.get("soup")
    text = page["text"]
    word_count = page["word_count"]

    print("  → Analysing structure...")
    structure = check_structure(soup, word_count)

    print("  → Analysing evidence density...")
    evidence = check_evidence_density(text)

    print("  → Checking schema markup...")
    schema = check_schema_markup(soup, business_name, url)

    print("  → Checking quotability (Claude API)...")
    quotability = check_quotability(text, business_name, category, client)

    print("  → Checking concept coverage vs competitors...")
    coverage = check_concept_coverage(text, category, top_competitors, client)

    total = (
        structure["total_points"]
        + evidence["evidence_points"]
        + schema["points"]
        + quotability["points"]
        + coverage["points"]
    )
    total = min(total, 100)

    # Build fixes
    fixes = []

    if structure["word_count"] < 1000:
        fixes.append({
            "priority": 1,
            "effort": "2–4 hours",
            "title": f"Homepage has only {word_count} words (benchmark: 1,000+)",
            "detail": (
                "High-influence AI pages average 1,943 words vs 170 for low-influence pages — "
                "an 11.44x difference (Zhang Kai et al., 2026). "
                "This isn't about SEO word count — it's about having enough content "
                "for AI to extract multiple evidence units from."
            ),
            "copy_paste": (
                f"Add these sections to your homepage to reach 1,000+ words:\n"
                f"• What is {business_name}? (clear definition, 2–3 sentences)\n"
                f"• Key numbers (customers, cities, years, products — with actual figures)\n"
                f"• What makes you different (specific, not generic)\n"
                f"• How it works (3–5 steps)\n"
                f"• Who it's for (specific customer types)"
            )
        })

    if structure["headings"]["total"] < 3:
        fixes.append({
            "priority": 2,
            "effort": "30 minutes",
            "title": "No structured headings — AI can't navigate your content",
            "detail": (
                "Top-quartile AI-cited pages have 12.46x more headings than bottom-quartile pages. "
                "Headings let AI extract specific sections as answer units."
            ),
            "copy_paste": (
                f"Recommended heading structure for {business_name}:\n\n"
                f"<h2>What is {business_name}?</h2>\n"
                f"<h2>How {business_name} Works</h2>\n"
                f"<h2>Who Uses {business_name}</h2>\n"
                f"<h2>Results and Impact</h2>\n"
                f"<h2>About {business_name}</h2>"
            )
        })

    if evidence["numbers_count"] < 3:
        fixes.append({
            "priority": 1,
            "effort": "1 hour",
            "title": "No quantitative facts — AI can't extract your evidence",
            "detail": (
                "Pages with numbers/statistics get +61.5% higher AI absorption. "
                "AI engines prefer pages that supply extractable evidence — facts, figures, comparisons."
            ),
            "copy_paste": (
                f"Add specific numbers to your homepage. Examples for {business_name}:\n"
                f"• 'Serving X+ customers across Y cities'\n"
                f"• 'Founded in [year] with [N] employees'\n"
                f"• 'Reduces [metric] by X% on average'\n"
                f"• '[N] years of experience in {category}'\n"
                f"Replace placeholders with your real numbers."
            )
        })

    if evidence["has_qa_format"] and evidence["qa_penalty_applied"]:
        fixes.append({
            "priority": 2,
            "effort": "2 hours",
            "title": "FAQ format without evidence density (counterintuitive finding)",
            "detail": (
                "This may surprise you: Q&A format alone reduces AI absorption by -5.7% "
                "(Zhang Kai et al., 23,745 data points). "
                "FAQ pages create short, isolated answers without the evidence density "
                "AI needs to synthesise across complex queries. "
                "Your FAQ pages need real statistics, definitions, and comparisons — "
                "not just question-and-answer wrappers."
            ),
            "copy_paste": (
                "For each FAQ answer, add at minimum:\n"
                "• One specific number or statistic\n"
                "• One clear definition ('{X} is...')\n"
                "• One comparison to alternatives"
            )
        })

    if not schema["has_schema"]:
        desc = quotability.get("generated_sentence", f"{business_name} is a {category} company.")
        schema_code = generate_schema_markup(business_name, category, location, url, desc)
        fixes.append({
            "priority": 2,
            "effort": "15 minutes",
            "title": "No schema markup — AI can't identify your entity type",
            "detail": "Schema.org markup tells AI systems what type of entity you are, helping with entity recognition.",
            "copy_paste": f"Paste this inside your <head> tag:\n\n{schema_code}"
        })

    if not quotability["has_quotable_sentence"] and quotability.get("generated_sentence"):
        fixes.append({
            "priority": 1,
            "effort": "10 minutes",
            "title": "No quotable sentence — AI has nothing to extract and attribute to you",
            "detail": (
                "AI needs a standalone, factual sentence it can quote or paraphrase "
                "when mentioning your business. Your homepage currently doesn't have one."
            ),
            "copy_paste": (
                f"Add this sentence to your homepage and About page:\n\n"
                f'"{quotability["generated_sentence"]}"'
            )
        })

    if coverage.get("missing_concepts"):
        top_missing = coverage["missing_concepts"][:5]
        fixes.append({
            "priority": 2,
            "effort": "2–3 hours",
            "title": f"Missing {len(coverage['missing_concepts'])} key concepts from your content",
            "detail": (
                f"Your competitors who get cited use vocabulary you don't. "
                f"LLMs retrieve content chunks — if the chunk doesn't contain the query's key terms, "
                f"it won't be retrieved. Most impactful gap: '{coverage.get('most_impactful_missing', '')}'"
            ),
            "copy_paste": (
                "Add these concepts to your homepage and relevant pages:\n" +
                "\n".join([f"• '{c}' — mention this explicitly 2–3 times" for c in top_missing])
            )
        })

    return {
        "check": "Answer Readiness",
        "score": total,
        "max": 100,
        "page_url": url,
        "word_count": word_count,
        "details": {
            "structure": structure,
            "evidence_density": evidence,
            "schema": schema,
            "quotability": quotability,
            "concept_coverage": coverage,
        },
        "fixes": fixes,
        "homepage_text": text,
    }