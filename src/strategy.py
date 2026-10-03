from collections.abc import Iterable, Mapping


def allocate_inventory_targets(
    potion_ids: Iterable[int],
    units_sold: Mapping[int, int],
    capacity: int,
) -> dict[int, int]:
    """Allocate finished-potion capacity in proportion to recorded demand."""
    ids = sorted(potion_ids)

    if capacity < 0:
        raise ValueError("capacity must be non-negative")

    if not ids:
        return {}

    # A weight of one keeps new or lower-volume products represented while
    # allowing established demand to control most of the capacity.
    weights = {potion_id: max(1, units_sold.get(potion_id, 0)) for potion_id in ids}
    total_weight = sum(weights.values())
    targets = {
        potion_id: capacity * weights[potion_id] // total_weight for potion_id in ids
    }
    unallocated = capacity - sum(targets.values())

    remainder_order = sorted(
        ids,
        key=lambda potion_id: (
            -(capacity * weights[potion_id] % total_weight),
            potion_id,
        ),
    )

    for potion_id in remainder_order[:unallocated]:
        targets[potion_id] += 1

    return targets
