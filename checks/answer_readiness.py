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

This is the most actionable check -- fixes go directly into the business's
own content.
"""

import re
import json
import requests
from bs4 import BeautifulSoup

from google import genai
from . import llm_utils

from schemas.quotability import Quotability
from schemas.concept_coverage import ConceptCoverage

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GEOAuditor/1.0)"}
TIMEOUT = 15


def fetch_page_content(url: str) -> dict:
    """Fetch and clean page content for analysis."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(resp.text, "lxml")

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
    """Check structural markers of a high-influence evidence container."""
    h1 = len(soup.find_all("h1"))
    h2 = len(soup.find_all("h2"))
    h3 = len(soup.find_all("h3"))
    total_headings = h1 + h2 + h3
    paragraphs = len(soup.find_all("p"))
    lists = len(soup.find_all(["ul", "ol"]))

    if word_count >= 2000:
        wc_points, wc_label = 20, "Strong"
    elif word_count >= 1000:
        wc_points, wc_label = 12, "Adequate"
    elif word_count >= 500:
        wc_points, wc_label = 6, "Thin"
    else:
        wc_points, wc_label = 0, "Very thin"

    if total_headings >= 6:
        h_points, h_label = 15, "Well structured"
    elif total_headings >= 3:
        h_points, h_label = 8, "Lightly structured"
    else:
        h_points, h_label = 0, "No structure"

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


# Numbers regex, fixed. The old pattern required a number + whitespace + a
# fixed English unit word (%, million, customers...), so "64-qubit" (hyphen,
# not whitespace) and "96x" (not in the unit list) were invisible to it even
# though they're exactly the kind of quantitative claim this check exists to
# reward. New pattern catches three shapes:
#   1. number-word          e.g. "64-qubit", "25-qubit"
#   2. number x / X         e.g. "96x", "10X"
#   3. number + known unit  e.g. "300 qubits", "50%", "12 million customers"
NUMBER_HYPHEN_UNIT = r'\b\d[\d,]*-[a-zA-Z]+\b'
NUMBER_MULTIPLIER = r'\b\d[\d,]*\.?\d*\s*[xX]\b'
NUMBER_WITH_UNIT = (
    r'\b\d[\d,]*\.?\d*\s*'
    r'(%|percent|million|billion|thousand|customers|users|years|countries|'
    r'cities|products|employees|clients|qubits?|nodes?|cores?|gb|tb|mb|ghz|mhz)\b'
)


