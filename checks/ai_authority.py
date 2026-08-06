"""
Check 2: Entity Authority (35% of total score)
= Independent Corroboration + Knowledge Graph Consistency + Entity Salience

(Renamed from "AI Authority" -- "authority" reads as PageRank/backlinks.
What this check actually measures is whether LLMs know who you are and
associate you with the right topic, so "Entity Authority" is more honest.)

Why this check:
- Zhang Kai et al.: Official + News + Vertical = 79-87% of all AI citations.
  If you're not corroborated, you don't enter the candidate pool.
- Entity Salience: a business can have news mentions and still be invisible
  if every mention associates them with the WRONG topic.
  This is the non-obvious check -- the one most GEO tools miss.

All Gemini calls go through llm_utils, which retries on 429 and reports
`available: bool` instead of silently returning a fake zero. Fixes derived
from a sub-check are only generated when that sub-check actually ran --
an unavailable check produces "Unable to compute" in the report, never a
confident-looking finding built on no evidence.
"""

import re
import requests

from google import genai
from . import llm_utils


HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GEOAuditor/1.0)"}
TIMEOUT = 10


# -- Sub-check A: Independent Corroboration ---------------------------------

def check_wikipedia(business_name: str) -> dict:
    """Check if business has a Wikipedia article. Deterministic -- no LLM."""
    try:
        api_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query", "list": "search",
            "srsearch": business_name, "format": "json", "srlimit": 3
        }
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        results = data.get("query", {}).get("search", [])
        biz_lower = business_name.lower()
        found = any(biz_lower in r["title"].lower() or biz_lower in r["snippet"].lower()
                    for r in results)
        return {
            "available": True,
            "found": found,
            "points": 20 if found else 0,
            "results": [r["title"] for r in results[:2]],
        }
    except Exception as e:
        return {"available": False, "found": False, "points": 0, "error": str(e)}


def check_news_mentions(business_name: str, client: genai.Client) -> dict:
    """Use Gemini + Google Search grounding to find independent news mentions."""
    prompt = (
        f'Search for news articles and mentions of "{business_name}" '
        f'from independent sources (not their own website). '
        f'List the source names and URLs you find. Be specific.'
    )
    result = llm_utils.generate(client, prompt, use_search=True, max_tokens=600)
    if not result["available"]:
        return {"available": False, "mention_count": 0, "domains": [], "points": 0,
                "error": result["error"]}

    full_text = result["text"]
    urls = re.findall(r'https?://([^/\s,\)\"]+)', full_text)
    biz_slug = business_name.lower().replace(" ", "")
    external_domains = list(set(
        d for d in urls if biz_slug not in d.lower() and len(d) > 5
    ))
    count = len(external_domains)
    points = min(25, count * 8)

    return {
        "available": True,
        "mention_count": count,
        "domains": external_domains[:5],
        "points": points,
        "response_preview": full_text[:400],
    }


def check_directory_presence(business_name: str, client: genai.Client) -> dict:
    """Check if business is listed on authoritative directories AI trusts."""
    prompt = (
        f'Search for "{business_name}" on Crunchbase, LinkedIn company pages, '
        f'G2, Trustpilot, or similar business directories. '
        f'Tell me which ones have a listing for this company.'
    )
    result = llm_utils.generate(client, prompt, use_search=True, max_tokens=400)
    if not result["available"]:
        return {"available": False, "directories_found": [], "points": 0, "error": result["error"]}

    full_text = result["text"]
    found_directories = [d for d in
                          ["crunchbase", "linkedin", "g2.com", "trustpilot", "glassdoor", "clutch"]
                          if d in full_text.lower()]
    points = min(15, len(found_directories) * 5)
    return {"available": True, "directories_found": found_directories, "points": points}


# -- Sub-check B: Entity Salience --------------------------------------------

