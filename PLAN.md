# FactorioArena — Project Plan

*Repo: `factorio-arena`. Headline for the writeup: "The factory must learn."*

---

## 1. Pitch

Existing Factorio agent work (the Factorio Learning Environment, FLE) hands the model a Python API with helpers that route belts and place entities for it. That measures *planning over an API*, not *play*. This project gives an LLM agent the same tasks as FLE's lab-play ("make 16 iron gears", "automate iron plates") but exactly a human's action vocabulary: walk, mine, place, rotate, insert, take, craft, wait, with real reach limits, walking speed, mining and crafting times enforced by a thin Lua mod running inside a headless Factorio server. Success is binary and scored by game-time used against a scripted par. It ships as a `verifiers` environment with a leaderboard of frontier models, an ablation that quantifies how much the API was doing for them, and an RL fine-tune of a small open model that visibly learns to play.

Every other Factorio AI gets an API. This one has to walk over and mine the ore.

---

## 2. What we are actually building

### 2.1 What "RL environment" means here

In the current industry sense, an RL environment for LLMs is three things:

1. **A dataset of task inputs.** Each row is a task: a prompt, a starting world state, a success condition.
2. **A harness.** The code that turns the model's text into actions in some sandbox, and turns the sandbox state back into text the model reads. Tools, context management, turn limits.
3. **A reward function.** A program that looks at what happened and emits a number. No human in the loop.

That's the whole product. The game is just the sandbox. Labs are bottlenecked on tasks where success is *automatically verifiable*, because that's what makes RL possible: you can run the model thousands of times and get a trustworthy score each time without paying a person to check.

The same package serves three uses:

- **Evaluation**: run any model through it, report success rate. A benchmark.
- **Training**: use the reward as a learning signal to make a model better at the task.
- **Data generation**: keep the successful trajectories as supervised data.

A good environment is therefore judged on the quality of its *tasks* and *reward*, not on how impressive the game plumbing is. Plumbing is the price of entry.

### 2.2 How training uses the environment (GRPO in one paragraph)

The training loop you'll run (GRPO or a close relative, via `prime-rl`) works like this. Take one task. Sample the model on it *G* times (say 8) with temperature, producing 8 full episodes. Score each with the reward function. Within the group, compute each episode's advantage: how much better or worse it scored than the group average. Then nudge the model's weights so the tokens it produced in above-average episodes become more likely, and tokens in below-average episodes less likely. Repeat across many tasks.

Three consequences for environment design fall out of this:

- **Reward needs variance within a group.** If all 8 episodes fail (reward 0) or all succeed with the same score, there is no gradient. Tasks must sit in a band where the current model sometimes succeeds and sometimes fails. This is why a *curriculum* (section 7) is not optional.
- **Every token the model reads costs money twice.** Once at inference during rollouts, once at training. Observation size is your budget line.
- **The reward is the spec.** Whatever is cheapest to score highly, the model will find. Reward hacking (section 5.4) is not a hypothetical.

### 2.3 Why "hands only" is the distinct contribution

FLE's agent writes Python programs against an API that includes helpers like "connect these two entities with belts" and, as far as I know, has no human-speed character constraints (reach, walking, mining time). When FLE reports that frontier models lack spatial reasoning, it's measuring that over an API that already does much of the spatial work.

Changing the *interface* while keeping the *tasks* identical creates a clean experiment. Same task, two interfaces, one model: the gap between the two scores is the amount of work the API was doing for the model. That gap is the thesis of this project, and it fits in one table.

Three interface levels exist. This project commits to the middle one:

| Level | What the model does | Verdict |
|---|---|---|
| High-level API (FLE) | Writes programs; helpers route, place, path-find | The thing we're contrasting against |
| **Human primitives, text observation** | One verb per human action; sees a structured description of nearby world | **This project** |
| Pixels in, mouse/keyboard out | True human parity, vision model, real client | Stretch goal; too slow and expensive for RL on a small model |

The action space is human-shaped either way, so the pixel mode can be added later as a second *observation* mode on the same environment without redesigning anything.

---

## 3. System architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Trainer / Evaluator  (prime-rl or vf-eval)                      │
│  - samples model, collects episodes, computes rewards            │
└───────────────┬──────────────────────────────────────────────────┘
                │ OpenAI-compatible model endpoint (OpenRouter / vLLM)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  verifiers v1 Taskset + Env.run  (Python package: `factorio_arena`)│
