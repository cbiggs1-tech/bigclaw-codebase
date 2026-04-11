#!/usr/bin/env python3
"""Multi-model truth assessment engine for BigClaw.

Takes a claim, article text, or URL and runs it through:
  - Claude Sonnet (Anthropic)
  - Grok (xAI)
  - Gemini Flash (Google)
  - DeepSeek R1 (DeepSeek)
All four models use the same neutral SIFT-based investigative framework.
Plus Brave Search for source verification and diversity scoring.

Usage:
    source ~/.env_secrets
    python3 truth_engine.py "The Fed raised rates by 50bps today"
    python3 truth_engine.py --url https://example.com/article
    python3 truth_engine.py --file /path/to/article.txt
    python3 truth_engine.py --claim "NVDA beat earnings by 20%" --json
"""

import argparse
import json
import os
import sys
import requests
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

# ── Source Lean Database (AllSides / Ad Fontes based) ──────────────────────
SOURCE_LEAN = {
    # Right
    "foxnews.com": "right", "breitbart.com": "right", "dailywire.com": "right",
    "newsmax.com": "right", "oann.com": "right", "thefederalist.com": "right",
    "townhall.com": "right", "nationalreview.com": "right",
    "freebeacon.com": "right", "dailycaller.com": "right",
    # Right-center
    "nypost.com": "right-center", "wsj.com": "right-center",
    "washingtontimes.com": "right-center", "economist.com": "right-center",
    "forbes.com": "right-center", "reason.com": "right-center",
    # Center
    "reuters.com": "center", "apnews.com": "center", "bbc.com": "center",
    "bbc.co.uk": "center", "thehill.com": "center", "axios.com": "center",
    "usatoday.com": "center", "abcnews.go.com": "center",
    "cbsnews.com": "center", "pbs.org": "center", "csmonitor.com": "center",
    # Left-center
    "npr.org": "left-center", "washingtonpost.com": "left-center",
    "nytimes.com": "left-center", "politico.com": "left-center",
    "nbcnews.com": "left-center", "bloomberg.com": "left-center",
    "time.com": "left-center", "theatlantic.com": "left-center",
    # Left
    "cnn.com": "left", "msnbc.com": "left", "huffpost.com": "left",
    "vox.com": "left", "slate.com": "left", "motherjones.com": "left",
    "thedailybeast.com": "left", "salon.com": "left",
    # International
    "theguardian.com": "left-center", "telegraph.co.uk": "right-center",
    "independent.co.uk": "left-center", "aljazeera.com": "left-center",
    "scmp.com": "center", "dw.com": "center",
    # Regional / misc
    "sfchronicle.com": "left-center", "sfgate.com": "left-center",
    "chicagotribune.com": "right-center", "latimes.com": "left-center",
    "dallasnews.com": "center", "denverpost.com": "left-center",
    "seattletimes.com": "left-center", "bostonglobe.com": "left-center",
    "nydn.com": "left-center", "nydailynews.com": "left-center",
    # Business / finance
    "cnbc.com": "center", "ft.com": "center",
    "barrons.com": "right-center", "marketwatch.com": "center",
    "businessinsider.com": "left-center", "fortune.com": "left-center",
    # Tech / culture
    "arstechnica.com": "left-center", "theverge.com": "left-center",
    "wired.com": "left-center", "techcrunch.com": "left-center",
    # Fact-check / specialized
    "snopes.com": "fact-check", "politifact.com": "fact-check",
    "factcheck.org": "fact-check", "fullfact.org": "fact-check",
    "factually.co": "fact-check",
}

# ── SIFT System Prompt (shared by all models) ─────────────────────────────
TRUTH_SEEKER_SYSTEM = (
    "You are a truth seeker. Your only goal is to determine whether "
    "a claim is true, false, or somewhere in between. Do not play a role. "
    "Do not adopt a persona. Do not lean in any predetermined direction. "
    "Evaluate the evidence on its merits using the structured investigative "
    "framework provided. Be direct, specific, and honest. Follow the "
    "evidence wherever it leads."
)