def check_entity_salience(business_name: str, category: str, website_text: str,
                           client: genai.Client) -> dict:
    """
    The non-obvious check -- the hub vs node insight.
    A business can be crawlable and corroborated but STILL invisible because
    AI associates it with the wrong topic cluster.
    """
    research_prompt = (
        f'Search for "{business_name}" and tell me: '
        f'What topic or industry does this business appear to be primarily associated with '
        f'based on how it appears across the web? '
        f'List the top 5 topics/concepts most strongly connected to this business name '
        f'in public web content. Be specific and factual.'
    )
    research = llm_utils.generate(client, research_prompt, use_search=True, max_tokens=600)
    if not research["available"]:
        return {
            "available": False, "points": 0, "salience_score": None,
            "salience_match": "unavailable", "current_associations": [],
            "missing_concepts": [], "error": research["error"],
        }

    full_text = research["text"]
    analysis_prompt = f"""
Based on this web research about "{business_name}":

{full_text}

The business wants to be associated with: "{category}"

Respond ONLY in this exact JSON format, no other text:
{{
  "current_associations": ["topic1", "topic2", "topic3", "topic4", "topic5"],
  "target_category": "{category}",
  "salience_match": "high" | "medium" | "low" | "none",
  "salience_score": 0-100,
  "gap_description": "one sentence describing the mismatch if any",
  "missing_concepts": ["concept1", "concept2", "concept3"]
}}

salience_score: 100 = perfectly associated with target category, 0 = completely wrong topic
"""
    analysis = llm_utils.generate_json(client, analysis_prompt, use_search=False, max_tokens=500)
    if not analysis["available"]:
        return {
            "available": False, "points": 0, "salience_score": None,
            "salience_match": "unavailable", "current_associations": [],
            "missing_concepts": [], "error": analysis["error"],
            "research_preview": full_text[:300],
        }

    data = analysis["data"]
    score = data.get("salience_score", 0)
    points = round((score / 100) * 20)

    return {
        "available": True,
        "points": points,
        "salience_score": score,
        "salience_match": data.get("salience_match", "unknown"),
        "current_associations": data.get("current_associations", []),
        "target_category": category,
        "gap_description": data.get("gap_description", ""),
        "missing_concepts": data.get("missing_concepts", []),
        "research_preview": full_text[:300],
    }


# -- Sub-check C: Knowledge Graph Consistency --------------------------------

def check_name_consistency(business_name: str, homepage_html: str, client: genai.Client) -> dict:
    """Check if the business name is consistent across its own site and external mentions."""
    prompt = (
        f'Search for "{business_name}" and list all the different ways '
        f"this company's name appears across web sources. "
        f'Include variations from LinkedIn, Crunchbase, news articles, '
        f"their own website. Are there inconsistencies?"
    )
    result = llm_utils.generate(client, prompt, use_search=True, max_tokens=400)
    if not result["available"]:
        return {"available": False, "canonical_name": business_name,
                "has_inconsistency": False, "points": 0, "error": result["error"]}

    full_text = result["text"]
    variations_mentioned = "variation" in full_text.lower() or "inconsist" in full_text.lower()
    has_issues = variations_mentioned or full_text.lower().count(business_name.lower()) < 2
    points = 10 if not has_issues else 5
    canonical = business_name

    return {
        "available": True,
        "canonical_name": canonical,
        "has_inconsistency": has_issues,
        "points": points,
        "fix_template": (
            f'Use exactly "{canonical}" everywhere:\n'
            f'- Website title tag and meta description\n'
            f'- LinkedIn company page name\n'
            f'- Crunchbase organization name\n'
            f'- Google Business Profile name\n'
            f'- All press releases and directories'
        ),
    }


# -- Main runner --------------------------------------------------------------

