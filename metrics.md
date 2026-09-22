# Shop Metrics

This report uses the shop's real production data. The charts were generated on
September 21, 2026 from 46 completed checkouts containing 75 potion units. To
refresh them after more game activity, run:

```bash
uv run python -m scripts.generate_version4_charts
```

## 1. Potion sales by game hour

This query creates one row for every game hour and every potion currently in
the catalog. It joins completed checkout transactions to their potion-ledger
entries and converts each negative inventory change into a positive number of
units sold.

```sql
WITH hourly_sales AS (
    SELECT
        transactions.game_hour,
        entries.potion_id,
        SUM(-entries.change)::INTEGER AS units_sold
    FROM inventory_transactions AS transactions
    JOIN potion_ledger_entries AS entries
        ON entries.transaction_id = transactions.id
    WHERE
        transactions.transaction_type = 'checkout'
        AND transactions.game_hour IS NOT NULL
        AND entries.change < 0
    GROUP BY
        transactions.game_hour,
        entries.potion_id
),
hours AS (
    SELECT generate_series(0, 23) AS game_hour
)
SELECT
    hours.game_hour,
    potions.id AS potion_id,
    potions.sku,
    potions.name,
    COALESCE(hourly_sales.units_sold, 0) AS units_sold
FROM hours
CROSS JOIN potions
LEFT JOIN hourly_sales
    ON hourly_sales.game_hour = hours.game_hour
    AND hourly_sales.potion_id = potions.id
ORDER BY
    hours.game_hour,
    potions.id;
```

| Potion | SKU | Units sold |
| --- | --- | ---: |
| Red potion | `RED_POTION_0` | 58 |
| Green potion | `GREEN_POTION_0` | 8 |
| Blue potion | `BLUE_POTION_0` | 3 |
| Yellow potion | `YELLOW_POTION_0` | 6 |

![Potion sales by game hour](docs/metrics/potion-sales-by-hour.svg)

### Finding

Red potion accounts for 58 of 75 units sold (77.3%), with the largest hourly
spikes at hour 12 (13 units) and hour 8 (10 units). The other potions sell in
smaller, more concentrated windows, so production should not treat all potion
types as equally demanded.

## 2. Barrel offers and cost per milliliter

The shop now records every distinct barrel offer received by `/barrels/plan`,
including the game day and hour. Identical offers received during the same game
hour are stored once so request retries do not inflate the data.

```sql
WITH distinct_offers AS (
    SELECT DISTINCT
        game_day,
        game_hour,
        sku,
        ml_per_barrel,
        red_fraction,
        green_fraction,
        blue_fraction,
        dark_fraction,
        price,
        quantity,
        CASE game_day
            WHEN 'Edgeday' THEN 1
            WHEN 'Bloomday' THEN 2
            WHEN 'Arcanaday' THEN 3
            WHEN 'Aracanaday' THEN 3
            WHEN 'Hearthday' THEN 4
            WHEN 'Crownday' THEN 5
            WHEN 'Blesseday' THEN 6
            WHEN 'Soulday' THEN 7
            ELSE 8
        END AS day_order
    FROM barrel_offers
)
SELECT
    game_day,
    game_hour,
    sku,
    CONCAT_WS(
        ' + ',
        CASE
            WHEN red_fraction > 0
            THEN TO_CHAR((red_fraction * 100)::NUMERIC, 'FM990.##') || '% red'
        END,
        CASE
            WHEN green_fraction > 0
            THEN TO_CHAR((green_fraction * 100)::NUMERIC, 'FM990.##') || '% green'
        END,
        CASE
            WHEN blue_fraction > 0
            THEN TO_CHAR((blue_fraction * 100)::NUMERIC, 'FM990.##') || '% blue'
        END,
        CASE
            WHEN dark_fraction > 0
            THEN TO_CHAR((dark_fraction * 100)::NUMERIC, 'FM990.##') || '% dark'
        END
    ) AS liquid_type,
    ml_per_barrel,
    price,
    ROUND(price::NUMERIC / NULLIF(ml_per_barrel, 0), 4) AS cost_per_ml,
    quantity
FROM distinct_offers
ORDER BY
    day_order,
    game_hour,
    sku;
```

The deployed `barrel_offers` table did not yet contain rows at this snapshot,
so there are no actual offers to display in the required table without
inventing data. The collection code and query are ready; this section can be
completed after the deployed shop receives another `/barrels/plan` request.
Historical wholesale catalogs cannot be reconstructed from barrel-delivery
transactions because those record purchases, not every barrel that was
offered.