# ── Model Configuration ────────────────────────────────────────────────────
MODELS = {
    "claude": {
        "id": "anthropic/claude-sonnet-4-6",
        "system": TRUTH_SEEKER_SYSTEM,
    },
    "grok": {
        "id": "x-ai/grok-4.1-fast",
        "system": TRUTH_SEEKER_SYSTEM,
    },
    "gemini": {
        "id": "google/gemini-2.5-flash",
        "system": TRUTH_SEEKER_SYSTEM,
    },
    "deepseek": {
        "id": "deepseek/deepseek-r1-0528",
        "system": TRUTH_SEEKER_SYSTEM,
    },
}

ANALYSIS_PROMPT = """Investigate this claim using the structured framework below. Return ONLY valid JSON.

CLAIM: {claim}

SOURCE CONTEXT:
{context}

WEB SOURCES FOUND:
Corroborating: {corroborating_count} sources
Contradicting: {contradicting_count} sources
Fact-checks: {factcheck_count} found

Source details:
{source_details}

── INVESTIGATIVE FRAMEWORK ──
Work through each step before rendering your verdict:

1. SOURCE CHECK: Who is making this claim? What are their credentials, funding, and known biases? Is the source rated by bias-tracking organizations?

2. PRIMARY SOURCE VERIFICATION: Do the cited sources actually support the claim? Are quotes in context? Is data being accurately represented?

3. COVERAGE DIVERSITY: How do sources across the political spectrum cover this? Where do they agree on facts? Where do they diverge on interpretation?

4. FACT-CHECK & TRACE: Have fact-check organizations addressed this? Are there archived versions showing edits? Has the claim evolved over time?

5. PATTERN ANALYSIS: Does the source have a track record of accuracy? Have similar claims been made before and how did they hold up?

6. BIAS & MOTIVATION: Who benefits from this claim being believed? Is emotional language being used? Are there logical fallacies in the argument?

── RESPONSE FORMAT ──
Respond with this exact JSON structure (no markdown, no explanation outside JSON):
{{
    "verdict": "TRUE" or "LIKELY_TRUE" or "UNVERIFIED" or "MISLEADING" or "LIKELY_FALSE" or "FALSE",
    "confidence": <number 0-100>,
    "source_check": "<1-2 sentences: who is behind this claim, credibility assessment>",
    "primary_verification": "<1-2 sentences: do cited sources actually support the claim>",
    "coverage_analysis": "<1-2 sentences: how coverage splits across the spectrum>",
    "fact_check_findings": "<1-2 sentences: what fact-checkers and verification found>",
    "pattern_analysis": "<1-2 sentences: source track record, similar past claims>",
    "bias_probe": "<1-2 sentences: who benefits, emotional language, fallacies>",
    "reasoning": "<2-3 sentence overall assessment synthesizing the above>",
    "flags": ["<list of any red flags or concerns, empty if none>"]
}}"""


def fetch_url_content(url, timeout=20):
    """Fetch and extract readable text from a URL."""
    try:
        headers = {"User-Agent": "BigClawBot/1.0 (truth-engine)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove script/style
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            title = soup.find("title")
            title_text = title.get_text().strip() if title else ""
            # Get article body
            article = soup.find("article") or soup.find("main") or soup.find("body")
            body_text = article.get_text(separator="\n", strip=True) if article else ""
            # Truncate to ~3000 chars for model context
            body_text = body_text[:3000]
            return {
                "title": title_text,
                "text": body_text,
                "url": url,
                "domain": urlparse(url).netloc.replace("www.", ""),
            }
        except ImportError:
            return {"text": resp.text[:3000], "url": url, "domain": urlparse(url).netloc}
    except Exception as e:
        return {"error": str(e), "url": url}


def brave_search(query, api_key, freshness="pm", count=8):
    """Search Brave Web API and return results with lean categorization."""
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": count, "freshness": freshness}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "results": []}
        data = resp.json()
        results = []
        for r in data.get("web", {}).get("results", []):
            domain = urlparse(r.get("url", "")).netloc.replace("www.", "")
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "domain": domain,
                "lean": SOURCE_LEAN.get(domain, "unknown"),
            })
        return {"count": len(results), "results": results}
    except Exception as e:
        return {"error": str(e), "results": []}


