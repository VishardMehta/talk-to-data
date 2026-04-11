import plotly.express as px
import plotly.graph_objects as go


def generate_chart(
    results: list,
    columns: list,
    chart_suggestion: dict,
) -> go.Figure | None:
    """
    Generate a Plotly figure from SQL results.
    Returns None if data is not chartable.
    """
    if not results or not columns or not chart_suggestion:
        return None

    # Need at least 2 columns (x + y) for most chart types
    chart_type = chart_suggestion.get("type", "bar")
    x_col = chart_suggestion.get("x_column")
    y_col = chart_suggestion.get("y_column")
    title = chart_suggestion.get("title", "")

    # Convert list-of-tuples to list-of-dicts
    rows = [dict(zip(columns, row)) for row in results]

    if not rows:
        return None

    # Auto-detect x and y if not specified
    if not x_col or x_col not in columns:
        x_col = columns[0]
    if not y_col or y_col not in columns:
        numeric_cols = [c for c in columns if c != x_col and _is_numeric_col(rows, c)]
        y_col = numeric_cols[0] if numeric_cols else (columns[1] if len(columns) > 1 else columns[0])

    try:
        if chart_type == "bar":
            fig = px.bar(
                rows, x=x_col, y=y_col, title=title,
                template="plotly_white",
                color_discrete_sequence=["#1f77b4"],
            )
        elif chart_type == "grouped_bar":
            # If there's a third grouping column, use it as color
            color_col = None
            for c in columns:
                if c not in (x_col, y_col) and not _is_numeric_col(rows, c):
                    color_col = c
                    break
            fig = px.bar(
                rows, x=x_col, y=y_col, color=color_col,
                barmode="group", title=title,
                template="plotly_white",
            )
        elif chart_type == "pie":
            fig = px.pie(
                rows, names=x_col, values=y_col, title=title,
                template="plotly_white",
            )
        elif chart_type == "line":
            fig = px.line(
                rows, x=x_col, y=y_col, title=title,
                template="plotly_white",
                markers=True,
            )
        else:
            fig = px.bar(
                rows, x=x_col, y=y_col, title=title,
                template="plotly_white",
            )

        fig.update_layout(margin=dict(l=40, r=40, t=60, b=40))
        return fig

    except Exception:
        return None


def _is_numeric_col(rows: list[dict], col: str) -> bool:
    for row in rows:
        val = row.get(col)
        if val is not None:
            return isinstance(val, (int, float))
    return False