def check_evidence_density(text: str) -> dict:
    """
    Check for evidence genres that boost AI absorption.
    Based on Zhang Kai et al. evidence genre uplift data:
      Numbers/stats: +61.5%
      Definitions:   +57.3%
      Comparisons:   +55.3%
    Q&A format alone: -5.7% (flag this)
    """
    hyphen_hits = re.findall(NUMBER_HYPHEN_UNIT, text)
    mult_hits = re.findall(NUMBER_MULTIPLIER, text)
    unit_hits = re.findall(NUMBER_WITH_UNIT, text, re.IGNORECASE)

    # all_number_matches = list(set(hyphen_hits + mult_hits +
    #                                [m if isinstance(m, str) else m[0] for m in
    #                                 re.finditer(NUMBER_WITH_UNIT, text, re.IGNORECASE)]))
    # Simpler, correct count: union of all matched spans across the 3 patterns
    numbers_found = []
    for pat in (NUMBER_HYPHEN_UNIT, NUMBER_MULTIPLIER, NUMBER_WITH_UNIT):
        numbers_found.extend(m.group(0) for m in re.finditer(pat, text, re.IGNORECASE))
    numbers_found = list(dict.fromkeys(numbers_found))  # dedupe, keep order

    definition_pattern = r'\b(is a|are a|defined as|refers to|means that|is the|is an)\b'
    definitions_found = re.findall(definition_pattern, text, re.IGNORECASE)

    comparison_pattern = r'\b(unlike|compared to|versus|vs\.?|better than|different from|while|whereas|in contrast)\b'
    comparisons_found = re.findall(comparison_pattern, text, re.IGNORECASE)

    qa_pattern = r'\b(Q:|A:|FAQ|Frequently Asked|What is|How do|Why should)\b'
    qa_found = len(re.findall(qa_pattern, text, re.IGNORECASE))
    has_qa = qa_found > 3

    num_points = 20 if len(numbers_found) >= 3 else (10 if len(numbers_found) >= 1 else 0)
    def_points = 10 if len(definitions_found) >= 3 else (5 if len(definitions_found) >= 1 else 0)
    cmp_points = 5 if len(comparisons_found) >= 2 else 0
    qa_penalty = -5 if has_qa and len(numbers_found) < 2 else 0

    total = max(0, num_points + def_points + cmp_points + qa_penalty)

    return {
        "numbers_count": len(numbers_found),
        "numbers_examples": numbers_found[:5],
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
    """Check for schema.org structured data -- helps AI identify entity type."""
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


def check_quotability(text: str, business_name: str, category: str, client: genai.Client) -> dict:
    """
    Check if the page contains a clear, standalone, extractable sentence
    that an AI could quote directly in an answer about the business.
    """
    sample = text[:3000]
    prompt = f"""
Analyze this website content for "{business_name}" (category: {category}).

Content:
{sample}

Answer in this exact JSON format, no other text:
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
    result = llm_utils.generate_json(client, prompt, schema=Quotability, use_search=False, max_tokens=500)
    if not result["available"]:
        return {
            "available": False, "has_quotable_sentence": False, "quotable_sentence": "",
            "generated_sentence": "", "missing_elements": [], "points": 0,
            "error": result["error"],
        }

    data = result["data"]
    points = 10 if data.has_quotable_sentence else 0

    return {
        "available": True,
        "has_quotable_sentence": data.has_quotable_sentence,
        "quotable_sentence": data.quotable_sentence,
        "reason": data.reason,
        "generated_sentence": data.generated_quotable_sentence,
        "missing_elements": data.missing_elements,
        "points": points,
    }


def check_concept_coverage(text: str, category: str, top_competitors: list,
                            client: genai.Client) -> dict:
    """
    The Retrieval Coverage insight -- LLMs retrieve chunks, not whole websites.
    Compare this business's vocabulary against competitors who ARE cited.
    """
    competitor_str = ", ".join(
        c["name"]
        for c in top_competitors
    ) if top_competitors else "industry leaders"
    research_prompt = (
        f"What are the 10 most important concepts, topics, and specific terms "
        f"that define the '{category}' space? "
        f"Look at what {competitor_str} talk about on their websites. "
        f"Give me a list of the key vocabulary and concepts a business in this space MUST mention."
    )
    research = llm_utils.generate(client, research_prompt, use_search=True, max_tokens=700)
    if not research["available"]:
        return {
            "available": False, "covered_concepts": [], "missing_concepts": [],
            "coverage_score": None, "most_impactful_missing": "", "points": 0,
            "error": research["error"],
        }

    competitor_concepts_text = research["text"]
    analysis_prompt = f"""
Key concepts for {category} space (from competitor research):
{competitor_concepts_text[:1000]}

Our website content:
{text[:2000]}

Which key concepts from the category ARE present in our content?
Which are MISSING?

Respond in this exact JSON format, no other text:
{{
  "covered_concepts": ["concept1", "concept2"],
  "missing_concepts": ["concept3", "concept4"],
  "coverage_score": 0-100,
  "most_impactful_missing": "the single most important missing concept"
}}
"""
    analysis = llm_utils.generate_json(client, analysis_prompt, schema=ConceptCoverage, use_search=False, max_tokens=600)
    if not analysis["available"]:
        return {
            "available": False, "covered_concepts": [], "missing_concepts": [],
            "coverage_score": None, "most_impactful_missing": "", "points": 0,
            "error": analysis["error"],
        }

    data = analysis["data"]
    coverage_score = data.coverage_score
    points = round((coverage_score / 100) * 10)

    return {
        "available": True,
        "covered_concepts": data.covered_concepts,
        "missing_concepts": data.missing_concepts,
        "coverage_score": coverage_score,
        "most_impactful_missing": data.most_impactful_missing,
        "points": points,
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
        top_competitors: list, client: genai.Client) -> dict:
    """
    Run all Answer Readiness checks. Max score: 100, renormalized across
    whichever LLM sub-checks actually returned data.

    Sub-check breakdown:
      Structure (word count + headings):   35 pts  (deterministic)
      Evidence density (stats/def/comp):   35 pts  (deterministic)
      Schema markup:                       15 pts  (deterministic)
      Quotable sentence:                   10 pts  (Gemini)
      Concept coverage:                    10 pts  (Gemini)
    """
    print("  -> Fetching homepage content...")
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

    print("  -> Analysing structure...")
    structure = check_structure(soup, word_count)

    print("  -> Analysing evidence density...")
    evidence = check_evidence_density(text)

    print("  -> Checking schema markup...")
    schema = check_schema_markup(soup, business_name, url)

    print("  -> Checking quotability (Gemini)...")
    quotability = check_quotability(text, business_name, category, client)

    print("  -> Checking concept coverage vs competitors (Gemini)...")
    coverage = check_concept_coverage(text, category, top_competitors, client)

    # Deterministic sub-checks are always "available"; LLM ones may not be.
    sub_checks = {
        "structure": ({"available": True, "points": structure["total_points"]}, 35),
        "evidence_density": ({"available": True, "points": evidence["evidence_points"]}, 35),
        "schema": ({"available": True, "points": schema["points"]}, 15),
        "quotability": (quotability, 10),
        "concept_coverage": (coverage, 10),
    }
    earned = sum(c["points"] for c, _ in sub_checks.values() if c.get("available"))
    max_available = sum(m for c, m in sub_checks.values() if c.get("available"))
    unavailable_count = sum(1 for c, _ in sub_checks.values() if not c.get("available"))
    score = round((earned / max_available) * 100) if max_available > 0 else 0

    fixes = []

    if structure["word_count"] < 1000:
        fixes.append({
            "priority": 1, "effort": "2-4 hours",
            "expected_impact": 20 - structure["word_count_points"], "confidence": "High",
            "title": f"Homepage provides relatively few standalone evidence units ({word_count} words)",
            "detail": (
                "This isn't about SEO word count -- it's about giving AI enough standalone "
                "facts to extract and cite. High-influence pages give models many independent "
                "evidence units (definitions, numbers, comparisons) to pull from; thin pages "
                "give them almost nothing to work with."
            ),
            "copy_paste": (
                f"Add these sections to your homepage to add real evidence units:\n"
                f"- What is {business_name}? (clear definition, 2-3 sentences)\n"
                f"- Key numbers (customers, cities, years, products -- with actual figures)\n"
                f"- What makes you different (specific, not generic)\n"
                f"- How it works (3-5 steps)\n"
                f"- Who it's for (specific customer types)"
            )
        })

    if structure["headings"]["total"] < 3:
        fixes.append({
            "priority": 2, "effort": "30 minutes",
            "expected_impact": 15 - structure["heading_points"], "confidence": "High",
            "title": "No structured headings -- AI can't navigate your content",
            "detail": (
                "Headings let AI extract specific sections as standalone answer units instead "
                "of having to parse one undifferentiated block of text."
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
            "priority": 1, "effort": "1 hour",
            "expected_impact": 20 - evidence["breakdown"]["numbers"], "confidence": "High",
            "title": "Too few quantitative facts for AI to extract",
            "detail": (
                "AI engines prefer pages that supply extractable evidence -- facts, figures, "
                "comparisons -- over unsupported claims."
            ),
            "copy_paste": (
                f"Add specific numbers to your homepage. Examples for {business_name}:\n"
                f"- 'Serving X+ customers across Y cities'\n"
                f"- 'Founded in [year] with [N] employees'\n"
                f"- 'Reduces [metric] by X% on average'\n"
                f"- '[N] years of experience in {category}'\n"
                f"Replace placeholders with your real numbers."
            )
        })

    if evidence["has_qa_format"] and evidence["qa_penalty_applied"]:
        fixes.append({
            "priority": 2, "effort": "2 hours", "expected_impact": 5, "confidence": "Medium",
            "title": "FAQ format without evidence density (counterintuitive finding)",
            "detail": (
                "Q&A format alone does not reliably improve AI absorption -- FAQ pages create "
                "short, isolated answers without the evidence density AI needs to synthesise "
                "across complex queries. Your FAQ pages need real statistics, definitions, and "
                "comparisons, not just question-and-answer wrappers."
            ),
            "copy_paste": (
                "For each FAQ answer, add at minimum:\n"
                "- One specific number or statistic\n"
                "- One clear definition ('{X} is...')\n"
                "- One comparison to alternatives"
            )
        })

    if not schema["has_schema"]:
        desc = quotability.get("generated_sentence") or f"{business_name} is a {category} company."
        schema_code = generate_schema_markup(business_name, category, location, url, desc)
        fixes.append({
            "priority": 2, "effort": "15 minutes", "expected_impact": 15, "confidence": "High",
            "title": "No schema markup -- AI can't identify your entity type",
            "detail": "Schema.org markup tells AI systems what type of entity you are, helping with entity recognition.",
            "copy_paste": f"Paste this inside your <head> tag:\n\n{schema_code}"
        })

    if quotability.get("available") and not quotability["has_quotable_sentence"] and quotability.get("generated_sentence"):
        fixes.append({
            "priority": 1, "effort": "10 minutes", "expected_impact": 10, "confidence": "High",
            "title": "No quotable sentence -- AI has nothing to extract and attribute to you",
            "detail": (
                "AI needs a standalone, factual sentence it can quote or paraphrase when "
                "mentioning your business. Your homepage currently doesn't have one."
            ),
            "copy_paste": (
                f"Add this sentence to your homepage and About page:\n\n"
                f'"{quotability["generated_sentence"]}"'
            )
        })

    if coverage.get("available") and coverage.get("missing_concepts"):
        top_missing = coverage["missing_concepts"][:5]
        fixes.append({
            "priority": 2, "effort": "2-3 hours",
            "expected_impact": max(0, 10 - coverage["points"]), "confidence": "Medium",
            "title": f"Missing {len(coverage['missing_concepts'])} key concepts from your content",
            "detail": (
                f"Your competitors who get cited use vocabulary you don't. LLMs retrieve "
                f"content chunks -- if the chunk doesn't contain the query's key terms, it "
                f"won't be retrieved. Most impactful gap: '{coverage.get('most_impactful_missing', '')}'"
            ),
            "copy_paste": (
                "Add these concepts to your homepage and relevant pages:\n" +
                "\n".join([f"- '{c}' -- mention this explicitly 2-3 times" for c in top_missing])
            )
        })

    return {
        "check": "Answer Readiness",
        "score": score,
        "max": 100,
        "unavailable_count": unavailable_count,
        "total_sub_checks": len(sub_checks),
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