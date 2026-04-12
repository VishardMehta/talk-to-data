from __future__ import annotations
"""
Data-aware chart generator.

Chart type is determined by DATA SHAPE, not LLM opinion.

Rules:
1. Single number (1 row, 1 col)         → None — caller uses st.metric()
2. Single column, multiple rows          → None — table only
3. Two cols: categorical + numeric       → horizontal bar (sorted)
4. Two cols: date + numeric              → line chart
5. Two cols: categorical + numeric ≤6   + BREAKDOWN pattern → donut chart
6. Three+ cols: categorical + multi-num → grouped bar
7. Time + multiple series               → multi-line
8. CHANGE_ANALYSIS pattern              → bar with green/red encoding
9. >15 categories                       → top 10 + "Others", horizontal bar
10. No clear fit                         → None (table only)
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

CHART_THEME = {
    "template": "plotly_white",
    "color_sequence": [
        "#6366F1",  # indigo
        "#06B6D4",  # cyan
        "#F59E0B",  # amber
        "#EF4444",  # red
        "#10B981",  # green
        "#8B5CF6",  # purple
        "#EC4899",  # pink
        "#F97316",  # orange
    ],
    "font_family": "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
    "font_size": 13,
    "title_font_size": 16,
}


def generate_chart(
    results: list,
    columns: list,
    pattern: str = None,
    question: str = "",
    # legacy arg kept for backward compat — ignored
    chart_suggestion: dict = None,
) -> go.Figure | None:
    """
    Generate appropriate chart based on data shape and query pattern.
    Returns None if chart is not appropriate — caller should show table/metric.
    """
    if not results or not columns:
        return None

    df = pd.DataFrame(results, columns=columns)

    # Rule 1: Single value — no chart, use st.metric()
    if len(df) == 1 and len(df.columns) == 1:
        return None

    # Rule 2: Single column list — no chart
    if len(df.columns) == 1:
        return None

    # Detect column types
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    date_cols = _detect_date_columns(df, non_numeric_cols)
    categorical_cols = [c for c in non_numeric_cols if c not in date_cols]

    # Nothing to plot without a numeric measure
    if not numeric_cols:
        return None

    # Collapse >15 categories → top 10 + Others
    if categorical_cols and len(df) > 15:
        df = _truncate_to_top_n(df, categorical_cols[0], numeric_cols[0], n=10)

    # Route to chart type
    if date_cols and numeric_cols:
        return _make_line_chart(df, date_cols[0], numeric_cols, pattern)

    if categorical_cols and len(numeric_cols) == 1:
        if pattern == "BREAKDOWN" and len(df) <= 6:
            return _make_donut_chart(df, categorical_cols[0], numeric_cols[0])
        if pattern == "CHANGE_ANALYSIS":
            return _make_change_bar_chart(df, categorical_cols[0], numeric_cols[0])
        return _make_horizontal_bar(df, categorical_cols[0], numeric_cols[0])

    if categorical_cols and len(numeric_cols) >= 2:
        return _make_grouped_bar(df, categorical_cols[0], numeric_cols[:3])

    return None


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        font=dict(
            family=CHART_THEME["font_family"],
            size=CHART_THEME["font_size"],
            color="#374151",
        ),
        title=dict(font=dict(size=CHART_THEME["title_font_size"], color="#111827"), x=0, xanchor="left"),
        margin=dict(l=16, r=16, t=56, b=16),
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.12,
            xanchor="center", x=0.5,
            font=dict(size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=380,
        hoverlabel=dict(bgcolor="white", font_size=12, font_family=CHART_THEME["font_family"]),
    )
    fig.update_xaxes(
        showgrid=False,
        showline=True, linewidth=1, linecolor="rgba(0,0,0,0.1)",
        tickfont=dict(size=11, color="#6B7280"),
    )
    fig.update_yaxes(
        showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.04)",
        showline=False,
        tickfont=dict(size=11, color="#6B7280"),
    )
    return fig


def _make_horizontal_bar(df: pd.DataFrame, cat_col: str, num_col: str) -> go.Figure:
    df_sorted = df.sort_values(num_col, ascending=True)
    fig = px.bar(
        df_sorted, x=num_col, y=cat_col, orientation="h",
        color_discrete_sequence=CHART_THEME["color_sequence"],
        text=num_col,
    )
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(yaxis_title="", xaxis_title=_fmt_col(num_col))
    return _apply_theme(fig)


def _make_line_chart(df: pd.DataFrame, date_col: str, num_cols: list, pattern: str) -> go.Figure:
    fig = go.Figure()
    colors = CHART_THEME["color_sequence"]
    for i, col in enumerate(num_cols[:4]):
        fig.add_trace(go.Scatter(
            x=df[date_col], y=df[col],
            mode="lines+markers",
            name=_fmt_col(col),
            line=dict(color=colors[i % len(colors)], width=2.5),
            marker=dict(size=6),
        ))
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _apply_theme(fig)


def _make_donut_chart(df: pd.DataFrame, cat_col: str, num_col: str) -> go.Figure:
    fig = px.pie(
        df, names=cat_col, values=num_col, hole=0.45,
        color_discrete_sequence=CHART_THEME["color_sequence"],
    )
    fig.update_traces(textposition="outside", textinfo="label+percent", textfont_size=12)
    return _apply_theme(fig)


def _make_change_bar_chart(df: pd.DataFrame, cat_col: str, num_col: str) -> go.Figure:
    colors = ["#10B981" if v >= 0 else "#EF4444" for v in df[num_col]]
    fig = go.Figure(go.Bar(
        x=df[cat_col], y=df[num_col],
        marker_color=colors,
        text=df[num_col],
        texttemplate="%{text:,.0f}",
        textposition="outside",
    ))
    fig.update_layout(xaxis_title="", yaxis_title=_fmt_col(num_col))
    return _apply_theme(fig)


def _make_grouped_bar(df: pd.DataFrame, cat_col: str, num_cols: list) -> go.Figure:
    fig = go.Figure()
    colors = CHART_THEME["color_sequence"]
    for i, col in enumerate(num_cols):
        fig.add_trace(go.Bar(
            name=_fmt_col(col),
            x=df[cat_col], y=df[col],
            marker_color=colors[i % len(colors)],
            text=df[col],
            texttemplate="%{text:,.0f}",
            textposition="outside",
        ))
    fig.update_layout(barmode="group", xaxis_title="", yaxis_title="")
    return _apply_theme(fig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_date_columns(df: pd.DataFrame, non_numeric_cols: list) -> list:
    date_cols = []
    for col in non_numeric_cols:
        try:
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().sum() > len(df) * 0.8:
                df[col] = parsed
                date_cols.append(col)
        except Exception:
            pass
    return date_cols


def _truncate_to_top_n(df: pd.DataFrame, cat_col: str, num_col: str, n: int = 10) -> pd.DataFrame:
    df_sorted = df.sort_values(num_col, ascending=False)
    top = df_sorted.head(n).copy()
    others_sum = df_sorted.iloc[n:][num_col].sum()
    if others_sum > 0:
        others_row = pd.DataFrame({cat_col: ["Others"], num_col: [others_sum]})
        top = pd.concat([top, others_row], ignore_index=True)
    return top


def _fmt_col(col: str) -> str:
    return col.replace("_", " ").replace("-", " ").title()


def format_indian_number(value, is_currency: bool = False) -> str:
    """Format numbers in Indian style — lakhs and crores."""
    if value is None:
        return "N/A"
    prefix = "₹" if is_currency else ""
    abs_val = abs(value)
    if abs_val >= 10_000_000:
        return f"{prefix}{value / 10_000_000:,.1f}Cr"
    elif abs_val >= 100_000:
        return f"{prefix}{value / 100_000:,.1f}L"
    elif abs_val >= 1_000:
        return f"{prefix}{value:,.0f}"
    else:
        return f"{prefix}{value:,.2f}" if isinstance(value, float) else f"{prefix}{value}"


def is_currency_column(col_name: str) -> bool:
    hints = ["amount", "revenue", "sales", "price", "cost", "total", "income", "profit", "spend"]
    return any(h in col_name.lower() for h in hints)
