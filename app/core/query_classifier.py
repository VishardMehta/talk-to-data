"""
Rule-based query pre-classifier.

Runs BEFORE the LLM router — zero latency, zero cost.

Why this exists:
  The semantic cache at threshold 0.90 was returning the same cached answer
  for all analytically-different queries. This classifier gives each query
  a canonical type so the cache can apply type-gated thresholds and prevent
  cross-type collisions (COUNT query hitting a COMPARISON cache entry).

Query types and their cache thresholds:
  COUNT_DISTINCT  — "how many distinct regions" → 0.99 (extremely precise)
  COUNT           — "how many orders"           → 0.98
  RANKING         — "top 5 / highest"           → 0.97
  AGGREGATION     — "total revenue / sum"        → 0.97
  TREND           — "monthly trend"              → 0.96
  COMPARISON      — "north vs south"            → 0.96
  LIST            — "list all regions"           → 0.97
  INSIGHT         — "why did X happen"           → 0.95 (narrative similarity is OK)
"""
from __future__ import annotations
import re


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

_COUNT_DISTINCT = re.compile(
    r"\b(how\s+many\s+(distinct|unique|different)|count\s+(distinct|unique|different)|"
    r"number\s+of\s+(distinct|unique|different)|distinct\s+(count|number|values))\b",
    re.IGNORECASE,
)

_COUNT = re.compile(
    r"\b(how\s+many|count\s+of|total\s+number\s+of|number\s+of|count|"
    r"how\s+much\s+(is|are)\s+there)\b",
    re.IGNORECASE,
)

_MAX_MIN = re.compile(
    r"\b(highest|lowest|most|least|maximum|minimum|max|min|"
    r"best|worst|largest|smallest|biggest|fewest|greatest|"
    r"which\s+\w+\s+has\s+the\s+(most|least|highest|lowest))\b",
    re.IGNORECASE,
)

_RANKING = re.compile(
    r"\b(top\s+\d+|bottom\s+\d+|rank|ranking|ranked|first|second|third|"
    r"\d+\s+(most|least)|leading|trailing)\b",
    re.IGNORECASE,
)

_TREND = re.compile(
    r"\b(trend|over\s+time|monthly|weekly|daily|by\s+month|by\s+week|by\s+day|"
    r"history|over\s+the\s+(last|past)|time\s+series|growth\s+over|progress\s+over)\b",
    re.IGNORECASE,
)

_COMPARISON = re.compile(
    r"\b(compare|vs\.?|versus|against|difference\s+between|between\s+\w+\s+and|"
    r"relative\s+to|which\s+is\s+(better|higher|lower|more|less|greater)|"
    r"north\s+vs|south\s+vs|east\s+vs|west\s+vs)\b",
    re.IGNORECASE,
)

_SUM = re.compile(
    r"\b(total|sum\s+of|aggregate|overall|combined|gross|net\s+total|"
    r"cumulative|revenue|total\s+revenue|total\s+sales|total\s+orders|"
    r"total\s+number|total\s+loans|total\s+amount)\b",
    re.IGNORECASE,
)

_AVG = re.compile(
    r"\b(average|avg\b|mean\b|typical|median|per\s+order|per\s+customer|"
    r"on\s+average)\b",
    re.IGNORECASE,
)

_LIST = re.compile(
    r"\b(list\s+(all|the)|show\s+(all|me\s+all)|give\s+me\s+(all|a\s+list)|"
    r"what\s+are\s+(all|the)|display\s+all|enumerate)\b",
    re.IGNORECASE,
)

