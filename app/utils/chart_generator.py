from __future__ import annotations
"""
Smart Chart Generator — Data-shape-aware chart selection.

Chart type is determined by DATA SHAPE, not LLM opinion:
1. Single value → None (use st.metric)
2. Single col list → None (table only)
3. Cat + Numeric → Horizontal bar
4. Date + Numeric → Line chart
5. Cat + Numeric (≤6, BREAKDOWN) → Donut
6. Cat + Multi-Numeric → Grouped bar
7. CHANGE_ANALYSIS → Color-coded bar (green/red)
8. >15 categories → Top 10 + Others
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Premium color palette
COLORS = [
    "#6366F1",  # indigo
    "#06B6D4",  # cyan
    "#F59E0B",  # amber
    "#10B981",  # emerald
    "#EF4444",  # red
    "#8B5CF6",  # violet
    "#EC4899",  # pink
    "#F97316",  # orange
]

POSITIVE_COLOR = "#10B981"
NEGATIVE_COLOR = "#EF4444"


def generate_chart(
    results: list,
    columns: list,
    chart_suggestion: dict = None,
    pattern: str = None,
    question: str = "",
) -> go.Figure | None:
    """Generate appropriate chart based on data shape and query pattern."""
    if not results or not columns:
        return None

    df = pd.DataFrame(results, columns=columns)

    # Rule 1: Single value — no chart (use st.metric in main.py)
    if len(df) == 1 and len(df.columns) <= 2:
        return None

    # Rule 2: Single column list — no chart
    if len(df.columns) == 1:
        return None

    # Detect column types
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    date_cols = _detect_date_columns(df, non_numeric_cols)
    categorical_cols = [c for c in non_numeric_cols if c not in date_cols]

    if not numeric_cols:
        return None  # No numeric data to chart

    # Rule: Too many categories → truncate
    if len(df) > 15 and categorical_cols and numeric_cols:
        df = _truncate_top_n(df, categorical_cols[0], numeric_cols[0], n=10)

    # Route to appropriate chart
    if date_cols and numeric_cols:
        return _make_line_chart(df, date_cols[0], numeric_cols)

    if categorical_cols and len(numeric_cols) == 1:
        if pattern == "BREAKDOWN" and len(df) <= 6:
            return _make_donut_chart(df, categorical_cols[0], numeric_cols[0])
        if pattern == "CHANGE_ANALYSIS":
            return _make_change_bar(df, categorical_cols[0], numeric_cols[0])
        return _make_horizontal_bar(df, categorical_cols[0], numeric_cols[0])

    if categorical_cols and len(numeric_cols) >= 2:
        return _make_grouped_bar(df, categorical_cols[0], numeric_cols[:3])

    # Fallback: try chart_suggestion from LLM if deterministic failed
    if chart_suggestion and categorical_cols and numeric_cols:
        return _make_horizontal_bar(df, categorical_cols[0], numeric_cols[0])

    return None


# ── Theme ────────────────────────────────────────────────────────

def _apply_theme(fig: go.Figure) -> go.Figure:
    """Apply premium dark theme to any Plotly figure."""
    fig.update_layout(
        font=dict(family="Inter, -apple-system, sans-serif", size=12, color="#F1F3F9"),
        title=dict(font=dict(size=15, color="#F1F3F9"), x=0, xanchor="left", y=0.98),
        margin=dict(l=16, r=16, t=56, b=16),
        legend=dict(
            orientation="h", yanchor="top", y=-0.12,
            xanchor="center", x=0.5,
            font=dict(size=11, color="#8B92A5"),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="rgba(30,34,53,0.6)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=380,
        hoverlabel=dict(
            bgcolor="#1E2235", font_size=12,
            font_family="Inter, sans-serif",
            bordercolor="rgba(99,102,241,0.3)",
        ),
    )
    fig.update_xaxes(
        showgrid=False, showline=True, linewidth=1,
        linecolor="rgba(255,255,255,0.1)",
        tickfont=dict(size=11, color="#8B92A5"),
    )
    fig.update_yaxes(
        showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.04)",
        showline=False, tickfont=dict(size=11, color="#8B92A5"),
    )
    return fig


# ── Chart Builders ───────────────────────────────────────────────

def _make_horizontal_bar(df, cat_col, num_col):
    """Horizontal bar — the workhorse chart. Always readable."""
    df_sorted = df.sort_values(num_col, ascending=True)
    fig = px.bar(
        df_sorted, x=num_col, y=cat_col, orientation="h",
        color_discrete_sequence=COLORS,
        text=num_col,
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}", textposition="outside",
        marker_line_width=0, opacity=0.9,
    )
    fig.update_layout(yaxis_title="", xaxis_title=_format_col(num_col))
    return _apply_theme(fig)


def _make_line_chart(df, date_col, num_cols):
    """Line chart for time series."""
    fig = go.Figure()
    for i, col in enumerate(num_cols[:4]):
        fig.add_trace(go.Scatter(
            x=df[date_col], y=df[col],
            mode="lines+markers",
            name=_format_col(col),
            line=dict(color=COLORS[i % len(COLORS)], width=2.5),
            marker=dict(size=6, line=dict(width=2, color="#1E2235")),
        ))
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _apply_theme(fig)


def _make_donut_chart(df, cat_col, num_col):
    """Donut chart — only for breakdowns with ≤6 categories."""
    fig = px.pie(
        df, names=cat_col, values=num_col, hole=0.45,
        color_discrete_sequence=COLORS,
    )
    fig.update_traces(
        textposition="outside", textinfo="label+percent",
        textfont_size=11,
        marker=dict(line=dict(color="#1E2235", width=2)),
    )
    return _apply_theme(fig)


def _make_change_bar(df, cat_col, num_col):
    """Bar chart with green/red color encoding for changes."""
    colors = [POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in df[num_col]]
    fig = go.Figure(go.Bar(
        x=df[cat_col], y=df[num_col],
        marker_color=colors,
        text=df[num_col],
        texttemplate="%{text:,.0f}",
        textposition="outside",
    ))
    fig.update_layout(xaxis_title="", yaxis_title=_format_col(num_col))
    return _apply_theme(fig)


def _make_grouped_bar(df, cat_col, num_cols):
    """Side-by-side bars for comparison / multi-metric."""
    fig = go.Figure()
    for i, col in enumerate(num_cols):
        fig.add_trace(go.Bar(
            name=_format_col(col),
            x=df[cat_col], y=df[col],
            marker_color=COLORS[i % len(COLORS)],
            text=df[col],
            texttemplate="%{text:,.0f}",
            textposition="outside",
        ))
    fig.update_layout(barmode="group", xaxis_title="", yaxis_title="")
    return _apply_theme(fig)


# ── Helpers ──────────────────────────────────────────────────────

def _detect_date_columns(df, non_numeric_cols):
    """Try to detect date columns by parsing."""
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


def _truncate_top_n(df, cat_col, num_col, n=10):
    """Keep top N categories, merge rest into 'Others'."""
    df_sorted = df.sort_values(num_col, ascending=False)
    top = df_sorted.head(n)
    others_sum = df_sorted.iloc[n:][num_col].sum()
    if others_sum > 0:
        others_row = pd.DataFrame({cat_col: ["Others"], num_col: [others_sum]})
        top = pd.concat([top, others_row], ignore_index=True)
    return top


def _format_col(col):
    """Turn 'total_revenue' into 'Total Revenue'."""
    return col.replace("_", " ").replace("-", " ").title()


def format_column_name(col):
    """Public alias for _format_col."""
    return _format_col(col)


def is_currency_column(col_name):
    """Detect if column likely contains currency values."""
    hints = ["amount", "revenue", "sales", "price", "cost", "total", "income", "profit", "spend"]
    return any(h in col_name.lower() for h in hints)


def format_indian_number(value, is_currency=False):
    """Format numbers the Indian way — lakhs and crores."""
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
