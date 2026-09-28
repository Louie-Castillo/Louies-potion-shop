"""Generate Version 4 charts from the configured shop database."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import sqlalchemy
from sqlalchemy.engine import Connection

from src import database


OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "docs" / "metrics"
POTION_COLORS = {
    "red potion": "#dc2626",
    "green potion": "#16a34a",
    "blue potion": "#2563eb",
    "yellow potion": "#ca8a04",
}
FALLBACK_COLORS = ["#7c3aed", "#0891b2", "#ea580c", "#475569"]
GAME_DAYS = [
    "Edgeday",
    "Bloomday",
    "Arcanaday",
    "Hearthday",
    "Crownday",
    "Blesseday",
    "Soulday",
]


def write_svg(path: Path, width: int, height: int, body: list[str]) -> None:
    path.write_text(
        "\n".join(
            [
                (
                    f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
                    f'height="{height}" viewBox="0 0 {width} {height}">'
                ),
                "<style>",
                "text { font-family: Arial, Helvetica, sans-serif; fill: #0f172a; }",
                ".title { font-size: 30px; font-weight: 700; }",
                ".subtitle { font-size: 16px; fill: #475569; }",
                ".heading { font-size: 17px; font-weight: 700; }",
                ".label { font-size: 14px; fill: #334155; }",
                ".tick { font-size: 12px; fill: #64748b; }",
                ".value { font-size: 14px; font-weight: 700; }",
                "</style>",
                *body,
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )


def svg_text(
    x: float,
    y: float,
    value: object,
    css_class: str = "label",
    anchor: str = "start",
    fill: str | None = None,
) -> str:
    fill_attribute = f' fill="{fill}"' if fill else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{css_class}" '
        f'text-anchor="{anchor}"{fill_attribute}>{escape(str(value))}</text>'
    )


def color_for_potion(name: str, index: int) -> str:
    return POTION_COLORS.get(
        name.lower(), FALLBACK_COLORS[index % len(FALLBACK_COLORS)]
    )


def blend_with_white(color: str, strength: float) -> str:
    strength = max(0.0, min(1.0, strength))
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    blended = (
        round(255 - (255 - red) * strength),
        round(255 - (255 - green) * strength),
        round(255 - (255 - blue) * strength),
    )
    return "#{:02x}{:02x}{:02x}".format(*blended)


def readable_text_color(background: str) -> str:
    red = int(background[1:3], 16)
    green = int(background[3:5], 16)
    blue = int(background[5:7], 16)
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "#ffffff" if luminance < 135 else "#0f172a"


def nice_axis(maximum: int) -> tuple[int, int]:
    if maximum <= 5:
        step = 1
    elif maximum <= 10:
        step = 2
    elif maximum <= 25:
        step = 5
    else:
        step = 10
    return max(step, math.ceil(maximum / step) * step), step


def generate_sales_by_hour(
    potions: list[dict[str, Any]],
    sales: dict[tuple[int, int], int],
) -> None:
    width = 1280
    height = 780
    body = [
        "<title>Potion sales by game hour</title>",
        (
            "<desc>Four time-series panels show units sold for every catalog "
            "potion during each game hour.</desc>"
        ),
        '<rect width="1280" height="780" fill="#ffffff"/>',
        svg_text(55, 52, "Potion Sales by Game Hour", "title"),
        svg_text(
            55,
            80,
            "Actual checkout-ledger sales aggregated across recorded game days",
            "subtitle",
        ),
    ]

    maximum = max(sales.values(), default=0)
    y_max, y_step = nice_axis(maximum)
    panel_width = 570
    panel_height = 270
    panel_positions = [(55, 115), (655, 115), (55, 420), (655, 420)]

    for index, (potion, (left, top)) in enumerate(zip(potions, panel_positions)):
        potion_id = int(potion["id"])
        potion_name = str(potion["name"])
        potion_sku = str(potion["sku"])
        color = color_for_potion(potion_name, index)
        values = [sales.get((hour, potion_id), 0) for hour in range(24)]
        total = sum(values)

        body.append(
            f'<rect x="{left}" y="{top}" width="{panel_width}" '
            f'height="{panel_height}" rx="10" fill="#f8fafc" '
            'stroke="#cbd5e1"/>'
        )
        body.append(f'<circle cx="{left + 24}" cy="{top + 27}" r="7" fill="{color}"/>')
        body.append(svg_text(left + 40, top + 32, potion_name.title(), "heading"))
        body.append(svg_text(left + 40, top + 53, potion_sku, "tick"))
        body.append(
            svg_text(
                left + panel_width - 22,
                top + 32,
                f"{total} units total",
                "label",
                "end",
            )
        )

        chart_left = left + 55
        chart_right = left + panel_width - 24
        chart_top = top + 76
        chart_bottom = top + panel_height - 48
        chart_width = chart_right - chart_left
        chart_height = chart_bottom - chart_top

        for tick in range(0, y_max + 1, y_step):
            y = chart_bottom - (tick / y_max) * chart_height
            body.append(
                f'<line x1="{chart_left}" y1="{y:.1f}" x2="{chart_right}" '
                f'y2="{y:.1f}" stroke="#e2e8f0"/>'
            )
            body.append(svg_text(chart_left - 10, y + 4, tick, "tick", "end"))

        for hour in (0, 4, 8, 12, 16, 20, 23):
            x = chart_left + (hour / 23) * chart_width
            body.append(
                f'<line x1="{x:.1f}" y1="{chart_top}" x2="{x:.1f}" '
                f'y2="{chart_bottom}" stroke="#f1f5f9"/>'
            )
            body.append(svg_text(x, chart_bottom + 20, hour, "tick", "middle"))

        points = []
        for hour, value in enumerate(values):
            x = chart_left + (hour / 23) * chart_width
            y = chart_bottom - (value / y_max) * chart_height
            points.append(f"{x:.1f},{y:.1f}")
        body.append(
            f'<polyline points="{" ".join(points)}" fill="none" '
            f'stroke="{color}" stroke-width="3" stroke-linejoin="round"/>'
        )

        for hour, value in enumerate(values):
            if value == 0:
                continue
            x = chart_left + (hour / 23) * chart_width
            y = chart_bottom - (value / y_max) * chart_height
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
            body.append(svg_text(x, y - 9, value, "tick", "middle"))

        body.append(
            svg_text(
                (chart_left + chart_right) / 2,
                top + panel_height - 13,
                "Game hour",
                "tick",
                "middle",
            )
        )

    body.append(
        svg_text(
            55,
            745,
            "Source: inventory_transactions + potion_ledger_entries + potions",
            "subtitle",
        )
    )
    write_svg(OUTPUT_DIRECTORY / "potion-sales-by-hour.svg", width, height, body)


def generate_heatmap(
    filename: str,
    title: str,
    subtitle: str,
    row_heading: str,
    rows: list[str],
    potions: list[dict[str, Any]],
    values: dict[tuple[str, int], int],
) -> None:
    width = 1220
    row_height = 44 if len(rows) > 8 else 54
    top = 160
    bottom_padding = 70
    height = top + len(rows) * row_height + bottom_padding
    label_width = 210
    grid_left = 245
    grid_right = width - 45
    cell_width = (grid_right - grid_left) / len(potions)
    maximum = max(values.values(), default=1)

    body = [
        f"<title>{escape(title)}</title>",
        f"<desc>{escape(subtitle)}</desc>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        svg_text(45, 50, title, "title"),
        svg_text(45, 79, subtitle, "subtitle"),
        svg_text(label_width, 137, row_heading, "heading", "end"),
    ]

    for index, potion in enumerate(potions):
        center = grid_left + (index + 0.5) * cell_width
        color = color_for_potion(str(potion["name"]), index)
        body.append(f'<circle cx="{center - 48:.1f}" cy="132" r="6" fill="{color}"/>')
        body.append(svg_text(center - 36, 137, str(potion["name"]).title(), "heading"))

    for row_index, row in enumerate(rows):
        y = top + row_index * row_height
        body.append(svg_text(label_width, y + row_height / 2 + 5, row, "label", "end"))

        for potion_index, potion in enumerate(potions):
            potion_id = int(potion["id"])
            value = values.get((row, potion_id), 0)
            color = color_for_potion(str(potion["name"]), potion_index)
            strength = 0.0 if value == 0 else 0.18 + 0.70 * math.sqrt(value / maximum)
            background = "#f8fafc" if value == 0 else blend_with_white(color, strength)
            text_color = readable_text_color(background)
            x = grid_left + potion_index * cell_width

            body.append(
                f'<rect x="{x + 3:.1f}" y="{y + 3:.1f}" '
                f'width="{cell_width - 6:.1f}" height="{row_height - 6:.1f}" '
                f'rx="5" fill="{background}" stroke="#e2e8f0"/>'
            )
            body.append(
                svg_text(
                    x + cell_width / 2,
                    y + row_height / 2 + 5,
                    value,
                    "value",
                    "middle",
                    text_color,
                )
            )

    body.append(
        svg_text(
            45,
            height - 27,
            "Cell values are potion units sold; darker cells represent more units.",
            "subtitle",
        )
    )
    write_svg(OUTPUT_DIRECTORY / filename, width, height, body)


def fetch_rows(connection: Connection, query: str) -> list[dict[str, Any]]:
    return [
        dict(row._mapping)
        for row in connection.execute(
            sqlalchemy.text(query),
            {"checkout": "checkout"},
        )
    ]


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    with database.engine.connect() as connection:
        potions = fetch_rows(
            connection,
            """
            SELECT id, sku, name
            FROM potions
            ORDER BY id
            """,
        )
        hourly_rows = fetch_rows(
            connection,
            """
            SELECT
                transactions.game_hour,
                entries.potion_id,
                SUM(-entries.change)::INTEGER AS units_sold
            FROM inventory_transactions AS transactions
            JOIN potion_ledger_entries AS entries
                ON entries.transaction_id = transactions.id
            WHERE
                transactions.transaction_type = :checkout
                AND transactions.game_hour IS NOT NULL
                AND entries.change < 0
            GROUP BY transactions.game_hour, entries.potion_id
            ORDER BY transactions.game_hour, entries.potion_id
            """,
        )

        demographic_rows: dict[str, list[dict[str, Any]]] = {}
        for dimension, column in (
            ("class", "carts.character_class"),
            ("species", "carts.character_species"),
            ("level", "carts.level"),
        ):
            demographic_rows[dimension] = fetch_rows(
                connection,
                f"""
                SELECT
                    {column} AS category,
                    entries.potion_id,
                    SUM(-entries.change)::INTEGER AS units_sold
                FROM inventory_transactions AS transactions
                JOIN carts ON carts.id = transactions.cart_id
                JOIN potion_ledger_entries AS entries
                    ON entries.transaction_id = transactions.id
                WHERE
                    transactions.transaction_type = :checkout
                    AND entries.change < 0
                GROUP BY {column}, entries.potion_id
                ORDER BY {column}, entries.potion_id
                """,
            )

        day_rows = fetch_rows(
            connection,
            """
            SELECT
                transactions.game_day AS category,
                entries.potion_id,
                SUM(-entries.change)::INTEGER AS units_sold
            FROM inventory_transactions AS transactions
            JOIN potion_ledger_entries AS entries
                ON entries.transaction_id = transactions.id
            WHERE
                transactions.transaction_type = :checkout
                AND transactions.game_day IS NOT NULL
                AND entries.change < 0
            GROUP BY transactions.game_day, entries.potion_id
            ORDER BY transactions.game_day, entries.potion_id
            """,
        )

    hourly_sales = {
        (int(row["game_hour"]), int(row["potion_id"])): int(row["units_sold"])
        for row in hourly_rows
    }
    generate_sales_by_hour(potions, hourly_sales)

    class_values = {
        (str(row["category"]), int(row["potion_id"])): int(row["units_sold"])
        for row in demographic_rows["class"]
    }
    class_rows = sorted({category for category, _ in class_values})
    generate_heatmap(
        "purchases-by-class.svg",
        "Potion Purchases by Customer Class",
        "Completed checkout units grouped by character class and potion",
        "Class",
        class_rows,
        potions,
        class_values,
    )

    species_values = {
        (str(row["category"]), int(row["potion_id"])): int(row["units_sold"])
        for row in demographic_rows["species"]
    }
    species_rows = sorted({category for category, _ in species_values})
    generate_heatmap(
        "purchases-by-species.svg",
        "Potion Purchases by Customer Species",
        "Completed checkout units grouped by species and potion",
        "Species",
        species_rows,
        potions,
        species_values,
    )

    level_values = {
        (str(row["category"]), int(row["potion_id"])): int(row["units_sold"])
        for row in demographic_rows["level"]
    }
    numeric_levels = [int(category) for category, _ in level_values]
    level_rows = (
        [str(level) for level in range(min(numeric_levels), max(numeric_levels) + 1)]
        if numeric_levels
        else []
    )
    generate_heatmap(
        "purchases-by-level.svg",
        "Potion Purchases by Customer Level",
        "Completed checkout units for every observed level range",
        "Level",
        level_rows,
        potions,
        level_values,
    )

    day_values: dict[tuple[str, int], int] = {}
    for row in day_rows:
        day = str(row["category"])
        if day == "Aracanaday":
            day = "Arcanaday"
        day_values[(day, int(row["potion_id"]))] = int(row["units_sold"])
    generate_heatmap(
        "sales-by-game-day.svg",
        "Potion Sales by Game Day",
        "An additional view of weekly demand not shown by the hourly chart",
        "Game day",
        GAME_DAYS,
        potions,
        day_values,
    )


if __name__ == "__main__":
    main()
