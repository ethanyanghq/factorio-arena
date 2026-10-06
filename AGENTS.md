# AGENTS.md

Guidelines for writing code in this repository. They apply to every language and tool we use.

**Core principle:** Code is read far more often than it is written. Optimize for a human reader building a mental model of the system. Clarity beats cleverness, brevity, and premature optimization.

## Project Commands

Run them before every commit. `make check` runs the full pre-commit hook set; `make setup` installs dependencies and hooks.

- **Test:** `make test`
- **Lint:** `make lint`
- **Format:** `make format`

## Agent Workflow

- **Follow existing conventions in the codebase.** Consistency matters more than any individual preference.
- **Make the smallest change that solves the task.** Focused changes are easier to review and less likely to break unrelated behavior.
- **Ask when requirements are ambiguous instead of guessing.** This matters most for reward and task design, where a wrong guess silently changes what is measured.
- **Run all project commands before committing; never commit failing checks.** A broken commit costs everyone who builds on it.
- **Never weaken tests or checks to make them pass.** Deleting assertions, loosening tolerances, or skipping tests hides a bug instead of fixing it.

## Naming

- **Names reveal intent.** A reader should learn what something is and why it exists without tracing its implementation.
- **Use one word per concept, drawn from the domain.** Consistent vocabulary (`observation`, `action`, `reward`, `episode`) lets readers map code to concepts.
- **Avoid abbreviations and encodings** (except universal ones like `id`, `rng`). Decoding names taxes every reader.
- **Name booleans as questions** (`is_terminal`, `has_reached_goal`). Conditionals then read like sentences.
- **Replace magic numbers with named constants.** A name records the meaning a bare literal hides.

## Functions

- **Do one thing.** If describing a function needs "and", split it; single-purpose functions are easier to name, test, and reuse.
- **Keep functions short (roughly 20 lines or fewer).** Small units fit in a reader's head at once.
- **Keep one level of abstraction per function, ordered top-down.** Code then reads like a narrative from intent down to detail.
- **Use few arguments (three or fewer); group related ones into a named structure.** Every argument is something the reader must hold in mind.
- **Avoid flag arguments.** A boolean parameter means the function does two things; write two functions.
- **No hidden side effects; separate commands from queries.** A function that looks like a read but mutates state breaks the reader's model.

## Design

- **Build the simplest thing that works; don't design for hypothetical futures.** Speculative abstractions add indirection with no payoff.
- **Remove duplicated knowledge, not coincidental similarity.** Merging code that changes for different reasons couples unrelated concepts.
- **Keep related code together and coupling between modules low.** Readers should find a concept in one place.
- **Isolate I/O, frameworks, and third-party APIs at the edges.** Core logic stays readable, testable, and stack-independent.
- **Prefer immutable data and pure functions where practical.** Values that can't change can't surprise the reader.

## Comments

- **Code says what; comments say why.** Rationale, constraints, and trade-offs can't be expressed in code.
- **Don't narrate the code.** Comments that restate the code add noise and drift out of date.
- **Document public interfaces: purpose, units, shapes, valid ranges, invariants.** This is the contract callers rely on.
- **Delete dead and commented-out code.** Version control remembers it; readers shouldn't have to wonder about it.

## Errors

- **Fail fast and loudly; validate inputs at boundaries.** Errors caught near their cause are cheap to diagnose.
- **Never swallow errors or signal failure with sentinel values.** Silent failures corrupt results far from their origin.
- **Error messages state what was expected and what was received.** The message alone should be enough to start debugging.

## Tests

- **Tests are documentation: one behavior per test, named for that behavior.** A failing test should tell the reader exactly what broke.
- **Keep tests fast, independent, and deterministic.** Slow or flaky tests get ignored.
- **Add or update tests with every behavior change.** Tests are what make refactoring safe.

## RL Environments

- **Separate dynamics, observation, reward, and termination into distinct, named units.** Each is its own concept to understand, test, and change.
- **Treat the reward function as the spec: name each component and document its intent.** The agent optimizes what you wrote, not what you meant.
- **Reward the intended outcome, not an easily gamed proxy.** Agents find loopholes humans don't anticipate.
- **Expose only intended information in observations.** Leaked privileged state lets agents shortcut the task and invalidates results.
- **Route all randomness through an explicit, seeded RNG; never use global random state.** The same seed and actions must reproduce the same trajectory.
- **Make environment state explicit; `reset` must fully restore it.** State leaking across episodes causes subtle, hard-to-trace bugs.
- **Distinguish termination (task ended) from truncation (step or time limit).** Conflating them biases value estimates.
- **Specify action and observation spaces explicitly: types, shapes, ranges, units.** They are the contract between environment and agent.
- **Bump the environment's version whenever its reward, observation, action, or dynamics semantics change.** Results from different versions aren't comparable, and the version number is what tells readers so.
- **Optimize the `step` hot path only with profiling evidence, and comment why.** Readability is the default; a measured bottleneck is the only exception.
- **Give each environment a short README: task, spaces, reward, termination, version history.** A newcomer should understand the environment without reading its code.
- **Test environment invariants: seeded determinism, reset correctness, space conformance, reward bounds, finite values, consistent dtypes.** These catch bugs that training curves hide.

## Commits

Follow [Conventional Commits](https://www.conventionalcommits.org): `<type>(<scope>): <description>`.

Use small and focused commits. Commit early and commit often.

- **Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`.** A fixed vocabulary makes history scannable and changelogs automatable.
- **Description: imperative, lowercase, no trailing period, 72 characters or fewer** (e.g., `fix(reward): clip distance penalty to [-1, 0]`). Uniform subjects read cleanly in logs.
- **Use the body to explain why.** The diff shows what changed; only the message can record the reason.
- **Mark breaking changes with `!` or a `BREAKING CHANGE:` footer.** Changes to reward, observation, or action semantics are breaking because they invalidate prior results.
- **One logical change per commit; keep refactors separate from behavior changes.** Focused commits are easier to review, revert, and bisect.
- **Leave code you touch cleaner, but put unrelated cleanup in its own commit.** Improvement shouldn't hide inside an unrelated diff.

### Scopes

Use exactly one scope from this table. A fixed set keeps history filterable by area.

| Scope    | Covers                                                        |
|----------|---------------------------------------------------------------|
| `env`    | Core dynamics, state, `step`/`reset`, termination, truncation |
| `reward` | Reward functions, components, and shaping                     |
| `obs`    | Observation construction and observation space                |
| `action` | Action handling and action space                              |
| `tasks`  | Task definitions, scenarios, levels, and their data           |
| `eval`   | Evaluation harnesses, metrics, and benchmarks                 |
| `config` | Configuration and default parameters                          |
| `deps`   | Dependency additions, upgrades, and removals                  |

- **Omit the scope only for repo-wide changes** (e.g., `chore: update license headers`). Forcing one scope onto a cross-cutting change would mislead readers.
- **If a change seems to need two scopes, split it into two commits.** It is usually two logical changes.
- **Don't invent scopes; add new ones to this table first.** The list stays useful only if everyone shares the same one.

**When in doubt,** choose the version a newcomer would understand fastest.
