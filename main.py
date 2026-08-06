"""
GEO Auditor — Main Entry Point
Usage: python main.py <url> <business_name> <category> [location]
"""

import sys
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Import checks
from checks import crawlability, ai_authority, answer_readiness
from visibility import live_test
from report import generator


def compute_geo_score(c1: dict, c2: dict, c3: dict) -> dict:
    """
    Final GEO score = weighted combination of three checks.
    Weights based on research:
      C1 Crawlability:    20% — gateway, necessary but rarely the main failure
      C2 AI Authority:    35% — source identity is a strong entry condition
      C3 Answer Readiness: 45% — absorption drives actual answer influence
    """
    weighted = ( 0.20 * c1["score"] + 0.35 * c2["score"] + 0.45 * c3["score"] )
    score = round(weighted)

    if score >= 85:
        band = "Strong"
        description = "AI engines are likely citing you for relevant queries."
    elif score >= 65:
        band = "Moderate"
        description = "You're in the candidate pool but poorly absorbed into answers."
    elif score >= 45:
        band = "Weak"
        description = "You're largely invisible to AI queries in your category."
    else:
        band = "Critical"
        description = "Fundamental barriers are preventing any AI visibility."

    return {
        "score": score,
        "band": band,
        "description": description,
        "breakdown": {
            "crawlability": {"score": c1["score"], "weight": 0.20, "contribution": round(0.20 * c1["score"])},
            "ai_authority": {"score": c2["score"], "weight": 0.35, "contribution": round(0.35 * c2["score"])},
            "answer_readiness": {"score": c3["score"], "weight": 0.45, "contribution": round(0.45 * c3["score"])},
        }
    }


def run_audit(url: str, business_name: str, category: str, location: str = "") -> dict:
    """Run the full GEO audit and return structured results."""

    # Initialise Gemini client (used across multiple checks)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set in .env")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    print(f"\n{'='*60}")
    print(f"GEO Audit: {business_name}")
    print(f"URL: {url}")
    print(f"Category: {category}")
    print(f"{'='*60}\n")

    # ── Step 0: Live Visibility Test ──────────────────────────────
    print("[ 0/3 ] Running live visibility test across AI platforms...")
    visibility = live_test.run(business_name, category, location, client)
    print(f"        Visibility: {visibility['visibility_pct']}% ({visibility['mentions']}/{visibility['total_tests']} responses)\n")

    # ── Check 1: Crawlability ─────────────────────────────────────
    print("[ 1/3 ] Crawlability check...")
    c1 = crawlability.run(url)
    print(f"        Score: {c1['score']}/100\n")

    # ── Check 2: AI Authority ─────────────────────────────────────
    print("[ 2/3 ] AI Authority check (this takes ~60s — using web search)...")
    homepage_text = ""
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        homepage_text = soup.get_text(separator=" ", strip=True)[:3000]
    except Exception:
        pass

    c2 = ai_authority.run(business_name, category, location, homepage_text, client)
    print(f"        Score: {c2['score']}/100\n")

    # ── Check 3: Answer Readiness ─────────────────────────────────
    print("[ 3/3 ] Answer Readiness check (Claude content analysis)...")
    top_competitors = visibility.get("top_competitors", [])
    c3 = answer_readiness.run(url, business_name, category, location, top_competitors, client)
    print(f"        Score: {c3['score']}/100\n")

    # ── Compute final score ───────────────────────────────────────
    geo_score = compute_geo_score(c1, c2, c3)
    print(f"{'='*60}")
    print(f"GEO Score: {geo_score['score']}/100 ({geo_score['band']})")
    print(f"{geo_score['description']}")
    print(f"{'='*60}\n")

    return {
        "url": url,
        "business_name": business_name,
        "category": category,
        "location": location,
        "timestamp": datetime.now().isoformat(),
        "visibility": visibility,
        "crawlability": c1,
        "ai_authority": c2,
        "answer_readiness": c3,
        "geo_score": geo_score,
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: python main.py <url> <business_name> <category> [location]")
        print("")
        print("Examples:")
        print('  python main.py https://qpiai.tech "QPiAI" "quantum computing" "India"')
        print('  python main.py https://notion.so "Notion" "productivity software"')
        sys.exit(1)

    url = sys.argv[1]
    business_name = sys.argv[2]
    category = sys.argv[3]
    location = sys.argv[4] if len(sys.argv) > 4 else ""

    # Run audit
    results = run_audit(url, business_name, category, location)

    # Generate report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = business_name.lower().replace(" ", "_")
    report_filename = f"report_{safe_name}_{timestamp}.html"
    report_path = os.path.join(os.path.dirname(__file__), report_filename)

    print("Generating report...")
    generator.generate(results, report_path)
    print(f"Report saved: {report_filename}")

    # Also save raw JSON for debugging
    json_path = report_path.replace(".html", ".json")
    with open(json_path, "w") as f:
        # Remove non-serialisable objects before saving
        save_results = {k: v for k, v in results.items() if k != "soup"}
        json.dump(save_results, f, indent=2, default=str)
    print(f"Raw data saved: {os.path.basename(json_path)}")

    return results


if __name__ == "__main__":
    main()