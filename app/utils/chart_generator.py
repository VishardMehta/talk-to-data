"""
Auto-generate Plotly charts from query results.
Maps chart type suggestions from the answer generator to Plotly figures.
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def generate_chart(
    results: list,
    columns: list,
    chart_suggestion: dict,
) -> go.Figure | None:
    """
    Generate a Plotly chart from query results and chart suggestion.

    Args:
        results: List of tuples/lists from SQL query
        columns: Column names from cursor.description
        chart_suggestion: Dict with 'type', 'x_column', 'y_column', 'title'

    Returns:
        Plotly Figure or None if results can't be charted
    """
    if not results or not columns or not chart_suggestion:
        return None

    # Build DataFrame
    try:
        df = pd.DataFrame(results, columns=columns)
    except Exception:
        return None

    if df.empty or len(df.columns) < 2:
        return None

    chart_type = chart_suggestion.get("type", "bar")
    x_col = chart_suggestion.get("x_column", "")
    y_col = chart_suggestion.get("y_column", "")
    title = chart_suggestion.get("title", "Chart")

    # Resolve column names — if suggested columns don't exist, pick best guesses
    x_col = _resolve_column(x_col, df, prefer="categorical")
    y_col = _resolve_column(y_col, df, prefer="numeric", exclude=[x_col])

    if not x_col or not y_col:
        return None

    # ── Color scheme ──
    color_sequence = [
        "#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd",
        "#818cf8", "#7c3aed", "#5b21b6", "#4f46e5",
    ]

    try:
        if chart_type == "bar":
            fig = px.bar(
                df, x=x_col, y=y_col,
                title=title,
                template="plotly_white",
                color_discrete_sequence=color_sequence,
            )

        elif chart_type == "grouped_bar":
            # Find a grouping column
            group_col = _find_group_column(df, exclude=[x_col, y_col])
            if group_col:
                fig = px.bar(
                    df, x=x_col, y=y_col, color=group_col,
                    barmode="group",
                    title=title,
                    template="plotly_white",
                    color_discrete_sequence=color_sequence,
                )
            else:
                fig = px.bar(
                    df, x=x_col, y=y_col,
                    title=title,
                    template="plotly_white",
                    color_discrete_sequence=color_sequence,
                )

        elif chart_type == "pie":
            fig = px.pie(
                df, names=x_col, values=y_col,
                title=title,
                color_discrete_sequence=color_sequence,
            )

        elif chart_type == "line":
            fig = px.line(
                df, x=x_col, y=y_col,
                title=title,
                template="plotly_white",
                color_discrete_sequence=color_sequence,
                markers=True,
            )

        else:
            # Default to bar
            fig = px.bar(
                df, x=x_col, y=y_col,
                title=title,
                template="plotly_white",
                color_discrete_sequence=color_sequence,
            )

        # ── Style the chart ──
        fig.update_layout(
            font=dict(family="Inter, sans-serif", size=13),
            title_font_size=16,
            title_x=0.0,
            margin=dict(l=40, r=20, t=60, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5,
            ),
        )

        return fig

    except Exception:
        return None


def _resolve_column(
    suggested: str,
    df: pd.DataFrame,
    prefer: str = "categorical",
    exclude: list = None,
) -> str | None:
    """
    Resolve a suggested column name to an actual DataFrame column.
    Falls back to best-guess based on column type preference.
    """
    exclude = exclude or []

    # Exact match
    if suggested in df.columns and suggested not in exclude:
        return suggested

    # Case-insensitive match
    col_map = {c.lower(): c for c in df.columns}
    if suggested.lower() in col_map:
        col_name = col_map[suggested.lower()]
        if col_name not in exclude:
            return col_name

    # Partial match
    for col in df.columns:
        if col in exclude:
            continue
        if suggested.lower() in col.lower() or col.lower() in suggested.lower():
            return col

    # Fallback: pick by type preference
    available = [c for c in df.columns if c not in exclude]
    if not available:
        return None

    if prefer == "numeric":
        for col in available:
            if pd.api.types.is_numeric_dtype(df[col]):
                return col
        return available[0]
    else:
        for col in available:
            if not pd.api.types.is_numeric_dtype(df[col]):
                return col
        return available[0]


def _find_group_column(
    df: pd.DataFrame,
    exclude: list = None,
) -> str | None:
    """Find a suitable grouping column (non-numeric, not excluded)."""
    exclude = exclude or []
    
    for col in df.columns:
        if col in exclude:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            nunique = df[col].nunique()
            if 2 <= nunique <= 10:
                return col
    
    return None
