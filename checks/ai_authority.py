"""
Check 2: AI Authority (35% of total score)
= Independent Corroboration + Knowledge Graph Consistency + Entity Salience

Why this check:
- Zhang Kai et al.: Official + News + Vertical = 79–87% of all AI citations.
  If you're not corroborated, you don't enter the candidate pool.
- Entity Salience: a business can have news mentions and still be invisible
  if every mention associates them with the WRONG topic.
  This is the non-obvious check — the one most GEO tools miss.
"""

import re
import requests
import os
import anthropic


HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GEOAuditor/1.0)"}
TIMEOUT = 10


# ── Sub-check A: Independent Corroboration ─────────────────────────────────

def check_wikipedia(business_name: str) -> dict:
    """Check if business has a Wikipedia article."""
    try:
        api_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query", "list": "search",
            "srsearch": business_name, "format": "json", "srlimit": 3
        }
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        results = data.get("query", {}).get("search", [])
        # Check if any result closely matches the business name
        biz_lower = business_name.lower()
        found = any(biz_lower in r["title"].lower() or biz_lower in r["snippet"].lower()
                    for r in results)
        return {
            "found": found,
            "points": 20 if found else 0,
            "results": [r["title"] for r in results[:2]],
        }
    except Exception as e:
        return {"found": False, "points": 0, "error": str(e)}


def check_news_mentions(business_name: str, client: anthropic.Anthropic) -> dict:
    """
    Use Claude with web search to find independent news mentions.
    Counts unique domains — not the business's own site.
    """
    try:
        query = f'"{business_name}" news coverage site mentions -site:{business_name.lower().replace(" ", "")}.com'
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    f'Search for news articles and mentions of "{business_name}" '
                    f'from independent sources (not their own website). '
                    f'List the source names and URLs you find. Be specific.'
                )
            }]
        )
        full_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        # Extract domains mentioned
        urls = re.findall(r'https?://([^/\s,\)\"]+)', full_text)
        # Filter out the business's own domain
        biz_slug = business_name.lower().replace(" ", "")
        external_domains = list(set(
            d for d in urls if biz_slug not in d.lower() and len(d) > 5
        ))

        count = len(external_domains)
        points = min(25, count * 8)  # 8 pts per source, max 25

        return {
            "mention_count": count,
            "domains": external_domains[:5],
            "points": points,
            "response_preview": full_text[:400],
        }
    except Exception as e:
        return {"mention_count": 0, "domains": [], "points": 0, "error": str(e)}


def check_directory_presence(business_name: str, client: anthropic.Anthropic) -> dict:
    """
    Check if business is listed on authoritative directories AI trusts:
    Crunchbase, LinkedIn, G2, Trustpilot, industry databases.
    """
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    f'Search for "{business_name}" on Crunchbase, LinkedIn company pages, '
                    f'G2, Trustpilot, or similar business directories. '
                    f'Tell me which ones have a listing for this company.'
                )
            }]
        )
        full_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        found_directories = []
        for directory in ["crunchbase", "linkedin", "g2.com", "trustpilot", "glassdoor", "clutch"]:
            if directory in full_text.lower():
                found_directories.append(directory)

        points = min(15, len(found_directories) * 5)
        return {
            "directories_found": found_directories,
            "points": points,
        }
    except Exception as e:
        return {"directories_found": [], "points": 0, "error": str(e)}


# ── Sub-check B: Entity Salience ────────────────────────────────────────────