def run(business_name: str, category: str, location: str,
        homepage_text: str, client: genai.Client) -> dict:
    """
    Run all Entity Authority sub-checks. Max score: 100, renormalized
    across whichever sub-checks actually returned data (see unavailable
    handling below and compute_geo_score in main.py).

    Sub-check breakdown:
      Wikipedia presence:         20 pts
      News mentions (3+ = max):   25 pts
      Directory listings:         15 pts
      Entity salience match:      20 pts
      Name consistency:           10 pts
    """
    print("  -> Checking Wikipedia presence...")
    wiki = check_wikipedia(business_name)

    print("  -> Checking news mentions (Gemini + search)...")
    news = check_news_mentions(business_name, client)

    print("  -> Checking directory listings...")
    directories = check_directory_presence(business_name, client)

    print("  -> Checking entity salience (the hub vs node check)...")
    salience = check_entity_salience(business_name, category, homepage_text, client)

    print("  -> Checking name consistency...")
    consistency = check_name_consistency(business_name, homepage_text, client)

    sub_checks = {
        "wikipedia": (wiki, 20),
        "news_mentions": (news, 25),
        "directories": (directories, 15),
        "entity_salience": (salience, 20),
        "name_consistency": (consistency, 10),
    }

    earned = sum(c["points"] for c, _ in sub_checks.values() if c.get("available"))
    max_available = sum(m for c, m in sub_checks.values() if c.get("available"))
    unavailable_count = sum(1 for c, _ in sub_checks.values() if not c.get("available"))

    # Renormalize to /100 across only the sub-checks that actually ran.
    score = round((earned / max_available) * 100) if max_available > 0 else 0

    # Build fixes -- ONLY from sub-checks that actually returned data.
    fixes = []

    if wiki.get("available") and not wiki["found"]:
        fixes.append({
            "priority": 1, "effort": "1-2 hours", "expected_impact": 20, "confidence": "High",
            "title": "No Wikipedia presence found",
            "detail": (
                "Wikipedia is a top-cited domain by AI systems. AI uses it as a primary "
                "trust signal for entity recognition."
            ),
            "copy_paste": (
                f"Draft Wikipedia description for {business_name}:\n\n"
                f'"{business_name} is a {category} company'
                f'{" based in " + location if location else ""}. '
                f'[Add founding year, notable facts, key products/services.]"\n\n'
                f"Note: Wikipedia requires notability. Build news mentions first, "
                f"then submit. Consider adding to relevant Wikipedia category pages first."
            )
        })

    if news.get("available") and news["mention_count"] < 3:
        fixes.append({
            "priority": 2, "effort": "2-4 weeks",
            "expected_impact": max(0, 25 - news["points"]), "confidence": "Medium",
            "title": f"Only {news['mention_count']} independent news mention(s) found",
            "detail": (
                "AI systems require corroboration from multiple independent sources "
                "before they treat a business as a trustworthy citation candidate."
            ),
            "copy_paste": (
                "Press release template you can use immediately:\n\n"
                f"FOR IMMEDIATE RELEASE\n\n"
                f"{business_name} [Verb: Launches/Announces/Partners] [Specific Achievement]\n\n"
                f"{location or 'City'}, [Date] -- {business_name}, a {category} company, "
                f"today announced [specific, newsworthy fact with a number if possible]. "
                f'"[Quote from founder/CEO]," said [Name], [Title] of {business_name}.\n\n'
                f"[One paragraph about the business with factual details.]\n\n"
                f"About {business_name}: [2-sentence factual description]\n"
                f"Contact: [email]"
            )
        })

    if salience.get("available") and salience.get("salience_match") in ["low", "none"]:
        missing = salience.get("missing_concepts", [])
        fixes.append({
            "priority": 1, "effort": "2-4 hours (content)",
            "expected_impact": max(0, 20 - salience["points"]), "confidence": "Medium",
            "title": "AI associates you with the wrong topic",
            "detail": (
                f"Current AI association: {', '.join(salience.get('current_associations', [])[:3]) or 'unclear'}. "
                f"Target: {category}. "
                f"{salience.get('gap_description', '')}"
            ),
            "copy_paste": (
                "Missing concepts -- add these to your homepage and key pages:\n\n" +
                "\n".join([f"- Mention '{c}' explicitly (at least 2-3 times)" for c in missing[:5]])
                if missing else
                f"Add a dedicated page or section clearly about: {category}. "
                f"Use the exact vocabulary your target audience searches for."
            )
        })

    if consistency.get("available") and consistency.get("has_inconsistency"):
        fixes.append({
            "priority": 2, "effort": "1 hour", "expected_impact": 5, "confidence": "Low",
            "title": "Inconsistent business name across sources",
            "detail": "AI systems aggregate signals by entity name. Inconsistencies split your authority.",
            "copy_paste": consistency.get("fix_template", "")
        })

    return {
        "check": "Entity Authority",
        "score": score,
        "max": 100,
        "unavailable_count": unavailable_count,
        "total_sub_checks": len(sub_checks),
        "details": {
            "wikipedia": wiki,
            "news_mentions": news,
            "directories": directories,
            "entity_salience": salience,
            "name_consistency": consistency,
        },
        "fixes": fixes,
    }