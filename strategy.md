# Version 4 Profitability Strategy

## Hypothesis

The shop will become more profitable by matching production to the demand
patterns already visible in completed checkouts instead of producing every
potion in equal quantities. The current sample contains 46 completed checkouts
and 75 potion units, so this is a working hypothesis that should be reevaluated
as more sales and barrel offers are recorded.

## 1. Keep red potion as the baseline product

Red potion accounts for 58 of the 75 units sold, or 77.3% of current unit
demand. At its catalog price of 50 gold, those sales represent 2,900 gold of
revenue. The hourly chart also shows repeated red demand across more time
windows than any other potion, including the two largest spikes at game hours
8 and 12.

My hypothesis is that keeping a larger safety stock of red potion will prevent
the most lost sales. The shop should direct roughly 70-80% of near-term brewing
capacity toward red while the demand mix remains similar. This is a starting
range rather than a permanent rule: the allocation should be recalculated from
the ledger as the sample grows.

## 2. Maintain smaller, targeted stock for the other classes

The class visualization shows a strong relationship between class and potion
choice in the current catalog:

- Warriors purchased all 58 red potions.
- Seers purchased all 8 green potions.
- Runesmiths purchased all 3 blue potions.
- Hunters purchased all 6 yellow potions.

Completely dropping the lower-volume potions would sacrifice entire customer
classes and could reduce recognition with those groups. Instead, the shop
should keep a smaller buffer of green, blue, and yellow potions while using red
as the high-volume base product. Yellow deserves special attention because its
60-gold selling price is higher than the 50-gold price of the pure potions, but
its 50/50 red-green recipe means it should only be brewed when its expected
margin exceeds the value of using those ingredients for pure potions.

## 3. Brew before the strongest demand windows

The hourly visualization shows the highest red demand at hour 12, followed by
hour 8. The game-day visualization shows the highest total demand on Hearthday
with 15 units. Soulday is the only observed day with sales of every potion
type.

My hypothesis is that brewing shortly before those windows will improve
availability without holding unnecessary inventory all week. The shop should:

1. Enter hours 8 and 12 with the largest red-potion buffer.
2. Enter Hearthday with the highest overall finished-potion inventory.
3. Enter Soulday with at least a small quantity of every potion because demand
   is more varied on that day.
4. Use lower-demand periods to rebuild ingredients and avoid consuming all
   available liquid immediately.

## 4. Purchase barrels by recipe need and cost per milliliter

Input cost must be considered together with sales demand. For any potion, the
estimated ingredient cost should be calculated as:

```text
ingredient cost =
    red recipe ml * red barrel cost/ml
  + green recipe ml * green barrel cost/ml
  + blue recipe ml * blue barrel cost/ml
  + dark recipe ml * dark barrel cost/ml
```

The `barrel_offers` instrumentation now records the information needed for
this comparison. At the time of this report, no post-deployment barrel catalog
had reached the table, so selecting a specific barrel as cheapest would be an
unsupported claim. Once offers are captured, the shop should prefer the lowest
cost-per-milliliter barrel that supplies the current recipe bottleneck, while
still preserving enough gold and storage capacity for the next demand window.

## 5. Validate the hypothesis with additional data

The current results are useful but still based on only 75 units. The shop
should refresh `metrics.md` after at least one complete game week and compare:

- each potion's share of units and revenue;
- checkout failures caused by unavailable inventory;
- profit margin using observed barrel costs rather than revenue alone;
- whether class preferences remain stable as more mixed potions are offered;
- whether the hour and day demand peaks repeat.

If those measurements continue to show red near 77% of demand, the shop should
retain the red-heavy plan. If mixed potions begin producing higher margins or
serving additional classes, brewing capacity should shift toward those recipes
even when their raw unit volume remains lower.

## 6. Build a low-cost dark-potion market before nighttime

After the competition reset, the initial red strategy completed 14 out of 14
checkouts and sold 59 red potions, but every successful customer was a Warrior.
That confirms strong reliability while also showing that recognition is
concentrated in only one class. The next strategy will preserve the reliable
red baseline while using a low-cost pure dark potion to reach nighttime classes
that the existing catalog does not serve.

Recorded wholesale history contains dark-bearing barrels, including a pure
10,000 ml dark barrel for 750 gold. That produces dark ingredient at 0.075 gold
per ml, or approximately 7.5 gold of ingredient cost for a 100 ml potion. The
dark potion will initially sell for 45 gold, leaving a strong estimated margin
while deliberately prioritizing customer value and recognition over the
highest possible unit price.

The production algorithm will maintain at least three bottles of every active
recipe for class coverage. Dark potion receives a larger minimum target:

- 20% of finished-potion capacity during ordinary daytime hours;
- 40% from game hour 16 through the night and through hour 4;
- the remaining capacity is allocated using recorded demand and estimated
  ingredient margin.

This is a controlled market-building strategy rather than an all-in bet. If a
wholesale tick has no barrel capable of producing dark potion, the planner will
fall back to the next most-needed active potion instead of skipping the entire
purchase opportunity. Dark sales, class recognition, and checkout reliability
should be reviewed after a complete game week before changing the price or
increasing the nighttime allocation further.