│  - loads task YAML, builds system prompt                          │
│  - parses model output → action batch                            │
│  - calls game client, formats observation                         │
│  - computes reward at episode end                                 │
└───────────────┬──────────────────────────────────────────────────┘
                │ Python client: reset(task), step(actions) → obs
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Game client  (RCON over TCP)                                     │
│  - sends `/sc remote.call("hands", "step", <json>)`               │
│  - receives JSON observation string                               │
└───────────────┬──────────────────────────────────────────────────┘
                │ one RCON connection per server
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Headless Factorio server, N copies in Docker                     │
│  - runs scenario "lab" with mod "hands"                           │
│  - game.speed cranked; world is frozen between steps              │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │  Lua mod "hands"                                          │     │
│  │  - owns one script-controlled character entity            │     │
│  │  - implements the primitives, enforces human constraints  │     │
│  │  - advances ticks for actions that take time              │     │
│  │  - serializes observation to JSON                         │     │
│  └──────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

**Key design facts**

- **RCON** is Factorio's remote console: a TCP protocol where you send console commands and get text back. `/sc` (silent command) runs arbitrary Lua. The Lua mod exposes a `remote` interface so the Python side calls named functions rather than injecting raw Lua each step.
- **Headless** means no renderer, no window. It runs on a cheap CPU box, dozens of copies on one machine.
- **The character** is a `character` entity controlled by script, not by a connected player. The engine's `LuaControl` interface (shared by players and characters) exposes `walking_state`, `mining_state`, `begin_crafting`, `can_reach_entity`, inventories. This is the fact the whole project rests on; verify it first (section 6, milestone 0). Evidence so far (see `REUSE.md` §4.4): walking on an unattached character is confirmed by forum posts and by the BotBridge mod; mining and crafting are documented but not yet confirmed empirically. If `mining_state` fails, the fallback is `LuaEntity.mine` with a tick cost computed from the prototype's mining time, which keeps the semantics but loses engine-enforced timing.
- **Framework-free game client.** The Python client (`reset`, `step`) knows nothing about `verifiers`. The `verifiers` adapter is a thin layer over it, so swapping trainers (prime-rl, or TRL as a single-GPU fallback) touches only the adapter.
- **Versions.** Factorio `2.0.77` (current stable; the `factoriotools/factorio` image) and Python 3.12 (`verifiers` excludes 3.14; `prime-rl` wants 3.12). Factorio 2.x renames that bite mod code: `storage` replaces `global`, directions are 16-way (N/E/S/W = 0/4/8/12), `helpers.table_to_json` replaces `game.table_to_json`.
- **Time control** uses `game.tick_paused = true` to freeze the world and `game.ticks_to_run = N` to advance exactly N ticks; RCON commands still execute while paused. One `ticks_to_run` call per action, since stepping granularity can change results.
- **Determinism.** Factorio is fully deterministic given a map seed and an input sequence. An episode is reproducible from `(task, seed, action_list)`. This gives you free replays, free debugging, and free footage: feed the action list to a real client later and record it.
- **The dev Mac is emulation-only.** There is no arm64 Factorio binary; the server runs under box64 or Rosetta on Apple Silicon. Throughput and cost numbers must come from an x86 Linux box.

---

## 4. Time model

This is the subtlest design decision and worth understanding before writing code.

A human plays Factorio in real time: the world keeps ticking while you think. An LLM takes seconds to minutes per decision, so real time would make the agent's thinking speed the dominant factor and make results non-reproducible.

The environment is therefore **turn-based with a game clock**:

- Between the model's turns, the world is frozen (`game.tick_paused`; see section 3).
- Each action has a *tick cost*: walking 10 tiles costs the ticks the character needs to walk them; mining an ore tile costs its mining time; placing is instant; `wait(n)` costs exactly `n`.
- When an action executes, the mod advances the world by that many ticks. Everything else in the world (furnaces smelting, drills mining, belts moving) runs during those ticks.
- The episode has a **tick budget** (game time) and a **turn budget** (model calls). They are different resources. A model that waits efficiently spends few turns but many ticks; a model that checks the furnace every 10 ticks spends many turns.

The score is based on **ticks used**, not turns, because ticks are what a human would be judged on. Turns are capped only to bound cost.

