"""
Live Visibility Test — the opening of every report.
Queries multiple AI models and checks if the business is mentioned.

Real: GEMINI API (with web search tool)
Real if key present: Groq (Llama 3 — tests training data, no live search)
Real if key present: Perplexity API
Mock (labeled): any platform where key is missing
"""

import os
import re
from google import genai
from google.genai import types

def build_queries(business_name: str, category: str, location: str) -> list[str]:
    """Build 3 queries that a real user would ask about this business's market."""
    return [
        f"top {category} companies{' in ' + location if location else ''}",
        f"who are the best {category} providers{' in ' + location if location else ''}?",
        f"recommend a {category} business{' in ' + location if location else ''}",
    ]


def check_mention(response_text: str, business_name: str) -> bool:
    """Check if the business name appears in the response."""
    name_lower = business_name.lower()
    response_lower = response_text.lower()
    # Also check for partial matches (e.g. "Acme" for "Acme Corp")
    name_parts = [p for p in name_lower.split() if len(p) > 3]
    return name_lower in response_lower or any(p in response_lower for p in name_parts)


def extract_competitors(response_text: str, business_name: str) -> list[str]:
    """
    Extract what entities ARE mentioned in the response.
    Simple heuristic: capitalized noun phrases that aren't the business.
    """
    competitors = []
    # Find capitalized runs of words (likely company/entity names)
    matches = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', response_text)
    seen = set()
    biz_lower = business_name.lower()
    for m in matches:
        if m.lower() != biz_lower and len(m) > 3 and m not in seen:
            seen.add(m)
            competitors.append(m)
    # Return top 5 most frequent
    from collections import Counter
    freq = Counter(competitors)
    return [c for c, _ in freq.most_common(5)]


def test_gemini(query: str, business_name: str, client: genai.Client) -> dict:
    """Test visibility in Gemini with web search."""
    try:
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=500,
        )
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=query,
            config=config
        )
        # Collect all text from response
        full_text = " ".join(
            block.text for block in response.content
            if hasattr(block, "text")
        )
        mentioned = check_mention(full_text, business_name)
        return {
            "platform": "Gemini",
            "real": True,
            "mentioned": mentioned,
            "response_preview": full_text[:400],
            "competitors": extract_competitors(full_text, business_name) if not mentioned else [],
        }
    except Exception as e:
        return {
            "platform": "Gemini",
            "real": True,
            "mentioned": False,
            "error": str(e),
            "competitors": [],
        }


def test_groq(query: str, business_name: str) -> dict:
    """
    Test Groq (Llama 3) — no web search.
    This tests training data presence, not live search.
    If no API key, returns labeled mock.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return {
            "platform": "Llama 3 (Groq)",
            "real": False,
            "mock": True,
            "mentioned": False,
            "note": "MOCK — no GROQ_API_KEY set. Add key to .env to enable real test.",
            "competitors": [],
        }

    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 400,
            },
            timeout=15,
        )
        text = resp.json()["choices"][0]["message"]["content"]
        mentioned = check_mention(text, business_name)
        return {
            "platform": "Llama 3 (Groq)",
            "real": True,
            "mock": False,
            "mentioned": mentioned,
            "response_preview": text[:400],
            "note": "No web search — tests if business appears in model training data.",
            "competitors": extract_competitors(text, business_name) if not mentioned else [],
        }
    except Exception as e:
        return {
            "platform": "Llama 3 (Groq)",
            "real": True,
            "mock": False,
            "mentioned": False,
            "error": str(e),
            "competitors": [],
        }


def test_perplexity(query: str, business_name: str) -> dict:
    """
    Test Perplexity — live web search.
    Zhang Kai et al. show Perplexity cites the broadest source pool (16.35 avg).
    Best platform for visibility testing.
    """
    perp_key = os.getenv("PERPLEXITY_API_KEY")
    if not perp_key:
        return {
            "platform": "Perplexity",
            "real": False,
            "mock": True,
            "mentioned": False,
            "note": "MOCK — no PERPLEXITY_API_KEY set. Add key to .env to enable real test.",
            "competitors": [],
        }

    try:
        import requests
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {perp_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-sonar-large-128k-online",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 400,
            },
            timeout=20,
        )
        text = resp.json()["choices"][0]["message"]["content"]
        mentioned = check_mention(text, business_name)
        return {
            "platform": "Perplexity",
            "real": True,
            "mock": False,
            "mentioned": mentioned,
            "response_preview": text[:400],
            "competitors": extract_competitors(text, business_name) if not mentioned else [],
        }
    except Exception as e:
        return {
            "platform": "Perplexity",
            "real": True,
            "mock": False,
            "mentioned": False,
            "error": str(e),
            "competitors": [],
        }


def run(business_name: str, category: str, location: str, client: genai.Client) -> dict:
    """
    Run all visibility tests across platforms and queries.
    Returns structured results for the report opening section.
    """
    queries = build_queries(business_name, category, location)
    results = []

    for query in queries:
        gemini_result = test_gemini(query, business_name, client)
        gemini_result["query"] = query
        results.append(gemini_result)

        groq_result = test_groq(query, business_name)
        groq_result["query"] = query
        results.append(groq_result)

        perp_result = test_perplexity(query, business_name)
        perp_result["query"] = query
        results.append(perp_result)

    total_tests = len(results)
    mentions = sum(1 for r in results if r.get("mentioned"))
    visibility_pct = round((mentions / total_tests) * 100) if total_tests > 0 else 0

    # Collect all competitors mentioned across responses
    all_competitors = []
    for r in results:
        all_competitors.extend(r.get("competitors", []))
    from collections import Counter
    top_competitors = [c for c, _ in Counter(all_competitors).most_common(3)]

    # Per-platform summary
    platforms = {}
    for r in results:
        p = r["platform"]
        if p not in platforms:
            platforms[p] = {"mentioned": 0, "total": 0, "mock": r.get("mock", False)}
        platforms[p]["total"] += 1
        if r.get("mentioned"):
            platforms[p]["mentioned"] += 1

    # Training data insight (Groq-specific)
    groq_results = [r for r in results if "Groq" in r["platform"] and not r.get("mock")]
    training_data_visible = any(r.get("mentioned") for r in groq_results) if groq_results else None

    return {
        "business_name": business_name,
        "category": category,
        "location": location,
        "queries": queries,
        "results": results,
        "visibility_pct": visibility_pct,
        "mentions": mentions,
        "total_tests": total_tests,
        "top_competitors": top_competitors,
        "platforms": platforms,
        "training_data_visible": training_data_visible,
    }