def gather_sources(claim, api_key):
    """Run 3 Brave searches: corroboration, debunking, fact-check."""
    short_claim = claim[:80]

    print("  Searching for corroboration...", file=sys.stderr)
    corroborating = brave_search(f'"{short_claim}"', api_key, freshness="pw")

    print("  Searching for debunking...", file=sys.stderr)
    contradicting = brave_search(
        f"{short_claim} false debunked misleading incorrect", api_key, freshness="pm"
    )

    print("  Searching fact-check sites...", file=sys.stderr)
    fact_checks = brave_search(f"{short_claim} fact check", api_key, freshness="pm")

    # Calculate source diversity
    all_results = (
        corroborating.get("results", [])
        + contradicting.get("results", [])
        + fact_checks.get("results", [])
    )
    diversity = {"left": 0, "left-center": 0, "center": 0, "right-center": 0,
                 "right": 0, "fact-check": 0, "unknown": 0}
    for r in all_results:
        lean = r.get("lean", "unknown")
        diversity[lean] = diversity.get(lean, 0) + 1

    return {
        "corroborating": corroborating,
        "contradicting": contradicting,
        "fact_checks": fact_checks,
        "diversity": diversity,
        "total_sources": len(all_results),
    }


def call_model(model_name, claim, context, sources, api_key):
    """Call a single model via OpenRouter API for truth assessment."""
    model_cfg = MODELS[model_name]

    # Build source details string
    source_lines = []
    for category in ["corroborating", "contradicting", "fact_checks"]:
        results = sources.get(category, {}).get("results", [])
        for r in results[:5]:
            lean_tag = f" [{r.get('lean', 'unknown')}]" if r.get("lean") != "unknown" else ""
            source_lines.append(f"- {r['title']}{lean_tag}: {r.get('description', '')[:120]}")

    prompt = ANALYSIS_PROMPT.format(
        claim=claim,
        context=context[:2000] if context else "No additional context provided.",
        corroborating_count=sources.get("corroborating", {}).get("count", 0),
        contradicting_count=sources.get("contradicting", {}).get("count", 0),
        factcheck_count=sources.get("fact_checks", {}).get("count", 0),
        source_details="\n".join(source_lines) if source_lines else "No sources found.",
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bigclaw.grandpapa.net",
        "X-Title": "BigClaw Truth Engine",
    }
    payload = {
        "model": model_cfg["id"],
        "messages": [
            {"role": "system", "content": model_cfg["system"]},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.3,
    }

    try:
        print(f"  Querying {model_name} ({model_cfg['id']})...", file=sys.stderr)
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers, json=payload, timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # Parse JSON from response (handle markdown code blocks)
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        # DeepSeek R1 wraps reasoning in <think>...</think> tags — extract the JSON after
        if "<think>" in content:
            think_end = content.rfind("</think>")
            if think_end != -1:
                content = content[think_end + len("</think>"):].strip()

        result = json.loads(content)
        result["model"] = model_name
        return result
    except json.JSONDecodeError:
        return {
            "model": model_name,
            "verdict": "ERROR", "confidence": 0,
            "reasoning": f"Failed to parse model response: {content[:200]}",
            "flags": ["Model returned non-JSON response"],
        }
    except Exception as e:
        return {
            "model": model_name,
            "verdict": "ERROR", "confidence": 0,
            "reasoning": f"API call failed: {str(e)}",
            "flags": ["Model API error"],
        }


def compute_consensus(model_results):
    """Compute consensus verdict from model assessments (supports any count)."""
    verdicts = {}
    confidences = []
    working_models = []

    for r in model_results.values():
        v = r.get("verdict", "ERROR")
        if v == "ERROR":
            continue
        working_models.append(r["model"])
        verdicts[v] = verdicts.get(v, 0) + 1
        confidences.append(r.get("confidence", 50))

    if not working_models:
        return {
            "label": "ERROR",
            "confidence": 0,
            "consensus": "no_data",
        }

    # Group similar verdicts for consensus calculation
    verdict_groups = {
        "true": ["TRUE", "LIKELY_TRUE"],
        "false": ["FALSE", "LIKELY_FALSE"],
        "middle": ["UNVERIFIED", "MISLEADING"],
    }

    group_counts = {"true": 0, "false": 0, "middle": 0}
    for v, count in verdicts.items():
        for group, members in verdict_groups.items():
            if v in members:
                group_counts[group] += count
                break

    total = len(working_models)

    # Find the dominant verdict (exact match first)
    most_common = max(verdicts.items(), key=lambda x: x[1])
    most_common_verdict = most_common[0]
    most_common_count = most_common[1]

    # Also check group-level agreement (TRUE + LIKELY_TRUE = same direction)
    dominant_group = max(group_counts.items(), key=lambda x: x[1])
    group_agreement = dominant_group[1]

    avg_confidence = sum(confidences) // len(confidences) if confidences else 0

    if most_common_count == total:
        consensus = "unanimous"
    elif group_agreement == total:
        # All models agree on direction even if exact verdicts differ
        consensus = "unanimous-direction"
    elif group_agreement >= 3:
        consensus = "strong-majority"
    elif most_common_count >= 2 or group_agreement >= 2:
        consensus = "majority"
    else:
        consensus = "split"
        most_common_verdict = "CONTESTED"
        avg_confidence = min(avg_confidence, 40)

    return {
        "label": most_common_verdict,
        "confidence": avg_confidence,
        "consensus": consensus,
        "agreement": f"{group_agreement}/{total}",
    }


def build_scorecard(consensus, model_results, sources):
    """Build a synthesis scorecard from all model results and source data."""
    working = {k: v for k, v in model_results.items() if v.get("verdict") != "ERROR"}
    total = len(working)

    if total == 0:
        return {"error": "No model results to score"}

    # ── Evidence table: classify sources as primary/secondary, corroborated/not ──
    corr_sources = sources.get("corroborating", {}).get("results", [])
    contra_sources = sources.get("contradicting", {}).get("results", [])
    fc_sources = sources.get("fact_checks", {}).get("results", [])

    # Primary = fact-check orgs + wire services (reuters, ap); secondary = everything else
    primary_domains = {"reuters.com", "apnews.com", "snopes.com", "politifact.com",
                       "factcheck.org", "fullfact.org", "bbc.com", "bbc.co.uk"}
    all_sources = corr_sources + contra_sources + fc_sources
    primary = [s for s in all_sources if s.get("domain") in primary_domains]
    secondary = [s for s in all_sources if s.get("domain") not in primary_domains]

    evidence_table = {
        "primary_sources": len(primary),
        "secondary_sources": len(secondary),
        "corroborating": len(corr_sources),
        "contradicting": len(contra_sources),
        "fact_checks": len(fc_sources),
        "total": len(all_sources),
    }

    # ── Confidence breakdown by SIFT layer ──
    # For each layer, check how many models flagged concerns vs. found support
    sift_fields = [
        "source_check", "primary_verification", "coverage_analysis",
        "fact_check_findings", "pattern_analysis", "bias_probe",
    ]

    # Aggregate confidence: use model confidence spread as a signal
    confidences = sorted([v.get("confidence", 50) for v in working.values()])
    conf_spread = confidences[-1] - confidences[0]
    avg_confidence = sum(confidences) // len(confidences)
    # Median is more resilient to one outlier than average
    mid = len(confidences) // 2
    if len(confidences) % 2 == 0:
        median_confidence = (confidences[mid - 1] + confidences[mid]) // 2
    else:
        median_confidence = confidences[mid]

    # Confidence level based on median (resistant to single outlier)
    # Spread is a secondary signal — flags disagreement but doesn't override strong consensus
    if median_confidence >= 75:
        confidence_level = "HIGH"
        if conf_spread > 40:
            confidence_level = "MEDIUM"  # one major outlier, downgrade to medium
    elif median_confidence >= 50:
        confidence_level = "MEDIUM"
    else:
        confidence_level = "LOW"

    # ── Uncertainties: where models disagree on SIFT layers ──
    uncertainties = []
    for field in sift_fields:
        findings = [v.get(field, "") for v in working.values() if v.get(field)]
        if not findings:
            continue
        # Simple heuristic: if any model's finding contains negating language
        # while another doesn't, flag it as an uncertainty
        neg_words = {"no ", "not ", "none ", "lacks ", "missing ", "unclear ",
                     "unverified", "cannot ", "insufficient"}
        has_negative = any(any(nw in f.lower() for nw in neg_words) for f in findings)
        has_positive = any(not any(nw in f.lower() for nw in neg_words) for f in findings)
        if has_negative and has_positive:
            label = field.replace("_", " ").title()
            uncertainties.append(f"Models disagree on {label}")

    if conf_spread > 25:
        uncertainties.append(
            f"Wide confidence spread ({min(confidences)}%-{max(confidences)}%) "
            f"suggests genuine ambiguity"
        )

    # Check for source-side uncertainties
    if evidence_table["primary_sources"] == 0:
        uncertainties.append("No primary/wire sources found — claim relies on secondary reporting")
    if evidence_table["fact_checks"] == 0:
        uncertainties.append("No fact-check coverage yet — claim may be too new or niche")
    if evidence_table["contradicting"] == 0 and evidence_table["corroborating"] > 0:
        uncertainties.append("No contradicting sources found — could indicate consensus or echo chamber")

    # ── Recommendations ──
    recommendations = []
    verdict = consensus.get("label", "")

    if confidence_level == "LOW":
        recommendations.append("Treat with skepticism — evidence is insufficient or contradictory")
    if verdict == "CONTESTED":
        recommendations.append("Wait for more evidence before drawing conclusions")
    if evidence_table["fact_checks"] == 0 and verdict in ("LIKELY_TRUE", "LIKELY_FALSE", "UNVERIFIED"):
        recommendations.append("Monitor for upcoming fact-check coverage")
    if evidence_table["primary_sources"] == 0:
        recommendations.append("Seek primary source confirmation before acting on this claim")

    diversity = sources.get("diversity", {})
    left_t = diversity.get("left", 0) + diversity.get("left-center", 0)
    right_t = diversity.get("right", 0) + diversity.get("right-center", 0)
    if (left_t > 0 and right_t == 0) or (right_t > 0 and left_t == 0):
        recommendations.append("Seek coverage from the other side of the spectrum for balance")

    if verdict in ("TRUE", "LIKELY_TRUE") and confidence_level == "HIGH":
        recommendations.append("Claim is well-supported — safe to reference with attribution")
    elif verdict in ("FALSE", "LIKELY_FALSE") and confidence_level == "HIGH":
        recommendations.append("Claim is well-debunked — do not amplify without correction")
    elif verdict == "MISLEADING":
        recommendations.append("Core facts may be true but framing is distorted — verify specifics")

    if not recommendations:
        recommendations.append("Exercise standard caution — verify before sharing")

    return {
        "confidence_level": confidence_level,
        "confidence_avg": avg_confidence,
        "confidence_median": median_confidence,
        "confidence_spread": conf_spread,
        "confidence_range": f"{confidences[0]}%-{confidences[-1]}%",
        "evidence_table": evidence_table,
        "uncertainties": uncertainties,
        "recommendations": recommendations,
    }


def build_assessment(claim, input_type, source_url, context, sources, model_results):
    """Build the final structured truth assessment."""
    consensus = compute_consensus(model_results)

    # Collect all bias flags
    all_flags = []
    for r in model_results.values():
        all_flags.extend(r.get("flags", []))

    # Check source diversity flags
    diversity = sources.get("diversity", {})
    left_total = diversity.get("left", 0) + diversity.get("left-center", 0)
    right_total = diversity.get("right", 0) + diversity.get("right-center", 0)
    center_total = diversity.get("center", 0)

    if sources.get("total_sources", 0) == 0:
        all_flags.append("No web sources found for this claim")
    elif center_total == 0 and (left_total > 0 or right_total > 0):
        all_flags.append("No centrist sources found — coverage may be partisan")
    if left_total > 0 and right_total == 0:
        all_flags.append("Only left-leaning sources cover this claim")
    elif right_total > 0 and left_total == 0:
        all_flags.append("Only right-leaning sources cover this claim")

    # Deduplicate flags
    all_flags = list(dict.fromkeys(all_flags))

    # Build summary
    total_models = len([r for r in model_results.values() if r.get("verdict") != "ERROR"])
    verdicts_str = ", ".join(
        f"{name}: {r.get('verdict', 'ERROR')}" for name, r in model_results.items()
    )
    agreement = consensus.get("agreement", "")
    if consensus["consensus"] == "unanimous":
        summary = (
            f"All {total_models} models agree: {consensus['label']}. "
            f"Confidence: {consensus['confidence']}%. "
            f"{sources.get('total_sources', 0)} web sources analyzed."
        )
    elif consensus["consensus"] == "unanimous-direction":
        summary = (
            f"All {total_models} models agree on direction ({agreement}). "
            f"Verdict: {consensus['label']}. "
            f"Confidence: {consensus['confidence']}%."
        )
    elif consensus["consensus"] == "strong-majority":
        dissenter = [
            name for name, r in model_results.items()
            if r.get("verdict") != consensus["label"] and r.get("verdict") != "ERROR"
        ]
        summary = (
            f"Strong majority ({agreement}): {consensus['label']}. "
            f"{', '.join(dissenter)} dissented. "
            f"Confidence: {consensus['confidence']}%."
        )
    elif consensus["consensus"] == "majority":
        dissenter = [
            name for name, r in model_results.items()
            if r.get("verdict") != consensus["label"] and r.get("verdict") != "ERROR"
        ]
        summary = (
            f"Majority verdict ({agreement}): {consensus['label']}. "
            f"{', '.join(dissenter)} dissented. "
            f"Confidence: {consensus['confidence']}%."
        )
    else:
        summary = (
            f"Models disagree — verdict is CONTESTED. "
            f"{verdicts_str}. "
            f"Low confidence ({consensus['confidence']}%). More evidence needed."
        )

    # Build scorecard synthesis layer
    scorecard = build_scorecard(consensus, model_results, sources)

    return {
        "claim": claim,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_type": input_type,
        "source_url": source_url,
        "verdict": consensus,
        "scorecard": scorecard,
        "models": {
            name: {
                "verdict": r.get("verdict", "ERROR"),
                "confidence": r.get("confidence", 0),
                "source_check": r.get("source_check", ""),
                "primary_verification": r.get("primary_verification", ""),
                "coverage_analysis": r.get("coverage_analysis", ""),
                "fact_check_findings": r.get("fact_check_findings", ""),
                "pattern_analysis": r.get("pattern_analysis", ""),
                "bias_probe": r.get("bias_probe", ""),
                "reasoning": r.get("reasoning", ""),
                "flags": r.get("flags", []),
            }
            for name, r in model_results.items()
        },
        "sources": {
            "corroborating": [
                {"title": r["title"], "url": r["url"], "domain": r["domain"], "lean": r["lean"]}
                for r in sources.get("corroborating", {}).get("results", [])[:5]
            ],
            "contradicting": [
                {"title": r["title"], "url": r["url"], "domain": r["domain"], "lean": r["lean"]}
                for r in sources.get("contradicting", {}).get("results", [])[:5]
            ],
            "fact_checks": [
                {"title": r["title"], "url": r["url"], "domain": r["domain"], "lean": r["lean"]}
                for r in sources.get("fact_checks", {}).get("results", [])[:5]
            ],
            "diversity": diversity,
            "total_sources": sources.get("total_sources", 0),
        },
        "bias_flags": all_flags,
        "summary": summary,
    }


def format_markdown(assessment):
    """Format assessment as readable markdown."""
    v = assessment["verdict"]
    label_emoji = {
        "TRUE": "✅", "LIKELY_TRUE": "✅", "UNVERIFIED": "❓",
        "MISLEADING": "⚠️", "LIKELY_FALSE": "❌", "FALSE": "❌",
        "CONTESTED": "⚔️", "ERROR": "🔴",
    }
    emoji = label_emoji.get(v["label"], "❓")
    agreement = v.get("agreement", "")

    lines = []
    lines.append(f"🔍 **TRUTH ASSESSMENT**: {emoji} {v['label']}")
    lines.append(f"**Confidence**: {v['confidence']}% | **Consensus**: {v['consensus']} ({agreement}) | **Sources**: {assessment['sources']['total_sources']} found")
    lines.append("")
    lines.append(f"**Claim**: {assessment['claim']}")
    lines.append("")

    # Model verdicts — compact summary
    lines.append("**Model Verdicts**:")
    for name, m in assessment["models"].items():
        m_emoji = label_emoji.get(m["verdict"], "❓")
        lines.append(f"- **{name.capitalize()}**: {m_emoji} {m['verdict']} ({m['confidence']}%)")
    lines.append("")

    # SIFT Investigation layers — show where models agree/disagree
    sift_layers = [
        ("source_check", "Source Check"),
        ("primary_verification", "Primary Verification"),
        ("coverage_analysis", "Coverage Analysis"),
        ("fact_check_findings", "Fact-Check Findings"),
        ("pattern_analysis", "Pattern Analysis"),
        ("bias_probe", "Bias & Motivation"),
    ]

    lines.append("**Investigation Detail**:")
    for field, label in sift_layers:
        findings = {name: m.get(field, "") for name, m in assessment["models"].items() if m.get(field)}
        if findings:
            lines.append(f"\n*{label}*:")
            for name, finding in findings.items():
                lines.append(f"  {name}: {finding}")

    # Model reasoning
    lines.append("")
    lines.append("**Model Reasoning**:")
    for name, m in assessment["models"].items():
        if m.get("reasoning"):
            lines.append(f"- **{name.capitalize()}**: {m['reasoning']}")

    # ── Scorecard ──
    sc = assessment.get("scorecard", {})
    if sc and "error" not in sc:
        conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(sc.get("confidence_level"), "⚪")
        lines.append("")
        lines.append("━" * 50)
        lines.append(f"📊 **SCORECARD**")
        lines.append(f"**Confidence**: {conf_emoji} {sc.get('confidence_level')} (median {sc.get('confidence_median')}%, avg {sc.get('confidence_avg')}%, range {sc.get('confidence_range')})")
        lines.append("")

        # Evidence table
        ev = sc.get("evidence_table", {})
        lines.append("**Evidence Table**:")
        lines.append(f"  Primary sources (wire/fact-check): {ev.get('primary_sources', 0)}")
        lines.append(f"  Secondary sources: {ev.get('secondary_sources', 0)}")
        lines.append(f"  Corroborating: {ev.get('corroborating', 0)} | Contradicting: {ev.get('contradicting', 0)} | Fact-checks: {ev.get('fact_checks', 0)}")

        # Source diversity
        div = assessment["sources"]["diversity"]
        lines.append(f"  Spectrum: Left: {div.get('left', 0) + div.get('left-center', 0)} | Center: {div.get('center', 0)} | Right: {div.get('right', 0) + div.get('right-center', 0)} | Fact-check: {div.get('fact-check', 0)}")

        # Uncertainties
        if sc.get("uncertainties"):
            lines.append("")
            lines.append("**Open Questions**:")
            for u in sc["uncertainties"]:
                lines.append(f"  ? {u}")

        # Recommendations
        if sc.get("recommendations"):
            lines.append("")
            lines.append("**Recommendations**:")
            for r in sc["recommendations"]:
                lines.append(f"  → {r}")

        lines.append("━" * 50)

    # Bias flags
    if assessment["bias_flags"]:
        lines.append("")
        lines.append("**Flags**:")
        for flag in assessment["bias_flags"]:
            lines.append(f"- ⚠️ {flag}")

    # Summary
    lines.append("")
    lines.append(f"**Bottom line**: {assessment['summary']}")

    return "\n".join(lines)


def format_source_list(assessment):
    """Format a detailed source list for manual verification."""
    lines = []
    lines.append("")
    lines.append("━" * 60)
    lines.append("📋 **SOURCES CHECKED**")
    lines.append("")

    for category, label in [
        ("corroborating", "Corroborating"),
        ("contradicting", "Contradicting / Debunking"),
        ("fact_checks", "Fact-Check"),
    ]:
        sources = assessment["sources"].get(category, [])
        lines.append(f"**{label}** ({len(sources)} found):")
        if not sources:
            lines.append("  (none)")
        for s in sources:
            lean_tag = f" [{s.get('lean', 'unknown')}]" if s.get("lean") != "unknown" else ""
            lines.append(f"  • {s['title']}{lean_tag}")
            lines.append(f"    {s['url']}")
        lines.append("")

    div = assessment["sources"].get("diversity", {})
    lines.append("**Source Lean Breakdown**:")
    for lean in ["left", "left-center", "center", "right-center", "right", "fact-check", "unknown"]:
        count = div.get(lean, 0)
        if count > 0:
            lines.append(f"  {lean}: {count}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="BigClaw Truth Engine — Multi-model fact assessment")
    parser.add_argument("claim", nargs="?", help="The claim to assess (positional)")
    parser.add_argument("--claim", dest="claim_flag", help="The claim to assess (flag)")
    parser.add_argument("--url", help="URL of an article to assess")
    parser.add_argument("--file", help="Path to a text file to assess")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of markdown")
    parser.add_argument("--sources", action="store_true", help="Show full source list with URLs after assessment")
    args = parser.parse_args()

    # Determine input
    claim = args.claim or args.claim_flag
    input_type = "claim"
    source_url = None
    context = ""

    if args.url:
        input_type = "url"
        source_url = args.url
        print(f"Fetching URL: {args.url}", file=sys.stderr)
        article = fetch_url_content(args.url)
        if "error" in article:
            print(f"Error fetching URL: {article['error']}", file=sys.stderr)
            sys.exit(1)
        context = article.get("text", "")
        if not claim:
            claim = article.get("title", args.url)
    elif args.file:
        input_type = "file"
        try:
            with open(args.file, "r") as f:
                context = f.read()
            if not claim:
                claim = context[:200]
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)

    if not claim:
        parser.error("Provide a claim as a positional argument, --claim, --url, or --file")

    # Check API keys
    brave_key = os.environ.get("BRAVE_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")

    if not brave_key:
        print("Warning: BRAVE_API_KEY not set — source search disabled", file=sys.stderr)
    if not openrouter_key:
        print("Error: OPENROUTER_API_KEY required for multi-model analysis", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Assessing: {claim[:100]}{'...' if len(claim) > 100 else ''}\n", file=sys.stderr)

    # Step 1: Gather sources
    if brave_key:
        print("Step 1: Searching for sources...", file=sys.stderr)
        sources = gather_sources(claim, brave_key)
        print(f"  Found {sources['total_sources']} total sources\n", file=sys.stderr)
    else:
        sources = {
            "corroborating": {"count": 0, "results": []},
            "contradicting": {"count": 0, "results": []},
            "fact_checks": {"count": 0, "results": []},
            "diversity": {},
            "total_sources": 0,
        }

    # Step 2: Multi-model analysis
    print("Step 2: Running multi-model analysis...", file=sys.stderr)
    model_results = {}
    for model_name in MODELS:
        result = call_model(model_name, claim, context, sources, openrouter_key)
        model_results[model_name] = result
        v = result.get("verdict", "ERROR")
        c = result.get("confidence", 0)
        print(f"  {model_name}: {v} ({c}%)", file=sys.stderr)

    # Step 3: Build assessment
    print("\nStep 3: Computing consensus...", file=sys.stderr)
    assessment = build_assessment(claim, input_type, source_url, context, sources, model_results)

    # Output
    if args.json:
        print(json.dumps(assessment, indent=2))
    else:
        output = format_markdown(assessment)
        if args.sources:
            output += format_source_list(assessment)
        print(output)


if __name__ == "__main__":
    main()