| Game day | Game hour | Barrel SKU | Liquid type | mL per barrel | Price | Cost per mL |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| _No offers recorded at this snapshot_ | — | — | — | — | — | — |

## 3. Potion purchases by class, species, and level

The following query links each completed checkout to the cart's customer
details, then totals the actual potion units purchased for each demographic.

```sql
WITH checkout_sales AS (
    SELECT
        carts.character_class,
        carts.character_species,
        carts.level,
        potions.id AS potion_id,
        potions.sku,
        potions.name AS potion_name,
        -entries.change AS units_sold
    FROM inventory_transactions AS transactions
    JOIN carts
        ON carts.id = transactions.cart_id
    JOIN potion_ledger_entries AS entries
        ON entries.transaction_id = transactions.id
    JOIN potions
        ON potions.id = entries.potion_id
    WHERE
        transactions.transaction_type = 'checkout'
        AND entries.change < 0
),
demographic_sales AS (
    SELECT
        1 AS dimension_order,
        'class' AS dimension,
        character_class AS demographic_value,
        LOWER(character_class) AS value_order,
        potion_id,
        sku,
        potion_name,
        SUM(units_sold)::INTEGER AS units_sold
    FROM checkout_sales
    GROUP BY character_class, potion_id, sku, potion_name

    UNION ALL

    SELECT
        2 AS dimension_order,
        'species' AS dimension,
        character_species AS demographic_value,
        LOWER(character_species) AS value_order,
        potion_id,
        sku,
        potion_name,
        SUM(units_sold)::INTEGER AS units_sold
    FROM checkout_sales
    GROUP BY character_species, potion_id, sku, potion_name

    UNION ALL

    SELECT
        3 AS dimension_order,
        'level' AS dimension,
        level::TEXT AS demographic_value,
        LPAD(level::TEXT, 3, '0') AS value_order,
        potion_id,
        sku,
        potion_name,
        SUM(units_sold)::INTEGER AS units_sold
    FROM checkout_sales
    GROUP BY level, potion_id, sku, potion_name
)
SELECT
    dimension,
    demographic_value,
    sku,
    potion_name,
    units_sold
FROM demographic_sales
ORDER BY dimension_order, value_order, potion_id;
```

![Potion purchases by customer class](docs/metrics/purchases-by-class.svg)

![Potion purchases by customer species](docs/metrics/purchases-by-species.svg)

![Potion purchases by customer level](docs/metrics/purchases-by-level.svg)

### Findings

- Demand separates very clearly by class: Warriors purchased all 58 red
  potions, Seers all 8 green, Runesmiths all 3 blue, and Hunters all 6 yellow.
- Folk customers bought 53 of the 75 units, making them the largest species
  segment. Their demand still spans all four potion types.
- Level 10 is the strongest single level with 11 red-potion units. Demand is
  spread from levels 3 through 17 rather than being limited to one narrow level
  band.

## 4. Additional insight: sales by game day

The first chart shows demand by hour but not whether demand changes throughout
the game week. This query groups the same completed sales by game day.

```sql
SELECT
    transactions.game_day,
    potions.id AS potion_id,
    potions.sku,
    potions.name,
    SUM(-entries.change)::INTEGER AS units_sold
FROM inventory_transactions AS transactions
JOIN potion_ledger_entries AS entries
    ON entries.transaction_id = transactions.id
JOIN potions
    ON potions.id = entries.potion_id
WHERE
    transactions.transaction_type = 'checkout'
    AND transactions.game_day IS NOT NULL
    AND entries.change < 0
GROUP BY
    transactions.game_day,
    potions.id,
    potions.sku,
    potions.name
ORDER BY
    CASE transactions.game_day
        WHEN 'Edgeday' THEN 1
        WHEN 'Bloomday' THEN 2
        WHEN 'Arcanaday' THEN 3
        WHEN 'Aracanaday' THEN 3
        WHEN 'Hearthday' THEN 4
        WHEN 'Crownday' THEN 5
        WHEN 'Blesseday' THEN 6
        WHEN 'Soulday' THEN 7
        ELSE 8
    END,
    potions.id;
```

![Potion sales by game day](docs/metrics/sales-by-game-day.svg)

### Finding

Hearthday has the highest total sales (15 units), while Soulday is the only day
with recorded demand for all four potion types. Edgeday, Bloomday, and Blesseday
currently show only red-potion sales. This suggests the shop should vary its
production mix by day instead of using one fixed daily recipe plan.