A human's reaction time and thinking are not modeled. This is a deliberate relaxation; the writeup should say so plainly.

---

## 5. Environment spec

### 5.1 Observation

Text JSON, budget ~1,000–1,500 tokens. Every field earns its place; token count is the single biggest cost driver in RL training.

```json
{
  "task": "Have 16 iron-gear-wheel in your inventory.",
  "budget": {"ticks_left": 14200, "turns_left": 38},
  "character": {"pos": [0, 0], "reach": 10},
  "inventory": {"iron-ore": 12, "stone": 5, "wood": 2},
  "crafting_queue": [{"recipe": "stone-furnace", "count": 1, "ticks_left": 18}],
  "entities": [
    {"type": "stone-furnace", "pos": [3, -2], "dir": "N",
     "fuel": {"wood": 1}, "input": {"iron-ore": 4}, "output": {"iron-plate": 2},
     "status": "working"},
    {"type": "burner-mining-drill", "pos": [8, 1], "dir": "E",
     "fuel": {}, "status": "no_fuel"}
  ],
  "resources": [
    {"type": "iron-ore", "nearest": [6, 4], "dist": 7.2, "approx_tiles": 400},
    {"type": "stone",    "nearest": [-9, 2], "dist": 9.2, "approx_tiles": 150},
    {"type": "coal",     "nearest": [14, -8], "dist": 16.1, "approx_tiles": 300}
  ],
  "last_action": {"action": "place", "ok": false, "error": "out_of_reach",
                  "detail": "target at distance 12.3, reach is 10"}
}
```

Design rules:

- **Local, not global.** Entities within reach plus a small margin, capped at N nearest. The model should have to walk to find out what's over there, like a human.
- **Resources are summarized**, not enumerated: nearest tile per ore type and a rough patch size. Enumerating ore tiles would cost thousands of tokens and tell the model nothing a human sees at a glance.
- **Positions are relative to the character.** Humans reason in "three tiles to my right", not world coordinates. Absolute positions can be added if relative ones measurably hurt.
- **Errors are precise.** `out_of_reach` with the distance, `no_item: stone` with what's in inventory, `blocked_by: stone-furnace at [3,-2]`. In this environment the error string is the primary learning signal for spatial mistakes. Vague errors make the task unlearnable.
- **Entity status comes from the engine.** `LuaEntity.status` yields a `defines.entity_status` value; keep `working`, `no_fuel`, `no_ingredients`, `full_output`, `no_minable_resources`, `waiting_for_source_items`, `waiting_for_space_in_destination`, `no_power`, and collapse the rest to `normal`. It's what a human sees as the icon over the machine. Chests and belts have no status; the field is simply absent for them.
- **Optional ASCII minimap.** Build it, A/B it. Keep it only if it moves success rate more than it costs in tokens.

### 5.2 Action space

The model emits one JSON object per turn: a list of up to ~5 primitives, executed in order, stopping at the first failure. Batching cuts turns (and cost) without doing any spatial reasoning for the model; the model still has to say *where* and *what*.

| Verb | Args | Human equivalent | Tick cost | Enforced constraints |
|---|---|---|---|---|
| `walk` | `dx, dy` | holding WASD | distance / walk speed | straight line, max ~10 tiles, stops on collision; **no pathfinding** |
| `mine` | `x, y` | right-click hold | engine mining time | in reach; resource or minable entity present |
| `place` | `item, x, y, dir` | left-click with item in hand | 0 | in reach; item in inventory; engine `can_place_entity` |
| `rotate` | `x, y` | R key | 0 | in reach; `rotatable` |
| `set_recipe` | `x, y, recipe` | open assembler, pick recipe | 0 | in reach; valid recipe for that machine |
| `insert` | `x, y, item, n` | ctrl-click into machine | 0 | in reach; item in inventory; target inventory accepts item |
| `take` | `x, y, item, n` | ctrl-click out of machine | 0 | in reach; item present |
| `craft` | `recipe, n` | handcraft from inventory | queued; crafts complete over ticks | ingredients present; recipe handcraftable |
| `wait` | `ticks` | standing still | `ticks` | capped per call |

Engine details the mod must respect (verified against the 2.1 API; see `REUSE.md` §4.4):

