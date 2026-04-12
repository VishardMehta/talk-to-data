from __future__ import annotations
"""
Agent 5 — Chart Agent

Runs AFTER SQL results are returned, BEFORE answer is displayed.
Two-step process:
  Step 1: Deterministic rules (covers 80% of cases) — no LLM needed
  Step 2: LLM refinement with 8B model for ambiguous cases

Returns a Plotly figure (or None) with annotations, highlights, and
professional formatting.
"""

import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from app.core.groq_client import call_llm
from app.utils.chart_generator import (
    _apply_theme,
    _detect_date_columns,
    _truncate_to_top_n,
    _fmt_col,
    CHART_THEME,
    format_indian_number,
    is_currency_column,
)


def _analyze_data_shape(df: pd.DataFrame) -> dict:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    date_cols = _detect_date_columns(df.copy(), non_numeric_cols)
    text_cols = [c for c in non_numeric_cols if c not in date_cols]
    n_rows = len(df)
    n_cols = len(df.columns)

    return {
        "n_rows": n_rows,
        "n_cols": n_cols,
        "n_numeric": len(numeric_cols),
        "n_text": len(text_cols),
        "n_date": len(date_cols),
        "numeric_cols": numeric_cols,
        "text_cols": text_cols,
        "date_cols": date_cols,
        "is_single_value": n_rows == 1 and n_cols <= 2,
        "is_time_series": len(date_cols) > 0 and len(numeric_cols) > 0,
        "is_categorical": len(text_cols) > 0 and len(numeric_cols) > 0 and len(date_cols) == 0,
        "is_comparison": n_rows >= 2 and n_rows <= 10 and len(text_cols) > 0,
        "has_too_many_categories": len(text_cols) > 0 and n_rows > 15,
    }


def _deterministic_chart_type(shape: dict, pattern: str) -> str | None:
    """Return chart type from rules — no LLM."""
    if shape["is_single_value"]:
        return "metric"
    if shape["n_numeric"] == 0:
        return "none"
    if shape["is_time_series"]:
        return "line"
    if shape["is_categorical"]:
        if pattern == "BREAKDOWN" and shape["n_rows"] <= 6:
            return "donut"
        if pattern == "CHANGE_ANALYSIS":
            return "change_bar"
        if shape["n_numeric"] >= 2:
            return "grouped_bar"
        return "horizontal_bar"
    return None  # ambiguous — use LLM


def _llm_chart_choice(question: str, shape: dict, pattern: str) -> dict:
    """Ask 8B model to choose chart config for ambiguous cases."""
    prompt = f"""User asked: "{question}"
Pattern: {pattern}
Data shape: {json.dumps({k: v for k, v in shape.items() if not isinstance(v, list)}, indent=2)}
Numeric columns: {shape["numeric_cols"]}
Text columns: {shape["text_cols"]}
Date columns: {shape["date_cols"]}

Choose the BEST chart type. Return JSON:
{{
  "chart_type": "horizontal_bar" | "line" | "donut" | "grouped_bar" | "metric" | "none",
  "x_column": "column name",
  "y_columns": ["column name(s)"],
  "title": "Short descriptive title",
  "sort_by": "value" | "name" | "none",
  "annotation": "one sentence insight to show on chart, or null"
}}

Rules:
- "none" if data doesn't benefit from visualization
- "metric" for single KPI values
- "donut" ONLY for composition questions with ≤6 categories
- "line" for anything with dates/time
- "horizontal_bar" is the DEFAULT for categorical+numeric
- "annotation" only if there's something genuinely notable"""

    try:
        return call_llm("chart", "Choose the best chart type. Return only JSON.", prompt, json_mode=True)
    except Exception:
        return {"chart_type": "horizontal_bar", "x_column": None, "y_columns": [], "annotation": None}


def generate_chart_figure(
    results: list,
    columns: list,
    pattern: str = None,
    question: str = "",
) -> tuple[go.Figure | None, str | None]:
    """
    Main entry point. Returns (figure, chart_type).
    figure is None for metric/none types — caller handles display.
    """
    if not results or not columns:
        return None, "none"

    df = pd.DataFrame(results, columns=columns)
    shape = _analyze_data_shape(df)

    # Deterministic rules first
    chart_type = _deterministic_chart_type(shape, pattern or "")

    annotation = None
    x_col = shape["text_cols"][0] if shape["text_cols"] else (shape["date_cols"][0] if shape["date_cols"] else None)
    y_cols = shape["numeric_cols"]

    # LLM fallback for ambiguous cases
    if chart_type is None:
        llm_cfg = _llm_chart_choice(question, shape, pattern or "")
        chart_type = llm_cfg.get("chart_type", "none")
        annotation = llm_cfg.get("annotation")
        if llm_cfg.get("x_column") and llm_cfg["x_column"] in columns:
            x_col = llm_cfg["x_column"]
        if llm_cfg.get("y_columns"):
            y_cols = [c for c in llm_cfg["y_columns"] if c in columns] or y_cols

    if chart_type in ("metric", "none"):
        return None, chart_type

    # Collapse >15 categories
    if shape["has_too_many_categories"] and x_col and y_cols:
        df = _truncate_to_top_n(df, x_col, y_cols[0], n=10)

    try:
        fig = _build_figure(df, chart_type, x_col, y_cols, pattern)
        if fig and annotation:
            _add_annotation(fig, annotation)
        return fig, chart_type
    except Exception:
        return None, "none"


