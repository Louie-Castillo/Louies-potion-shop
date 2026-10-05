from collections.abc import Iterable, Mapping


DIVERSIFICATION_STOCK_FLOOR = 3
DARK_DAY_STOCK_SHARE = 0.20
DARK_NIGHT_STOCK_SHARE = 0.40
DARK_MARKET_HOURS = frozenset({0, 2, 4, 16, 18, 20, 22})


def allocate_inventory_targets(
    potion_ids: Iterable[int],
    units_sold: Mapping[int, int],
    capacity: int,
    profit_weights: Mapping[int, float] | None = None,
    minimum_targets: Mapping[int, int] | None = None,
) -> dict[int, int]:
    """Allocate finished-potion capacity in proportion to recorded demand."""
    ids = sorted(potion_ids)

    if capacity < 0:
        raise ValueError("capacity must be non-negative")

    if not ids:
        return {}

    sold_ids = [potion_id for potion_id in ids if units_sold.get(potion_id, 0) > 0]
    exploration_ids = [potion_id for potion_id in ids if potion_id not in sold_ids]
    targets = {potion_id: 0 for potion_id in ids}

    if minimum_targets is not None:
        remaining_capacity = capacity
        for potion_id in ids:
            requested_minimum = max(0, minimum_targets.get(potion_id, 0))
            allocated_minimum = min(requested_minimum, remaining_capacity)
            targets[potion_id] = allocated_minimum
            remaining_capacity -= allocated_minimum

        capacity = remaining_capacity
        ids_to_allocate = sold_ids or ids
    elif sold_ids and exploration_ids:
        exploration_slots = min(capacity, len(exploration_ids))
        for potion_id in exploration_ids[:exploration_slots]:
            targets[potion_id] = 1
        capacity -= exploration_slots
        ids_to_allocate = sold_ids
    else:
        ids_to_allocate = ids

    if capacity == 0:
        return targets

    weights: dict[int, int] = {}
    for potion_id in ids_to_allocate:
        demand = max(1, units_sold.get(potion_id, 0))
        profit = 1.0
        if sold_ids and profit_weights is not None:
            profit = max(1.0, profit_weights.get(potion_id, 1.0))
        weights[potion_id] = max(1, round(demand * profit))

    total_weight = sum(weights.values())
    allocated = 0
    for potion_id in ids_to_allocate:
        allocation = capacity * weights[potion_id] // total_weight
        targets[potion_id] += allocation
        allocated += allocation
    unallocated = capacity - allocated

    remainder_order = sorted(
        ids_to_allocate,
        key=lambda potion_id: (
            -(capacity * weights[potion_id] % total_weight),
            potion_id,
        ),
    )

    for potion_id in remainder_order[:unallocated]:
        targets[potion_id] += 1

    return targets


def build_market_minimum_targets(
    potion_recipes: Mapping[int, list[int]],
    capacity: int,
    game_hour: int | None,
) -> dict[int, int]:
    """Reserve class coverage and a larger dark-potion position near night."""
    if capacity < 0:
        raise ValueError("capacity must be non-negative")

    potion_ids = sorted(potion_recipes)
    if not potion_ids or capacity == 0:
        return {potion_id: 0 for potion_id in potion_ids}

    floor = min(
        DIVERSIFICATION_STOCK_FLOOR,
        capacity // len(potion_ids),
    )
    minimums = {potion_id: floor for potion_id in potion_ids}
    dark_ids = [
        potion_id
        for potion_id, recipe in potion_recipes.items()
        if len(recipe) >= 4 and recipe[3] > 0
    ]

    if not dark_ids:
        return minimums

    dark_share = (
        DARK_NIGHT_STOCK_SHARE
        if game_hour in DARK_MARKET_HOURS
        else DARK_DAY_STOCK_SHARE
    )
    dark_target = max(floor * len(dark_ids), round(capacity * dark_share))
    dark_target = min(
        dark_target,
        capacity - floor * (len(potion_ids) - len(dark_ids)),
    )

    per_dark_potion, remainder = divmod(dark_target, len(dark_ids))
    for index, potion_id in enumerate(sorted(dark_ids)):
        minimums[potion_id] = per_dark_potion + (1 if index < remainder else 0)

    return minimums


def estimate_potion_margins(
    potion_specs: Mapping[int, tuple[int, list[int]]],
    ingredient_costs: Mapping[str, float],
) -> dict[int, float]:
    colors = ("red", "green", "blue", "dark")
    margins: dict[int, float] = {}

    for potion_id, (price, recipe) in potion_specs.items():
        estimated_cost = sum(
            recipe[index] * ingredient_costs.get(color, 0.0)
            for index, color in enumerate(colors)
        )
        margins[potion_id] = max(1.0, price - estimated_cost)

    return margins