- **Walking.** Collisions raise no event, so the mod detects a stall by position delta each tick. An unattached character keeps walking until `walking_state` is cleared explicitly.
- **Mining.** Select the target with `update_selected_entity`, then set `mining_state` each tick until the engine reports the mine complete.
- **Placing.** `create_entity` has no build check in 2.x. Check with `can_place_entity{build_check_type = manual}` first, then create, then remove the item from inventory.
- **Inventories.** `insert` and `take` address machine inventories by the 2.x defines `crafter_input`, `crafter_output`, `fuel`, `burnt_result`, and `chest`. The 1.x names (`furnace_source` and friends) no longer exist. `get_insertable_count` gives the exact capacity for "inserted N of M" errors.
- **Reach and speed** come from the base character prototype: reach 10, build distance 10, resource reach 2.7, running speed 0.15 tiles per tick. Confirm these return real values on an unattached character in milestone 0.

What is deliberately **absent**: `walk_to(x, y)` with pathfinding, `connect(a, b)`, `build_blueprint`, teleport, "find nearest X". Each of these is spatial reasoning the model would otherwise have to do itself. The pushback rule for the whole project: when models struggle, **do not add helpers**. If they can't walk around a rock, that's a finding, not a bug.

### 5.3 Tasks

A task is a YAML file, so tasks are data and the task set can grow without code changes. A Pydantic model validates each file at load time and exports a JSON Schema for editor validation. The task set stays finite with unique ids, because the curriculum sampler (section 7.2) tracks per-task reward.

```yaml
id: gears-16-empty
description: "Have 16 iron-gear-wheel in your inventory."
target: {item: iron-gear-wheel, count: 16}
delivery: inventory            # or: {chest_at: [x, y]}
start_inventory: {}            # empty-handed
map: {scenario: lab-v1, seed: 7}   # ore patches at seeded offsets
budget: {ticks: 36000, turns: 60}  # 36000 ticks = 10 game-minutes
par_ticks: 9800                # from the scripted solver
tags: [smelting, handcraft, tier-1]
```

**The lab map** is a scenario whose surface is built in Lua (all autoplace off, lab tiles, frozen daytime, ore patches placed at seeded offsets), so `reset` rebuilds the surface in place rather than restarting a container.

**The task ladder** reuses FLE's lab-play targets so the comparison is direct. One caveat for the writeup: FLE lab-play scores throughput per minute, while this ladder scores "have N items by episode end". The targets match; the metric does not. Either say so plainly or add a throughput variant. Roughly, in increasing difficulty:

1. Mine 10 iron ore (walk, mine)
2. Craft 5 gears from 10 plates in inventory (craft only)
3. Smelt 10 plates with a furnace and fuel given (place, insert, wait, take)
4. **Make 16 gears empty-handed** (the canonical task: mine ore + stone + wood, craft furnace, place, fuel, feed, wait, take, craft)
5. Place and fuel a burner drill on iron ore; collect 20 ore from it
6. Burner drill → furnace: automate plates, collect 30
7. Two drills, two furnaces, a belt and an inserter
8. Electronic circuits (two input chains, copper cable intermediate)
9. … up to small automated science

**Starting inventory is a difficulty dial.** The same target with a full starter kit is a different task from the same target empty-handed. Generate variants: `gears-16-kit`, `gears-16-ore-only`, `gears-16-empty`. This gives the curriculum fine-grained rungs for free.

**Why these are long-horizon.** "16 gears empty-handed" is roughly 40–80 primitive actions for a competent human-speed play: you need 32 iron plates, which needs 32 ore mined by hand (several seconds each), 5 stone for a furnace, fuel, and then crafting. A 4–8B model holding this plan across 40 turns with a 1.5k-token observation each turn is a real test of long-horizon reasoning. That is the point.

### 5.4 Reward

Per episode, computed at termination:

```
fail:     R = 0
success:  R = 0.5 + 0.5 * clip(par_ticks / ticks_used, 0, 1)
```

So a success is worth at least 0.5, and matching par is worth 1.0. Beating par caps at 1.0 (otherwise the model is rewarded for exploiting solver weaknesses rather than for playing well).

**Why binary success, not partial credit.** Partial credit ("you smelted some plates, here's 0.3") is tempting because it gives gradient on tasks the model can't finish. It also teaches the model to *collect partial credit* rather than finish. The honest fix for "no gradient on hard tasks" is the curriculum: give the model an easier task it *can* finish, not a consolation prize on the hard one.