_INSIGHT = re.compile(
    r"\b(why|what\s+caused|explain|reason|analysis|insight|impact|"
    r"factor|root\s+cause|diagnose|investigate)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_query(question: str) -> dict:
    """
    Classify a user query into an analytical type.

    Returns:
      query_type       — canonical type string
      cache_threshold  — minimum cosine similarity for a cache hit
      aggregation_fn   — expected SQL aggregation (hint for SQL generator)
      needs_distinct   — whether DISTINCT is likely needed
      is_factual       — True for COUNT/RANKING/AGGREGATION (use direct answer style)
      hints            — list of strings injected into SQL generator prompt
    """
    q = question.strip()

    query_type = "INSIGHT"
    cache_threshold = 0.95
    aggregation_fn = None
    needs_distinct = False
    is_factual = False

    # Priority order matters — check most specific patterns first
    if _COUNT_DISTINCT.search(q):
        query_type = "COUNT_DISTINCT"
        cache_threshold = 0.99
        aggregation_fn = "COUNT(DISTINCT col)"
        needs_distinct = True
        is_factual = True

    elif _MAX_MIN.search(q) and (_COUNT.search(q) or _SUM.search(q)):
        query_type = "AGGREGATION"
        cache_threshold = 0.97
        aggregation_fn = "MAX/MIN with aggregation (e.g. ORDER BY SUM(...) DESC LIMIT 1)"
        is_factual = True

    elif _MAX_MIN.search(q):
        query_type = "RANKING"
        cache_threshold = 0.97
        aggregation_fn = "ORDER BY metric DESC LIMIT 1 (or LIMIT N)"
        is_factual = True

    elif _RANKING.search(q):
        query_type = "RANKING"
        cache_threshold = 0.97
        aggregation_fn = "ORDER BY metric DESC LIMIT N"
        is_factual = True

    elif _COUNT.search(q):
        query_type = "COUNT"
        cache_threshold = 0.98
        aggregation_fn = "COUNT(*) or COUNT(col)"
        is_factual = True

    elif _COMPARISON.search(q):
        query_type = "COMPARISON"
        cache_threshold = 0.96
        aggregation_fn = "GROUP BY dimension for side-by-side comparison"
        is_factual = False

    elif _TREND.search(q):
        query_type = "TREND"
        cache_threshold = 0.96
        aggregation_fn = "GROUP BY strftime('%Y-%m', date_col)"
        is_factual = False

    elif _SUM.search(q) or _AVG.search(q):
        query_type = "AGGREGATION"
        cache_threshold = 0.97
        aggregation_fn = "SUM(...) or AVG(...)"
        is_factual = True

    elif _LIST.search(q):
        query_type = "LIST"
        cache_threshold = 0.97
        is_factual = True

    elif _INSIGHT.search(q):
        query_type = "INSIGHT"
        cache_threshold = 0.95
        is_factual = False

    # Build SQL generator hints
    hints: list[str] = []

    if query_type == "COUNT_DISTINCT":
        hints.append(
            "QUERY TYPE: COUNT_DISTINCT — user wants the count of unique/distinct values. "
            "Use SELECT COUNT(DISTINCT col) AS total FROM table."
        )
        hints.append(
            "Do NOT return individual rows. Return a single COUNT(DISTINCT) value."
        )

    elif query_type == "COUNT":
        hints.append(
            "QUERY TYPE: COUNT — user wants a count/total number. "
            "Use SELECT COUNT(*) or COUNT(col) with appropriate filters."
        )
        hints.append(
            "Return a count result, not a breakdown. Use COUNT(*) AS total."
        )

    elif query_type == "RANKING":
        hints.append(
            "QUERY TYPE: RANKING — user wants the top/bottom/highest/lowest item(s). "
            "Use ORDER BY metric DESC LIMIT N. Do not return all rows."
        )

    elif query_type == "AGGREGATION":
        fn = aggregation_fn or "SUM/COUNT/AVG"
        hints.append(
            f"QUERY TYPE: AGGREGATION — user wants an aggregate value. "
            f"Likely SQL: {fn}."
        )

    elif query_type == "COMPARISON":
        hints.append(
            "QUERY TYPE: COMPARISON — user wants side-by-side values. "
            "Use GROUP BY to return one row per compared item, not a scalar."
        )

    elif query_type == "TREND":
        hints.append(
            "QUERY TYPE: TREND — user wants time-series data. "
            "Use GROUP BY strftime('%Y-%m', date_col) ORDER BY period ASC."
        )

    elif query_type == "LIST":
        hints.append(
            "QUERY TYPE: LIST — user wants to see all distinct values of a dimension. "
            "Use SELECT DISTINCT col FROM table ORDER BY col."
        )

    if needs_distinct:
        hints.append(
            "IMPORTANT: User explicitly wants DISTINCT/UNIQUE values. "
            "Use COUNT(DISTINCT col) or SELECT DISTINCT col."
        )

    return {
        "query_type": query_type,
        "cache_threshold": cache_threshold,
        "aggregation_fn": aggregation_fn,
        "needs_distinct": needs_distinct,
        "is_factual": is_factual,
        "hints": hints,
    }
