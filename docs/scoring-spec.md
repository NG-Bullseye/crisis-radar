# Scoring Specification

This is the **exact, machine-translatable** version of the scoring framework. Prose in the original brief becomes typed rules here. The runtime source of truth is [`../config/scoring.example.yaml`](../config/scoring.example.yaml); this document explains and justifies it. If the two ever disagree, the YAML wins and this doc is the bug.

## 1. Rule types

Every indicator maps its raw value to points through exactly one rule type:

| Type | Shape | Example |
|---|---|---|
| `band` | numeric value → tiers (`> hi → a`, `< lo → b`, else `0`) | TTF gas `> 50 → +20`, `< 30 → -20` |
| `count` | integer count × `points_each`, capped | production outages: `+15` each, cap `+45` |
| `enum` | categorical key → points | Iran escalation `{low: -20, medium: +10, high: +40}` |
| `bool` | `true → points`, `false → 0` (or a `false` value) | Hormuz insurance rising `+12` |

Two hard backstops apply after the rules:

- **Per-cluster clamp:** each cluster score is clamped to `[-100, +100]` *after* summing its rules.
- **Caps on `count` rules:** unbounded counts (e.g. "each announcement +5") get an explicit cap so one cluster cannot be dominated by a single noisy day. Caps are tunable; the clamp is the final guarantee.

## 2. Cluster 1 — AI-fund health

| Indicator key | Type | Rule | Cap |
|---|---|---|---|
| `product_announcements` | count | `+5` each (major launches: OpenAI, Google, Meta, Nvidia, …) | `+40` |
| `ai_startup_funding_weekly_busd` | band | `> 10 → +10`, `< 5 → -10`, else `0` | — |
| `rate_hike_signals` | count | `-15` each ECB/Fed hike-leaning signal | `-45` |
| `tech_performance_5d_pct` | band | `> +2 → +10`, `< -2 → -10`, else `0` | — |
| `negative_ai_news` | count | `-8` each (regulation, privacy scandal, major outage) | `-40` |

**Cluster 1 score** = clamp(Σ of the above, -100, +100).

> Original formula: `(announcements × 5) + funding + rate + performance + negative_news`. Encoded faithfully; `product_announcements` is a *count* whose `points_each` is `5`, which is the same arithmetic.

## 3. Cluster 2 — Fertilizer-crisis indicators

| Indicator key | Type | Rule | Cap |
|---|---|---|---|
| `gas_ttf_eur_mwh` | band | `> 50 → +20`, `< 30 → -20`, else `0` | — |
| `production_outages` | count | `+15` each plant offline / curtailed | `+45` |
| `hormuz_status` | enum | `{blocked: +30, open: -30}` | — |
| `harvest_forecast` | enum | `{reduction_warning: +10, neutral: 0, favorable: -5}` | — |
| `fertilizer_import_costs` | count | `+12` each shortage/cost-spike report | `+36` |
| `iran_conflict_escalation` | enum | `{low: -20, medium: +10, high: +40}` | — |

**Cluster 2 score** = clamp(Σ, -100, +100).

> `hormuz_status` is the renamed *"Hornmus"* indicator (see [architecture.md §13](architecture.md#13-normalization-note--hornmus--strait-of-hormuz)). `harvest_forecast` adds a mild `favorable: -5` tier so a good harvest can *relieve* the crisis score, not just be neutral — a small extension of the original (which only specified the warning case). Set it to `0` in config to match the brief exactly.

## 4. Cluster 3 — Oil proxy

| Indicator key | Type | Rule | Cap |
|---|---|---|---|
| `wti_usd_bbl` | band | `> 90 → +25`, `< 60 → -25`, else `0` | — |
| `mideast_tension` | enum | `{high: +15, medium: 0, low: 0}` | — |
| `refinery_outages` | count | `+10` each outage | `+30` |
| `hormuz_insurance_rising` | bool | `true → +12`, `false → 0` | — |

**Cluster 3 score** = clamp(Σ, -100, +100).

## 5. Total & interpretation

```
total = mean(cluster1, cluster2, cluster3)          # each already clamped to [-100, +100]
```

| Total band | Recommendation | Risk level |
|---|---|---|
| `> +30` | Crisis scenario more likely — **consider rotation** | elevated |
| `0 … +30` | Heightened caution — consider a half position in fertilizer/commodities | medium |
| `-30 … 0` | Neutral — keep observing | low |
| `< -30` | AI-fund tailwind — **rotation not needed** | low |

Bands are half-open and evaluated top-down: `total > 30` first, else `total >= 0`, else `total >= -30`, else below.

## 6. The rotation signal (the actual product)

A single day above `+30` is **not** an action. The brief is explicit: *"if the total climbs above +30 for two-to-three weeks in a row, that is your signal to rotate."*

The `SignalDetector` therefore evaluates **sustained pressure** over history:

```
signal.rotation.active  ⟺  total > rotation.threshold  for ≥ rotation.consecutive_days
                              consecutive (most recent) stored report days
```

Defaults: `threshold = +30`, `consecutive_days = 15` (≈ 3 trading weeks). The detector reports `{active, streak_days, since_date}` so a *building* streak (e.g. 9/15) is visible before it fires. See [`data-model.md` § Signal](data-model.md#signal).

## 7. Correlation note (read before trusting the total)

`iran_conflict_escalation`, `hormuz_status`, `mideast_tension`, and `hormuz_insurance_rising` are **not independent**: a Hormuz/Iran flare-up pushes the fertilizer cluster (gas feedstock) *and* the oil cluster *and* indirectly gas prices. The mean-of-three total therefore amplifies a single geopolitical shock across multiple clusters.

This is **by design** in the source framework — oil is meant as a *confirmation proxy*, so deliberate overlap is acceptable. But the implementer must keep it explicit and, when tuning, consider:

- adding per-cluster **weights** to the total (config already reserves a `weights` block), or
- treating cluster 3 as a *gate/confirmation* on cluster 2 rather than an equal third of the mean.

Do not "fix" this silently — it is a modeling choice for Leo to make, not a bug to patch.

## 8. Worked example

Indicators (one day):

- C1: announcements `2`, funding `12 B$`, rate signals `1`, tech 5d `+3.1%`, negative news `1`
  → `+10` + `+10` + `-15` + `+10` + `-8` = **+7**
- C2: gas `58 €/MWh`, outages `1`, hormuz `open`, harvest `reduction_warning`, import reports `2`, iran `medium`
  → `+20` + `+15` + `-30` + `+10` + `+24` + `+10` = **+49**
- C3: WTI `94`, tension `high`, refinery outages `0`, insurance `rising`
  → `+25` + `+15` + `0` + `+12` = **+52**

`total = mean(7, 49, 52) = 36.0` → **> +30 → consider rotation, risk elevated.** One day only — the rotation *signal* would still need ~15 such days in a row.