**Monitor metrics are not reward.** Log everything (ore mined, furnace placed, plates smelted, invalid-action count, ticks spent walking vs waiting) as diagnostics. They tell you *why* a task is failing and make excellent writeup material. They never enter the number the trainer sees. Failure-taxonomy labels (section 6, milestone 4) are also metrics, attached with `@vf.metric`; `vf-replay` can re-score saved traces offline without a game server, so labels can be refined after the fact.

**Reward-hack audit, before any training run.** Ask: what is the cheapest way to make the success condition true?

- Target items must not exist anywhere in the starting world (no pre-placed chests with gears).
- Delivery is checked at episode end, not on first sight (prevents "have 16 then drop 15").
- The scripted solver's par must be validated against a known-good human play so par isn't trivially beatable.
- Any `error` path in the mod must be a real failure, never a silent success.
- Watch the invalid-action rate during training: a sudden drop in invalid actions with no rise in success usually means the model found a degenerate loop (e.g., `wait` until budget runs out costs nothing and never errors).

### 5.5 Termination

An episode ends on the first of:

- **Success**: delivery condition true at check time.
- **Tick budget exhausted**: game time ran out. Reward 0.
- **Turn budget exhausted**: model used all its calls. Reward 0.
- **Malformed output** for K consecutive turns: the model stopped producing parseable actions. Reward 0. (Single malformed turns get an error observation and continue.)
- **Character dead**: shouldn't happen with biters off; handle it anyway.

---

## 6. Milestones

No timeline. Each milestone ends with something demonstrable, and the order is chosen so the riskiest unknown is retired first.

### Milestone 0 — Retire the existential risk

Before anything else: **confirm that a script-controlled `character` entity can walk, mine, and craft with no client connected.** If this works, the rest of the design stands. If mining fails, use the `LuaEntity.mine` fallback (section 3); if walking fails, the design changes (a connected bot client, which is much heavier), and it's better to know now than after writing the mod.

Checklist:

- [x] Headless server starts in Docker on the Mac (box64 or Rosetta) with `auto_pause: false`; RCON hello-world from Python. (2026-10-14: `make server`, hand-written `rcon.py`, `make test-server`.)
- [x] Unattached character walks, stops when told, and stalls on collision. (2026-10-14: `scripts/probe_walk.py`. Walking persists across ticks from one `walking_state` call; no per-tick re-assertion needed.)
- [x] Unattached character mines via `mining_state` (or the fallback). (2026-10-14: `scripts/probe_mine.py`. `mining_state` does nothing on an unattached character, even re-asserted every tick; use `LuaEntity.mine` and charge `mining_time / mining_speed` ticks in the mod. The fallback ignores reach, so the mod checks `can_reach_entity` itself.)
- [x] Unattached character crafts via `begin_crafting`; `crafting_queue` advances with ticks. (2026-10-14: `scripts/probe_craft.py`. Engine-driven, unlike mining: 3 gears appear on schedule, ingredients are consumed up front, and a craft without ingredients queues 0.)
- [x] Reach attributes return real values on the unattached character. (2026-10-14: `scripts/probe_ticks.py`. reach 10, build 10, resource reach 2.7, item pickup 1, drop 10.)
- [x] `tick_paused` + `ticks_to_run` step the world exactly N ticks. (2026-10-14: `scripts/probe_ticks.py`. Frozen clock holds; +60 is exactly +60 and re-pauses; walking moves only during the step. `ticks_to_run` runs at normal speed in the background, so the client must poll `game.tick` to know the step finished.)
- [x] An observation over 8 KB round-trips over RCON intact. (2026-10-14: 9000-byte reply, single packet, hand-written client.)
- [ ] `factorio --dump-data` produces a versioned `game_data.json` (recipes, mining times, crafting speeds, character fields); commit it. (2026-10-14: raw dump works via `make dump-data` (13 MB, base game only, gitignored). Still to do: a Python script that extracts the subset into a small committed `game_data.json` tagged with the game version. Note `energy_required` is absent from recipes that use the 0.5 s default, so the extractor must apply defaults.)
- [ ] Ticks per second at cranked `game.speed`, servers per core, and a determinism checksum of the same `(seed, action_list)` on the Mac versus an x86 box. These numbers drive the cost model later.

