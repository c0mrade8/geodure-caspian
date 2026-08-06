"""
Check 1: Crawlability (20% of total score)
Can AI bots actually find and read this website?
This is the gateway check — failing here means nothing else matters.
"""

import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup


AI_BOTS = {
    "GPTBot":        {"points": 30, "platform": "ChatGPT"},
    "GeminiBot":     {"points": 20, "platform": "Gemini"},
    "PerplexityBot": {"points": 20, "platform": "Perplexity"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GEOAuditor/1.0)"
}

TIMEOUT = 10


def check_robots_txt(base_url: str) -> dict:
    """
    Fetch robots.txt and check if AI bots are blocked.
    Returns per-bot status and points earned.
    """
    robots_url = base_url.rstrip("/") + "/robots.txt"
    result = {
        "url": robots_url,
        "found": False,
        "raw": "",
        "bots": {},
        "points": 0,
        "fixes": [],
    }

    try:
        resp = requests.get(robots_url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            result["found"] = True
            result["raw"] = resp.text
        else:
            # No robots.txt — all bots allowed by default, full points
            for bot, meta in AI_BOTS.items():
                result["bots"][bot] = {"blocked": False, "points": meta["points"], "platform": meta["platform"]}
                result["points"] += meta["points"]
            result["fixes"].append({
                "issue": "No robots.txt found",
                "severity": "low",
                "detail": "No robots.txt is fine — all bots are allowed by default. Consider adding one for control.",
                "fix": None
            })
            return result
    except Exception as e:
        result["error"] = str(e)
        return result

    content = result["raw"].lower()
    lines = content.splitlines()

    # Parse robots.txt — simplified but sufficient for our checks
    current_agents = []
    disallowed_paths = {}

    for line in lines:
        line = line.strip()
        if line.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current_agents = [agent]
            if agent not in disallowed_paths:
                disallowed_paths[agent] = []
        elif line.startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            for agent in current_agents:
                disallowed_paths[agent].append(path)

    for bot, meta in AI_BOTS.items():
        bot_lower = bot.lower()
        blocked = False

        # Check if this bot or * has a Disallow: /
        for agent_key, paths in disallowed_paths.items():
            if agent_key == bot_lower or agent_key == "*":
                if "/" in paths or "" in paths:
                    blocked = True
                    break

        pts = 0 if blocked else meta["points"]
        result["bots"][bot] = {
            "blocked": blocked,
            "points": pts,
            "platform": meta["platform"],
        }
        result["points"] += pts

        if blocked:
            result["fixes"].append({
                "issue": f"{bot} is blocked in robots.txt",
                "severity": "high",
                "detail": f"This blocks {meta['platform']} from crawling your site — making you invisible to it.",
                "fix": f"User-agent: {bot}\nAllow: /"
            })

    return result


def check_sitemap(base_url: str) -> dict:
    """Check if sitemap.xml exists and is valid."""
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
    result = {
        "url": sitemap_url,
        "found": False,
        "url_count": 0,
        "points": 0,
        "fix": None,
    }

    try:
        resp = requests.get(sitemap_url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200 and "<url" in resp.text.lower():
            result["found"] = True
            soup = BeautifulSoup(resp.text, "lxml-xml")
            result["url_count"] = len(soup.find_all("url"))
            result["points"] = 15
        else:
            result["fix"] = (
                "Create a sitemap.xml file at your website root.\n"
                "Most CMS platforms (WordPress, Webflow, Squarespace) generate this automatically.\n"
                "For a custom site, use: https://www.xml-sitemaps.com/"
            )
    except Exception as e:
        result["error"] = str(e)
        result["fix"] = "Could not check sitemap. Ensure /sitemap.xml is accessible."

    return result


def check_llms_txt(base_url: str) -> dict:
    """
    Check if llms.txt exists — an emerging standard for AI context.
    Not yet widely adopted; presence is a strong positive signal.
    """
    llms_url = base_url.rstrip("/") + "/llms.txt"
    result = {
        "url": llms_url,
        "found": False,
        "content_preview": "",
        "points": 0,
        "fix": None,
    }

    try:
        resp = requests.get(llms_url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200 and len(resp.text.strip()) > 20:
            result["found"] = True
            result["content_preview"] = resp.text[:300]
            result["points"] = 15
        else:
            result["fix"] = None  # Generated by report from entity info
    except Exception as e:
        result["error"] = str(e)

    return result


def run(url: str) -> dict:
    """
    Run all crawlability checks. Returns structured results with score.
    Max score: 100
    """
    # Normalise URL
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    robots = check_robots_txt(base_url)
    sitemap = check_sitemap(base_url)
    llms = check_llms_txt(base_url)

    total_points = robots["points"] + sitemap["points"] + llms["points"]

    # Collect all copy-pasteable fixes
    fixes = []
    blocked_bots = [b for b, d in robots.get("bots", {}).items() if d.get("blocked")]
    if blocked_bots:
        fix_block = "\n".join([f"User-agent: {b}\nAllow: /" for b in blocked_bots])
        fixes.append({
            "priority": 1,
            "effort": "5 minutes",
            "title": "Unblock AI crawlers in robots.txt",
            "detail": f"These AI bots are currently blocked: {', '.join(blocked_bots)}",
            "copy_paste": f"# Add these lines to your robots.txt file:\n{fix_block}"
        })

    if not sitemap["found"]:
        fixes.append({
            "priority": 2,
            "effort": "30 minutes",
            "title": "Add a sitemap.xml",
            "detail": "AI crawlers use sitemaps to discover all your pages, not just the homepage.",
            "copy_paste": sitemap.get("fix", "")
        })

    if not llms["found"]:
        fixes.append({
            "priority": 3,
            "effort": "15 minutes",
            "title": "Create an llms.txt file",
            "detail": (
                "llms.txt is an emerging standard (like robots.txt, but for AI). "
                "It tells AI systems what your business is and which pages matter most. "
                "Very few businesses have this yet — it's a quick win."
            ),
            "copy_paste": None  # Generated in report using entity info
        })

    return {
        "check": "Crawlability",
        "score": total_points,
        "max": 100,
        "base_url": base_url,
        "details": {
            "robots": robots,
            "sitemap": sitemap,
            "llms_txt": llms,
        },
        "fixes": fixes,
    }