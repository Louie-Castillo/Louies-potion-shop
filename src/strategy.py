from collections.abc import Iterable, Mapping


def allocate_inventory_targets(
    potion_ids: Iterable[int],
    units_sold: Mapping[int, int],
    capacity: int,
    profit_weights: Mapping[int, float] | None = None,
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

    if sold_ids and exploration_ids:
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