### Milestone 1 — The "hands" mod

The Lua mod implementing the primitives in section 5.2, a `remote` interface (`reset`, `step`, `observe`), human-constraint enforcement, tick advancement, and JSON observation serialization. A Python client that wraps RCON with `reset(task) → obs` and `step(actions) → obs`.

Lua unit tests run inside the headless server with FactorioTest. The Python client writes one JSONL line per step (`tick`, `action`, `result`, `observation`); because the game is deterministic, that file is the replay and the main debugging tool until a renderer exists.

Exit criteria: every primitive has a test that exercises its success path and each of its error paths; error strings are precise; observations are deterministic across runs with the same seed and actions.

### Milestone 2 — Scripted solvers

For every task in the ladder, a hand-written Python policy that solves it through the same client (no shortcuts through the mod). These are three things at once: the integration test suite, the generator of `par_ticks`, and the ceiling baseline. Writing them is also how you discover which primitives are missing or awkward, before a model ever sees them.

The API-interface helpers for the ablation (section 7.1) are built here too, and are mostly borrowed: the engine's `request_path` for `walk_to`, `find_entities_filtered` for `find_nearest`, and FLE's `connect_entities` Lua for belt routing. The hands-only solvers get no such help.

### Milestone 3 — Task system and packaging

YAML task loader, the full ladder with inventory variants, the `verifiers` v1 adapter (a `Taskset` that loads the YAML, and an `Env.run` loop that handles system prompt, action parsing, observation formatting, and reward), and docker-compose for N parallel servers. Scaffold with `vf-init`, install editable; use the built-in `null` harness and the `subprocess` runtime. Measure throughput: episodes per hour per server, tokens per episode. The goal is for the *model*, not the game, to be the bottleneck.

Exit criteria: one `vf-eval` command runs the whole ladder against an API model end-to-end and writes `traces.jsonl`.

### Milestone 4 — Evaluation and the first post

Run frontier models (via API) and a few open models through the ladder. Report success rate, time score, pass@k, cost per task. Build the **failure taxonomy**: categorize every failed episode by root cause (out-of-reach placement, forgot fuel, walked into an obstacle and never recovered, lost track of inventory, gave up and waited).

Run the **interface ablation** (section 7.1). Publish v0.1 and the first writeup. This is the first thing worth posting.

### Milestone 5 — RL fine-tune

Train a ~4–8B open model with `prime-rl` on rented GPUs, using the curriculum in section 7.2, which is a `prime-rl` sampler config rather than code. Rough sizing from `prime-rl`'s shipped examples: a 4B LoRA run needs 2 to 4 H100s once sequence length is set for 40-turn episodes; an 8B full fine-tune needs about 8. Measure before trusting this. Track success per rung, the reward curve, invalid-action rate, and tokens per episode. Re-run the reward-hack audit on the trained model's trajectories; a model that improved suspiciously fast has usually found something.

Deliverables: the before/after table on the full ladder, the reward curve, one before/after replay pair, and the cost (GPU-hours, episodes, dollars). Second writeup.

### Milestone 6 — Stretch, in order of value

1. **Replay renderer**: feed an episode's action list to a real Factorio client and record it. This is where the footage comes from.
2. **Publish to the Environments Hub** so others can eval and train on it. Hub packages are not auto-installed since `verifiers` 0.3.1; users install first, then run.
3. **Rendered-image observation mode** for vision-language models: same actions, screenshot instead of JSON.
4. **Pixels + mouse/keyboard mode**: true human parity. A separate project in cost and effort, but the action-space design makes it a mode, not a rewrite.

---

## 7. Experiments

### 7.1 Baselines

| Baseline | Role |
|---|---|
| Random valid-action policy | The floor. Also a reward-hack detector: if random scores above 0 on anything, the task is broken. |
| Scripted solver per task | The ceiling and the source of `par_ticks`. |
| Frontier LLMs, hands interface | The headline leaderboard. Every model goes through OpenRouter's single OpenAI-compatible endpoint, which reports cost per response, so cost per episode comes straight from the traces. vLLM serves only our own checkpoints. |
| Same LLMs, **API interface** | Expose FLE-style helpers (`walk_to` with pathfinding, `connect_belts`, `find_nearest`) as extra tools on the *same* tasks. The gap between this row and the one above is the thesis. |
| Small open model, before vs after RL | The proof that the environment is a usable training signal. |
| You, through the text interface, and through the normal client | A human number on the board. Cheap, fun, and it calibrates how hard the text interface itself is. The text version is a small terminal loop over the Python client that writes the same trace format as the models. |