def _build_figure(df, chart_type, x_col, y_cols, pattern) -> go.Figure | None:
    colors = CHART_THEME["color_sequence"]

    if chart_type == "horizontal_bar":
        if not x_col or not y_cols:
            return None
        df_sorted = df.sort_values(y_cols[0], ascending=True)
        fig = px.bar(df_sorted, x=y_cols[0], y=x_col, orientation="h",
                     color_discrete_sequence=colors, text=y_cols[0])
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(yaxis_title="", xaxis_title=_fmt_col(y_cols[0]))
        return _apply_professional_theme(fig)

    if chart_type == "line":
        date_col = x_col
        fig = go.Figure()
        for i, col in enumerate(y_cols[:4]):
            fig.add_trace(go.Scatter(
                x=df[date_col], y=df[col],
                mode="lines+markers",
                name=_fmt_col(col),
                line=dict(color=colors[i % len(colors)], width=2.5),
                marker=dict(size=6),
            ))
        # Trend line for single series
        if len(y_cols) == 1 and len(df) > 3:
            try:
                import numpy as np
                z = np.polyfit(range(len(df)), df[y_cols[0]].fillna(0), 1)
                p = np.poly1d(z)
                fig.add_trace(go.Scatter(
                    x=df[date_col], y=p(range(len(df))),
                    mode="lines", name="Trend",
                    line=dict(dash="dash", color="gray", width=1.5),
                    opacity=0.6,
                ))
            except Exception:
                pass
        return _apply_professional_theme(fig)

    if chart_type == "donut":
        if not x_col or not y_cols:
            return None
        fig = px.pie(df, names=x_col, values=y_cols[0], hole=0.45,
                     color_discrete_sequence=colors)
        fig.update_traces(textposition="outside", textinfo="label+percent", textfont_size=12)
        return _apply_professional_theme(fig)

    if chart_type == "change_bar":
        if not x_col or not y_cols:
            return None
        bar_colors = ["#10B981" if v >= 0 else "#EF4444" for v in df[y_cols[0]]]
        fig = go.Figure(go.Bar(
            x=df[x_col], y=df[y_cols[0]],
            marker_color=bar_colors,
            text=df[y_cols[0]],
            texttemplate="%{text:,.0f}",
            textposition="outside",
        ))
        fig.update_layout(xaxis_title="", yaxis_title=_fmt_col(y_cols[0]))
        return _apply_professional_theme(fig)

    if chart_type == "grouped_bar":
        if not x_col or not y_cols:
            return None
        fig = go.Figure()
        for i, col in enumerate(y_cols[:3]):
            fig.add_trace(go.Bar(
                name=_fmt_col(col), x=df[x_col], y=df[col],
                marker_color=colors[i % len(colors)],
                text=df[col], texttemplate="%{text:,.0f}", textposition="outside",
            ))
        fig.update_layout(barmode="group", xaxis_title="", yaxis_title="")
        return _apply_professional_theme(fig)

    return None


def _add_annotation(fig: go.Figure, text: str):
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.06,
        text=f"<i>{text}</i>",
        showarrow=False,
        font=dict(size=11, color="#6B7280"),
        xanchor="left",
    )


def _apply_professional_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        font=dict(family=CHART_THEME["font_family"], size=CHART_THEME["font_size"], color="#374151"),
        margin=dict(l=16, r=16, t=64, b=16),
        legend=dict(
            orientation="h", yanchor="top", y=-0.14,
            xanchor="center", x=0.5,
            font=dict(size=11), bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=390,
        hoverlabel=dict(bgcolor="white", font_size=12, font_family=CHART_THEME["font_family"]),
    )
    fig.update_xaxes(
        showgrid=False, showline=True, linewidth=1, linecolor="rgba(0,0,0,0.1)",
        tickfont=dict(size=11, color="#6B7280"),
    )
    fig.update_yaxes(
        showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.04)",
        showline=False, tickfont=dict(size=11, color="#6B7280"),
    )
    return fig