def check_entity_salience(business_name: str, category: str, website_text: str, client: anthropic.Anthropic) -> dict:
    """
    The non-obvious check — the hub vs node insight from our QPiAI discussion.

    A business can be crawlable and corroborated but STILL invisible because
    AI associates it with the wrong topic cluster.

    Example: IIIT Dharwad is mentioned everywhere — for engineering admissions.
    Never for quantum computing. So when you ask about quantum computing, it's invisible.

    We check: what topic does AI currently associate this business with?
    Does it match their actual category?
    """
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    f'Search for "{business_name}" and tell me: '
                    f'What topic or industry does this business appear to be primarily associated with '
                    f'based on how it appears across the web? '
                    f'List the top 5 topics/concepts most strongly connected to this business name '
                    f'in public web content. Be specific and factual.'
                )
            }]
        )
        full_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        # Now use Claude (no search) to assess salience match
        salience_check = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"""
Based on this web research about "{business_name}":

{full_text}

The business wants to be associated with: "{category}"

Please respond ONLY in this exact JSON format:
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
            }]
        )
        import json
        salience_text = salience_check.content[0].text.strip()
        # Strip markdown code fences if present
        salience_text = re.sub(r"```json|```", "", salience_text).strip()
        salience_data = json.loads(salience_text)

        score = salience_data.get("salience_score", 0)
        # Scale to 20 points max for this sub-check
        points = round((score / 100) * 20)

        return {
            "points": points,
            "salience_score": score,
            "salience_match": salience_data.get("salience_match", "unknown"),
            "current_associations": salience_data.get("current_associations", []),
            "target_category": category,
            "gap_description": salience_data.get("gap_description", ""),
            "missing_concepts": salience_data.get("missing_concepts", []),
            "research_preview": full_text[:300],
        }
    except Exception as e:
        return {
            "points": 0,
            "salience_score": 0,
            "salience_match": "unknown",
            "current_associations": [],
            "missing_concepts": [],
            "error": str(e),
        }


# ── Sub-check C: Knowledge Graph Consistency ───────────────────────────────

def check_name_consistency(business_name: str, homepage_html: str, client: anthropic.Anthropic) -> dict:
    """
    Check if the business name is consistent across its own site and external mentions.
    Inconsistency = AI systems can't reliably aggregate signals about this entity.
    e.g. "Acme Corp" vs "AcmeCorp" vs "ACME Corporation" = three different entities to AI.
    """
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    f'Search for "{business_name}" and list all the different ways '
                    f'this company\'s name appears across web sources. '
                    f'Include variations from LinkedIn, Crunchbase, news articles, '
                    f'their own website. Are there inconsistencies?'
                )
            }]
        )
        full_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        # Check for variation mentions
        variations_mentioned = "variation" in full_text.lower() or "inconsist" in full_text.lower()
        has_issues = variations_mentioned or full_text.lower().count(business_name.lower()) < 2

        points = 10 if not has_issues else 5
        canonical = business_name  # Use input as the canonical form

        return {
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
    except Exception as e:
        return {"canonical_name": business_name, "has_inconsistency": False, "points": 10, "error": str(e)}


# ── Main runner ─────────────────────────────────────────────────────────────

def run(business_name: str, category: str, location: str,
        homepage_text: str, client: anthropic.Anthropic) -> dict:
    """
    Run all AI Authority sub-checks. Max score: 100.

    Sub-check breakdown:
      Wikipedia presence:         20 pts
      News mentions (3+ = max):   25 pts
      Directory listings:         15 pts
      Entity salience match:      20 pts
      Name consistency:           10 pts
      Bonus (reserved):           10 pts (future)
    """
    print("  → Checking Wikipedia presence...")
    wiki = check_wikipedia(business_name)

    print("  → Checking news mentions (web search)...")
    news = check_news_mentions(business_name, client)

    print("  → Checking directory listings...")
    directories = check_directory_presence(business_name, client)

    print("  → Checking entity salience (the hub vs node check)...")
    salience = check_entity_salience(business_name, category, homepage_text, client)

    print("  → Checking name consistency...")
    consistency = check_name_consistency(business_name, homepage_text, client)

    total = wiki["points"] + news["points"] + directories["points"] + salience["points"] + consistency["points"]
    total = min(total, 100)

    # Build fixes
    fixes = []

    if not wiki["found"]:
        fixes.append({
            "priority": 1,
            "effort": "1–2 hours",
            "title": "No Wikipedia presence found",
            "detail": (
                "Wikipedia is the #2 most cited domain by AI (Zhang Kai et al., 2026). "
                "AI systems use it as a primary trust signal for entity recognition."
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

    if news["mention_count"] < 3:
        fixes.append({
            "priority": 2,
            "effort": "2–4 weeks",
            "title": f"Only {news['mention_count']} independent news mention(s) found",
            "detail": (
                "AI systems require corroboration from multiple independent sources. "
                "Zhang Kai et al. show Official + News + Vertical = 87% of AI citations. "
                "You need to be in those source pools."
            ),
            "copy_paste": (
                "Press release template you can use immediately:\n\n"
                f"FOR IMMEDIATE RELEASE\n\n"
                f"{business_name} [Verb: Launches/Announces/Partners] [Specific Achievement]\n\n"
                f"{location or 'City'}, [Date] — {business_name}, a {category} company, "
                f"today announced [specific, newsworthy fact with a number if possible]. "
                f'"[Quote from founder/CEO]," said [Name], [Title] of {business_name}.\n\n'
                f"[One paragraph about the business with factual details.]\n\n"
                f"About {business_name}: [2-sentence factual description]\n"
                f"Contact: [email]"
            )
        })

    if salience.get("salience_match") in ["low", "none", "unknown"]:
        missing = salience.get("missing_concepts", [])
        fixes.append({
            "priority": 1,
            "effort": "2–4 hours (content)",
            "title": f"AI associates you with the wrong topic",
            "detail": (
                f"Current AI association: {', '.join(salience.get('current_associations', [])[:3])}. "
                f"Target: {category}. "
                f"{salience.get('gap_description', '')}"
            ),
            "copy_paste": (
                f"Missing concepts — add these to your homepage and key pages:\n\n" +
                "\n".join([f"• Mention '{c}' explicitly (at least 2–3 times)" for c in missing[:5]])
                if missing else
                f"Add a dedicated page or section clearly about: {category}. "
                f"Use the exact vocabulary your target audience searches for."
            )
        })

    if consistency.get("has_inconsistency"):
        fixes.append({
            "priority": 2,
            "effort": "1 hour",
            "title": "Inconsistent business name across sources",
            "detail": "AI systems aggregate signals by entity name. Inconsistencies split your authority.",
            "copy_paste": consistency.get("fix_template", "")
        })

    return {
        "check": "AI Authority",
        "score": total,
        "max": 100,
        "details": {
            "wikipedia": wiki,
            "news_mentions": news,
            "directories": directories,
            "entity_salience": salience,
            "name_consistency": consistency,
        },
        "fixes": fixes,
    }