### 7.2 Curriculum

GRPO needs within-group variance (section 2.2). Keep each task the model trains on in roughly the 20–80% success band:

- Start with rungs the base model already solves sometimes.
- Promote a rung out of the training mix when success exceeds ~80%; it has nothing left to teach.
- Introduce the next rung when its success rises above ~20%; below that, groups are almost all zeros.
- Inventory variants are the fine adjustment: `-kit` → `-ore-only` → `-empty` moves a task up the ladder without changing its target.
- Always keep a held-out eval set (fixed seeds, never trained on) so the reported numbers are honest.

`prime-rl`'s difficulty-pool sampler implements this: it tracks each task's latest mean group reward and assigns tasks to named pools with a threshold and a sampling weight. The thresholds are on *reward*, not success rate. Under the reward in section 5.4 a success scores above 0.5, so the 20–80% success band maps to mean-reward thresholds of roughly 0.1 and 0.6. Calibrate once on real runs.

### 7.3 Cost model (fill in with measured numbers)

Rough shape, to be replaced with real measurements from milestone 3:

- Observation ~1.2k tokens × ~40 turns ≈ 50k input tokens per episode, plus the model's output. That means a 32k-plus sequence length per episode at training time, which drives GPU count more than model size does.
- G=8 episodes per task × T tasks per training step.
- Game side: N headless servers per CPU box, each running many times faster than real time; usually not the bottleneck.
- The lever that matters most is observation size. A 30% cut in observation tokens is a 30% cut in the whole bill.

---

## 8. What the writeup should make visible

The audience is tech Twitter and people who hire. The goal is that someone skimming for 60 seconds understands the idea, and someone reading for 10 minutes sees that you understand environments, not just Factorio.

- **The thesis in one sentence and one table.** Hands vs API, same tasks, same models.
- **Why the interface is honest.** Which human constraints are enforced (reach, walking, mining and crafting time, no pathfinding, local observation), which are relaxed (turn-based time, batched primitives, text not pixels), and why each relaxation doesn't leak spatial reasoning to the model.
- **Reward design reasoning.** Why binary + time score, why no partial credit in the reward, the reward hack the audit caught, what the monitor metrics revealed about *why* models fail.
- **The failure taxonomy.** Concrete, quotable, often funny: the model that placed a furnace out of reach eleven times, the one that forgot fuel exists.
- **The RL story.** Curriculum decisions, the reward curve, one before/after replay pair, and the bill.
- **Throughput engineering.** Episodes per hour, tokens per episode, what observation compression traded against success rate.
- **Honest limitations and reproducibility.** What's still not human play. One command to run the evals.
- **Twitter assets.** A 20-second replay clip, the ablation table, the reward curve, and the line: every other Factorio AI gets an API; this one has to walk over and mine the ore.

---

## 9. Glossary

- **Episode / rollout**: one full attempt at one task, from `reset` to termination.
- **Observation**: what the model reads each turn.
- **Action / primitive**: one verb from section 5.2.
- **Turn**: one model call; may contain a batch of primitives.
- **Tick**: Factorio's simulation unit, 60 per second of game time.
- **Reward**: the single number per episode the trainer optimizes.
- **Monitor metric**: a number logged for diagnosis, never optimized.
- **GRPO**: group-relative policy optimization; the RL algorithm that compares episodes within a sampled group rather than against a learned value function.
- **Par**: the tick count a scripted solver needs; the reference for the time score.
- **pass@k**: probability that at least one of k sampled attempts succeeds.
- **RCON**: Factorio's remote console protocol; how Python talks to the server.
- **Headless**: a server with no renderer; what training runs on.
- **`verifiers`**: the Python library that defines the environment interface the trainer and evaluator expect. Its v1 vocabulary: a **Taskset** loads **Tasks**; an **Env** runs the turn loop; a **harness** is the agent's chat loop; a **runtime** is where the harness executes; a **trace** is the saved record of one episode.
- **`prime-rl`**: the trainer that samples from a `verifiers` environment and runs GRPO.
