# REUSE.md — Open-source code, tools, and data to build on

Research snapshot: 2026-10-06. Versions and links were verified on that date; re-check before pinning anything.

**How to read this.** Each section covers one part of the system from `PLAN.md`. For every item: what it is, license, version, what we take from it, what we leave, and anything unconfirmed. "Reuse" means copy or depend on; "read" means study it for engine semantics but write our own code; "skip" means we looked and it does not help.

Licensing rule: this repo is intended to be published. Only copy code from MIT, BSD, or Apache-2.0 sources. GPL and AGPL sources are read-only. Game assets are never committed.

---

## 1. Headless server and containers (PLAN §3, Milestone 0)

| Item | License | Version | Verdict |
|---|---|---|---|
| [factoriotools/factorio-docker](https://github.com/factoriotools/factorio-docker) | MIT | `stable` = 2.0.77, `latest` = 2.1.21 | **Reuse.** Pin `factoriotools/factorio:2.0.77`. |
| Factorio headless binary | Proprietary, free download, no account | 2.0.77 | **Reuse** via the image. Linux x86-64 only. |
| [FLE `fle/cluster/run_envs.py`](https://github.com/JackHopkins/factorio-learning-environment/blob/main/fle/cluster/run_envs.py) | MIT | FLE 0.4.8, Factorio 2.0.73 | **Read** for the compose generator pattern. |

What to take from the image:

- One volume at `/factorio` with `config/`, `mods/`, `saves/`, `scenarios/`. Files are owned by UID 845.
- RCON on TCP 27015. Password lives in `config/rconpw`; write our own from `.env` rather than using the random one.
- Scenarios start with `--start-server-load-scenario <name>`; FLE bypasses the image entrypoint and passes the server flags itself.
- Set `auto_pause: false` in `server-settings.json`. The default pauses the map when no player is connected, and nothing ticks.
- Set `DLC_SPACE_AGE=false` for a base-game lab.
- One container per server, ports offset per instance (FLE uses UDP `34197+i`, RCON `27000+i`). Factorio's update loop is single-threaded, so budget one core per server.

What to take from FLE's compose generator: the loop that stamps out N services with distinct names, volumes, and ports, and its 1 CPU / 1 GB per container limits. Rewrite it; it is small.

Apple Silicon: there is no arm64 Factorio binary. The arm64 image runs the x86 binary under box64 and is labelled experimental. The alternative is `--platform linux/amd64` under Docker Desktop's Rosetta. Both are emulation. Treat the Mac as dev-only; take throughput and cost numbers on an x86 Linux box.

Unconfirmed: whether box64 or Rosetta preserve bit-exact determinism versus native x86. Milestone 0 should diff a checksum of the same `(seed, action list)` across platforms.

CI: the image downloads Factorio at image build time, so a CI job is a ~130 MB `docker pull` from Docker Hub with no factorio.com login. GitHub's ubuntu runners can run the server.

---

## 2. RCON client (PLAN §3)

| Item | License | Version | Verdict |
|---|---|---|---|
| [factorio-rcon-py](https://github.com/mark9064/factorio-rcon-py) | MIT | 2.1.3 (June 2024) | **Reuse.** Sync `RCONClient` and anyio `AsyncRCONClient`. |
| [rcon](https://pypi.org/project/rcon/) (conqp), mcrcon | MIT | 2.4.9 | Skip. Minecraft-oriented, no advantage. |
| FLE `fle/env/instance.py` | MIT | 0.4.8 | **Read** for the `game.speed` / `tick_paused` wrapper pattern. FLE pins factorio-rcon-py 1.2.1. |

Protocol facts:

- `/sc <lua>` runs Lua silently on the server. The only return channel is `rcon.print(text)`, so every step is one command of the form `/sc rcon.print(remote.call("hands", "step", '<json>'))`.
- The library reads a 4-byte length prefix then the full body, so it handles any single-packet size.

Unconfirmed: whether Factorio fragments large responses Source-style. Milestone 0 should round-trip an observation over 8 KB.

---

## 3. Lua mod tooling (Milestone 1)

| Item | License | Version | Verdict |
|---|---|---|---|
| [FMTK](https://github.com/justarandomgeek/vscode-factoriomod-debug) (`factoriomod-debug` on npm) | MIT | 2.1.9 (Aug 2026) | **Reuse** its LuaLS library generator. Debugger is VS Code only. |
| [FactorioTest](https://github.com/GlassBricks/FactorioTest) (`factorio-test` on npm) | MIT | 3.1.0 (active) | **Reuse** for Lua unit tests that run inside the headless server. |
| [factorio-check](https://pypi.org/project/factorio-check/) | check before use | — | Consider for wrapping headless test runs in CI. |
| Testorio, faketorio | — | 2022 / stale | Skip. Predecessors of FactorioTest. |
| [StyLua](https://github.com/JohnnyMorganz/StyLua) | MPL-2.0 | 2.5.2 | **Reuse** as formatter; ships a pre-commit hook. |
| [selene](https://github.com/Kampfkarren/selene) | MPL-2.0 | current | **Reuse** as linter. Needs a ~20-line Factorio std file declaring `game`, `script`, `remote`, `defines`, `storage`. |
| luacheck | MIT | unmaintained since 2018 | Skip. |

Generate the editor typedefs with:

```sh
npx -y factoriomod-debug sumneko-3rd .luals
```

This writes `.luals/factorio/{config.json, plugin.lua, library/}`. Point a repo-root `.luarc.json` at it (Lua 5.2 runtime, `io`/`os`/`coroutine` disabled, `lowercase-global` diagnostic off). Gitignore `.luals/` and add a `make typedefs` target.

Unconfirmed: whether Zed's bundled lua-language-server loads `runtime.plugin` from `.luarc.json`. Verify by hovering `game` in `control.lua`.

Factorio 2.x API changes that matter: `global` became `storage`; `defines.direction` is 16-way (0 = north, clockwise, so N/E/S/W = 0/4/8/12); `game.table_to_json` became `helpers.table_to_json`; `helpers.write_file` replaces `game.write_file`.

---

## 4. Lua mod building blocks (Milestone 1)

### 4.1 Libraries

| Item | License | Version | Verdict |
|---|---|---|---|
| `helpers.table_to_json` / `helpers.json_to_table` | engine builtin | 2.x | **Reuse.** No JSON library needed. |
| [flib](https://github.com/factoriolib/flib) (canonical home is Codeberg) | MIT | 0.17.2 (GitHub mirror at 0.16.4) | **Reuse** `position`, `direction`, `bounding-box`, `table`, `math.clamp`. Skip gui, dictionary, migration. |

JSON gotchas: `nil` fields vanish, so always emit explicit `{}` or `0`; `inf` and `NaN` serialize as invalid JSON; tables must be pure arrays or pure string-keyed maps.

### 4.2 Prior art for each primitive

| Primitive | Source | What to take | What to leave |
|---|---|---|---|
| `walk` | arturh85/factorio-bot `mods/BotBridge/control.lua` (see 4.3); FLE `move_to/server.lua` slow mode | Set `walking_state` toward a target each tick; detect a stall by position delta (collisions raise no event); clear `walking=false` explicitly because an unattached character keeps walking until told to stop | FLE's default fast mode, which teleports; FLE's dependence on a `request_path` handle |
| `mine` | BotBridge | `update_selected_entity(pos)` then `mining_state = {mining=true, position=pos}`, refreshed per tick; reach guard via `can_reach_entity` with fallback to `resource_reach_distance` | FLE `harvest_resource`, which calls `entity.mine{}` and fakes elapsed ticks |
| `place` | FLE `fle/env/mods/utils.lua` `can_place_entity` (~line 104) and `place_entity/server.lua` diagnostics (~lines 401–431) | `surface.can_place_entity{build_check_type=defines.build_check_type.manual, force=...}`, then `create_entity`, then `remove_item`; the error-message construction | Nothing else |
| `rotate` | FLE `rotate_entity/server.lua` | The 2.0 direction comments | The assembler-recreate workaround; we only rotate belts, inserters, drills via `entity.rotate()` |
| `set_recipe` | FLE `set_entity_recipe/server.lua` (47 lines) | All of it: `force.recipes[name]`, `get_recipe()`, `set_recipe(name)` | — |
| `insert` / `take` | FLE `insert_item` / `extract_item` | The per-inventory `can_insert` / `insert` flow | FLE references `defines.inventory.furnace_source` and `assembling_machine_input`, which no longer exist in 2.x (see 4.4) |
| `craft` | FLE `craft_item/server.lua` | `get_missing_ingredients` error construction; `begin_crafting{count, recipe}` | Synthetic tick accounting |
| `wait` | — | Nothing to reuse; `game.ticks_to_run` does it | FLE `sleep` (fakes elapsed ticks) |
| observation | FLE `fle/env/mods/serialize.lua` (1,410 lines) | `entity_status_names` reverse lookup; the burner/fuel sub-serializers | The rest; it is far larger than our observation needs |

### 4.3 Whole-mod prior art

| Item | License | Status | Verdict |
|---|---|---|---|
| [arturh85/factorio-bot](https://github.com/arturh85/factorio-bot) `mods/BotBridge/control.lua` (7,887 lines) | Repo LICENSE is MIT; the mod's `info.json` says GPL3 | Pushed 2026-10-05, Factorio 2.1 | **Read only** until the license conflict is clarified. The closest existing implementation of our model: unattached characters driven by per-tick `walking_state`, stall detection, `mining_state` mining, reach guards. |
| ai-player-v3 (thedemon117) | "MIT" on the portal, no LICENSE file in repo | 0.4.2, Factorio 2.0 | Skip. Moves by `teleport` in 16-tile hops and mines with `mine_entity(target, true)`. Its README says the AI cheats. Only its `can_place_entity` error strings are worth a glance. |
| AI Agent Bridge (bits-orio) | MIT | — | Skip. Read-only chat Q&A, no character control. |
| chat-ai-player | portal says MIT, source link dead | — | Skip. Unverifiable. |
| FLE `data/scripts/create_character.lua` | MIT | — | Confirms `surface.create_entity{name="character"}` spawns a script character. Says nothing about driving it headless. |

### 4.4 Engine facts verified against `runtime-api.json` (2.1.21)

- `LuaEntity.status` returns a `defines.entity_status` value (72 of them). Map `working`, `no_fuel`, `no_ingredients`, `full_output`, `no_minable_resources`, `waiting_for_source_items`, `waiting_for_space_in_destination`, `no_power`; everything else to `normal`. `status` is nil for chests and belts.
- Inventory defines in 2.x are `crafter_input`, `crafter_output`, `crafter_modules`, `fuel`, `burnt_result`, `chest`, `character_main`. **`PLAN.md` §5.2 must drop `furnace_source` / `furnace_fuel` / `furnace_result`.**
- `LuaSurface.create_entity` has no `build_check_type` argument in 2.x. Check with `can_place_entity` first, then create.
- `LuaEntity.rotate{reverse?}` returns a boolean; `rotatable` says whether R would work.
- `LuaInventory.get_insertable_count` gives exact capacity for "inserted N of M" errors.
- `LuaControl.can_reach_entity(entity)` exists on a character entity (`LuaEntity` inherits `LuaControl`) and measures to the collision box.
- Base character prototype values (`wube/factorio-data`, `base/prototypes/entity/entities.lua` ~719–732): `reach_distance` 10, `build_distance` 10, `reach_resource_distance` 2.7, `item_pickup_distance` 1, `running_speed` 0.15 tiles/tick.
- `LuaControl.walking_state`, `mining_state`, `begin_crafting`, `crafting_queue`, `cancel_crafting`, `get_craftable_count` are all present. `mining_state` errors if written with a controller type other than character, god, or editor.
- Time control: `game.tick_paused = true` freezes entity updates; `game.ticks_to_run = N` runs N ticks while paused and re-pauses at zero. RCON `/sc` still executes while paused. `game.speed` is a float with no documented maximum.

Evidence that an unattached character is script-drivable:

- Forum thread [p=573948](https://forums.factorio.com/viewtopic.php?p=573948): walking works with correct speed; the state persists until cleared.
- Forum thread [p=585087](https://forums.factorio.com/viewtopic.php?p=585087): shooting state driven per tick on a dummy character.
- BotBridge does walking and mining this way on 2.1.

Unconfirmed, and therefore still the Milestone 0 gate: `mining_state` and `begin_crafting` on an unattached character, and whether the reach attributes return real values rather than "max uint when not a character". Fallback for mining if it fails: `LuaEntity.mine{inventory=...}` with the tick cost computed from `prototype.mineable_properties.mining_time / character.mining_speed`.

Forum report [p=465432](https://forums.factorio.com/viewtopic.php?p=465432) suggests stepping granularity can change results. Use one `ticks_to_run` call per action.

---

## 5. Deterministic lab map (PLAN §5.3, Milestone 1)

| Item | License | Verdict |
|---|---|---|
| Editor Extensions `scripts/testing-lab.lua` (raiguard) | MIT on the portal; unstated in the archived GitHub mirror | **Reuse** the surface-creation call verbatim. |
| FLE `default_lab_scenario` | MIT | Skip. Vanilla freeplay with the crash site disabled; `map-gen-settings.json` is defaults. |
| Base game `sandbox` scenario | proprietary | Skip. God mode. |

The Editor Extensions recipe: `game.create_surface(name, {default_enable_all_autoplace_controls=false, property_expression_names={cliffiness=0}, autoplace_settings={tile={settings={["out-of-map"]={}}}}, starting_area="none"})`, then `surface.generate_with_lab_tiles = true`, `freeze_daytime = true`, `daytime = 0`. After that, `set_tiles` a grass square and `create_entity{name="iron-ore", position=..., amount=...}` patches at seeded offsets. Owning the layout in Lua lets `reset` rebuild the surface in place instead of restarting the container.

---

## 6. Game data for Python (Milestone 2)

| Item | License | Version | Verdict |
|---|---|---|---|
| `factorio --dump-data` → `script-output/data-raw-dump.json` | engine | matches the pinned image | **Reuse.** Authoritative; includes character and resource prototypes. |
| Kirk McDonald calculator [`data/vanilla-2.0.55.json`](https://github.com/KirkMcDonald/kirkmcdonald.github.io) | Apache-2.0 | 2.0.55 | **Reuse** as a cross-check. Flat JSON with `energy_required`, `mining_time`, `mining_speed`, `crafting_speed`. |
| [factorio-draftsman](https://factorio-draftsman.readthedocs.io/) | MIT | 4.0.1 (2026-10-04) | Only if blueprints become needed. Bundled recipe data lacks resource and character prototypes (unverified). |
| factoriocalc | AGPL-3.0 | 0.3.0 | **Avoid.** |
| FLE `data/recipes/recipes.lua` | MIT | — | Skip. Ingredients only, no times. |

Plan: in Milestone 0, dump data on the exact server image and commit one versioned `game_data.json` with recipes, mining times, crafting speeds, and character fields. Note `energy_required` may be absent in the dump; the engine default is 0.5 s.

```sh
docker run --rm --platform linux/amd64 -v "$PWD/factorio:/factorio" \
  --entrypoint /opt/factorio/bin/x64/factorio factoriotools/factorio:2.0.77 --dump-data
```

Unconfirmed: whether the dump lands in `/factorio/script-output` or `/opt/factorio/script-output` when the image entrypoint is bypassed. Mount both if needed.

Reference docs to keep locally: [`runtime-api.json`](https://lua-api.factorio.com/latest/runtime-api.json) and [`prototype-api.json`](https://lua-api.factorio.com/latest/prototype-api.json) (~2 MB each, machine-readable, greppable). [factorio-docs-mcp](https://github.com/hjfmailbox/factorio-docs-mcp) wraps the same data as an MCP server; the committed JSON plus a short query script is simpler.

---

## 7. Scripted solvers and the API-interface ablation (Milestone 2, PLAN §7.1)

| Item | License | Verdict |
|---|---|---|
| `LuaSurface.request_path` + `on_script_path_request_finished` | engine | **Reuse** for the ablation's `walk_to`. Async, so the tool must wait ticks. FLE `fle/env/tools/admin/request_path/server.lua` is a correct 2.0 example (chunk generation, `collision_mask` format, `prefer_straight_paths`). |
| `LuaSurface.find_entities_filtered{position, radius, type/name}` | engine | **Reuse** for the ablation's `find_nearest`. |
| FLE `connect_entities` (1,694 lines of Lua) | MIT | **Reuse as-is** for the ablation's belt and pipe routing. Do not port. |
| arturh85/factorio-bot `crates/planner` | MIT | **Read.** Goal-to-action planning with `gather` / `fabricate` / `extract` / `connect` methods. |
| [windfisch/factorio-bot](https://github.com/windfisch/factorio-bot) (C++, 2019) | GPL-3.0 | **Read only.** `mine_planning` and `scheduler` designs. |

The hands-only solvers in Milestone 2 must go through the same client as the model, with no pathfinding. Nothing found is importable for that; the planner crates are design references.

---

## 8. Environment framework (Milestone 3)

| Item | License | Version | Verdict |
|---|---|---|---|
| [verifiers](https://github.com/PrimeIntellect-ai/verifiers) | MIT | 0.3.1 (2026-08-24); `requires-python >=3.11,<3.14` | **Reuse**, targeting the v1 API. |
| [prime-rl](https://github.com/PrimeIntellect-ai/prime-rl) | Apache-2.0 | 0.9.0 (2026-08-25), not on PyPI | **Reuse** for training. Python 3.12, NVIDIA only. |
| OpenEnv (meta-pytorch) | BSD-3 | 0.7.0 | Skip for now. verifiers can wrap an OpenEnv-shaped env later. |
| TRL `GRPOTrainer` | Apache-2.0 | 1.14.1 | Fallback for a single-GPU run via `environment_factory`. Its docs discourage a generic `step(action)` tool, which conflicts with our batched-JSON actions. |
| SkyRL 0.4.0, ART 0.5.19, Atropos 0.4.0 | various | — | Skip. None reduce the game-side work. |

**The verifiers API in `PLAN.md` is stale.** The v0 stack (`MultiTurnEnv`, `env_response`, `is_completed`, `Rubric`, `load_environment`) moved to `verifiers.legacy`, and `vf.RLTrainer` no longer exists. The v1 model:

- `TaskData` is an immutable row; `Task` carries hooks (`@vf.reward`, `@vf.metric`, `@vf.stop`, `setup`, `finalize`).
- `Taskset.load()` returns a list or generator of tasks. Keep it finite with unique keys (the curriculum sampler needs this).
- An `Env.run(task, agents)` method drives the loop: call `interaction.turn(observation_text)` until `segment.terminated`, record reward via `trace.record_reward`.
- Use the built-in `null` harness (tool-less chat loop) and `subprocess` runtime (0.3.1 defaults to a Prime VM runtime, so set this explicitly).
- Scaffold with `uv run vf-init factorio-arena`; install with `uv pip install -e environments/factorio_arena`. There is no `vf-install`.
- Reference implementations: `verifiers/v1/tasksets/textarena/taskset.py`, `environments/kuhn_poker/`, `environments/alphabet_sort/`.
- Eval: `uv run vf-eval factorio-arena -n 20 -r 4 --model <id> --env.agent.harness.id null --env.agent.runtime.type subprocess`. Output is `outputs/<env>--<model>--<harness>/<uuid>/traces.jsonl`.
- Hub: `prime env push`. Since 0.3.1 Hub packages are not auto-installed. Some Hub docs still describe the v0 contract.

Keep the Python game client (`reset`, `step`) framework-free so the verifiers adapter is thin and the TRL fallback stays cheap.

prime-rl sizing from its shipped examples: Qwen3-4B LoRA r32, batch 256, group 16, seq 2048, 200 steps ran on one H100 in about an hour. Our episodes are ~40 turns at ~1.5k tokens, so expect sequence lengths of 32k+ and 2 to 4 H100s for a 4B LoRA run, 8 for an 8B full fine-tune. Measure before trusting this.

FLE note for the writeup: FLE lab-play scores throughput per 60 s, not "have N items in inventory". The comparison must say so or add a throughput variant.

---

## 9. Tasks, curriculum, model access (Milestones 3 to 5)

| Item | License | Version | Verdict |
|---|---|---|---|
| PyYAML `safe_load` + Pydantic v2 | MIT | pydantic 2.12 | **Reuse.** Export `TaskSpec.model_json_schema()` to `tasks/task.schema.json` for editor validation; `# yaml-language-server: $schema=...` modeline per file. |
| pydantic-yaml | MIT | 1.7.0 | Skip. Wraps the same two lines. |
| Hugging Face `datasets` | Apache-2.0 | current | Later. `Dataset.from_list(...).push_to_hub(...)` for Milestone 6. |
| prime-rl `DifficultyPoolSampler` | Apache-2.0 | 0.9.0 | **Reuse.** PLAN §7.2 becomes config, not code. |
| OpenRouter | service | — | **Reuse** for every leaderboard model. One OpenAI-compatible base URL; returns `usage.cost` per response. |
| vLLM | Apache-2.0 | 0.31.0 | **Reuse** only for serving our own checkpoints. |
| LiteLLM | MIT (core) | 1.104.0 | Skip. OpenRouter already covers frontier and open models. |
| tokencost | MIT | 0.1.26 (Aug 2025) | Skip. Price table is stale. |

Curriculum config in prime-rl (`docs/algorithms.md`, "Curricula"):

```toml
[orchestrator.train.source.curriculum.sampler]
type = "difficulty_pool"
[orchestrator.train.source.curriculum.sampler.pools.hard]
threshold = 0.2
weight = 0.2
[orchestrator.train.source.curriculum.sampler.pools.normal]
threshold = 0.8
weight = 1.0
[orchestrator.train.source.curriculum.sampler.pools.easy]
threshold = 1.0
weight = 0.0
```

Thresholds are on mean group reward. Under our reward scheme success means reward above 0.5, so a 20–80% success band maps to roughly 0.1 and 0.6 on mean reward. Calibrate once. `AdvRangeGate` rejects zero-signal groups. Per-task state is checkpointed and logged under `curriculum/<env>/`.

verifiers client config: `--client.base-url https://openrouter.ai/api/v1 --client.api-key-var OPENROUTER_API_KEY --model <provider/model>`. The same config feeds judge calls.

Unconfirmed: whether verifiers copies OpenRouter's `usage.cost` field into `trace.usage`. Check one trace.

---

## 10. Eval analysis and failure taxonomy (Milestone 4)

| Item | License | Version | Verdict |
|---|---|---|---|
| numpy, pandas, matplotlib | BSD | current | **Reuse.** Own `analysis.py` producing `leaderboard.md` and PNGs. |
| `scipy.stats.bootstrap` | BSD-3 | current | **Reuse.** Resample episodes within a task, not across tasks. |
| [scorio](https://github.com/mohsenhariri/scorio) | MIT | 0.2.3 (one day old, 23 stars) | **Read.** Vendor its pass@k function rather than depend on it. |
| verifiers `vf.Judge[T]` and `vf-replay` | MIT | 0.3.1 | **Reuse.** Judge supports `schema=` with Pydantic, so a `Literal[...]` label enum is enforced. `vf-replay <output-dir>` re-scores saved traces offline with no game server. |
| inspect-ai 0.3.276, lighteval 0.13.0 | MIT | — | Skip. Nothing over verifiers for a custom multi-turn env; would require porting. |
| `prime eval tui` | — | — | Unconfirmed whether it reads v1 `traces.jsonl` (it was written for the v0 layout). Test before relying on it. |

pass@k is the Codex estimator: `1 - prod(1 - k / arange(n - c + 1, n + 1))`, with `num_rollouts >= k`.

Failure taxonomy order of operations: rule-based classifiers over monitor metrics first (out-of-reach count, zero fuel inserts, consecutive malformed turns, wait fraction), then the LLM judge as a `@vf.metric` for the remainder, then `vf-replay` across all eval runs once the label set stabilizes.

---

## 11. Visibility, replay, and baselines (Milestones 1, 4, 6)

| Item | License | Version | Verdict |
|---|---|---|---|
| Pillow + imageio + imageio-ffmpeg | MIT-CMU / BSD-2 | current | **Reuse.** One frame per step from observation JSON, MP4 for the clip, GIF via Pillow. ~80 lines. |
| rich | MIT | current | **Reuse** for a terminal replay and for the human-play loop. textual is overkill. |
| factorio-draftsman | MIT | 4.0.1 | **Reuse** to turn an entity list into a blueprint string for before/after stills. |
| [piebro/factorio-blueprint-visualizer](https://github.com/piebro/factorio-blueprint-visualizer) | MIT | 2.0 support since Jan 2025, last push Jan 2025 | **Reuse** for SVG stills. |
| [FBE (teoxoy)](https://github.com/Teoxoy/factorio-blueprint-editor) | MIT | active Aug 2026 | **Reuse** for sprite-accurate stills via the web editor. |
| `game.take_screenshot`, mapshot, FactorioMaps | — | — | Skip. Headless renders nothing; mapshot needs a GUI client; FactorioMaps is 1.1 only. |
| `factorio --benchmark --benchmark-ticks N` | engine | — | **Reuse** only for Milestone 0 UPS measurements, not visibility. |

Milestone 1 debugging path: the Python client writes one JSONL line per step (`tick`, `action`, `result`, `observation`) to `runs/<episode>.jsonl`. Determinism makes that file the replay. Add `helpers.write_file` traces from Lua only when debugging the mod itself. Real-client footage stays in Milestone 6 by replaying the action list on a native Mac client.

Human-play baseline: verifiers v1 has no human harness. Write a ~50-line `rich` loop over the Python client (`reset`, print observation, `input()`, parse JSON, `step`) that writes the same trace schema so the human row sits in the same analysis.

---

## 12. Repo scaffolding and developer tooling

| Item | License | Version | Verdict |
|---|---|---|---|
| uv | MIT/Apache | 0.12.6 installed | **Reuse.** Single src-layout package, `uv_build` backend, lockfile committed. |
| Python | PSF | pin 3.12 | verifiers excludes 3.14; prime-rl wants 3.12. |
| ruff | MIT | 0.16.10 | **Reuse** for lint and format. |
| pyrefly | MIT | 1.3.2 | **Reuse** advisory type checking. `ty` is still 0.0.x. |
| pytest | MIT | 9.x | **Reuse** with a `server` marker so unit tests run without Factorio. |
| pre-commit | MIT | 4.6 | **Reuse** with a pre-push hook that refuses pushes to `main`. |
| yamllint | GPL-3.0 (tool only, not linked) | 1.38 | **Reuse** as a hook. |
| GitHub Actions `astral-sh/setup-uv@v10`, `actions/checkout@v7`, `JohnnyMorganz/stylua-action@v4` | MIT | — | **Reuse.** |

GitHub branch protection: classic protection and rulesets both return 403 on this private repo under the Free plan. Options are making the repo public, GitHub Pro, or the local pre-push guard plus CI on PRs. Once rulesets are available, create one with `gh api -X POST repos/<owner>/<repo>/rulesets` requiring a pull request and a passing `ci` status check; `gh ruleset` itself is view-only.

Editor: Zed's Lua extension plus the FMTK typedefs via `.luarc.json`; basedpyright plus ruff for Python with format on save; redhat `yaml-language-server` picks up the task schema. Claude Code reads `AGENTS.md` natively when no `CLAUDE.md` exists (since 2.1.277). A committed `.claude/settings.json` can allowlist `uv`, `pytest`, `docker compose`, and `gh` commands and run ruff on edit.

---

## 13. Corrections to carry into PLAN.md

1. Replace `MultiTurnEnv`, `env_response`, `is_completed`, and `vf.RLTrainer` (sections 2.2, 3, 6) with verifiers v1 `Taskset` + `Env.run` and prime-rl.
2. Drop `defines.inventory.furnace_source` and friends (section 5.2); the 2.x names are `crafter_input`, `crafter_output`, `fuel`, `burnt_result`.
3. Pin Factorio 2.0.77 and Python 3.12.
4. Note that FLE lab-play measures throughput per minute, not inventory count (section 2.3 / 5.3).
5. Note that the Mac is emulation-only; cost numbers come from an x86 box (section 7.3).

## 14. Milestone 0 checklist derived from this research

- [ ] Headless server starts in Docker on the Mac (box64 or Rosetta), `auto_pause: false`, RCON hello-world from Python.
- [ ] Unattached character walks, stops when told, and stalls on collision.
- [ ] Unattached character mines via `mining_state` (fallback: `LuaEntity.mine` with computed tick cost).
- [ ] Unattached character crafts via `begin_crafting`; `crafting_queue` advances with ticks.
- [ ] Reach attributes return real values on the unattached character.
- [ ] `tick_paused` + `ticks_to_run` step the world exactly N ticks.
- [ ] An observation over 8 KB round-trips over RCON intact.
- [ ] `--dump-data` produces `game_data.json`; commit it.
- [ ] UPS at cranked `game.speed`; servers per core; determinism checksum Mac vs x86.
