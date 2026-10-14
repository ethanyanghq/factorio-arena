"""Milestone 0 probe: does an unattached character craft, and does the queue advance?

Run with the Docker server up:

    FACTORIO_RCON_PASSWORD=<value from .env> uv run python scripts/probe_craft.py

PLAN.md §3 lists `begin_crafting` as documented but unconfirmed for a character with
no player attached. Mining turned out to need a fallback (see probe_mine.py), so the
question here is whether crafting is engine-driven or also needs the mod to do it.

Step 1 queues a craft and checks the queue. Step 2 lets the clock run and checks the
product arrived in the expected number of ticks. Step 3 checks a craft without
ingredients is refused rather than silently queued.
"""

from probe_lib import RconClient, connect, lua, lua_json, report, wait_ticks

RECIPE = "iron-gear-wheel"
INGREDIENT = "iron-plate"
INGREDIENTS_PER_CRAFT = 2
# Base game: iron-gear-wheel energy_required 0.5 s, character crafting speed 1.
EXPECTED_TICKS_PER_CRAFT = 30
CRAFTS = 3
WAIT_TICKS = EXPECTED_TICKS_PER_CRAFT * CRAFTS + 30


def spawn_character_with_plates(client: RconClient) -> dict:
    return lua_json(
        client,
        f"""
        local surface = game.surfaces[1]
        local spot = surface.find_non_colliding_position("character", {{0, 0}}, 50, 1)
        probe_char = surface.create_entity{{name = "character", position = spot, force = "player"}}
        local inserted = probe_char.get_main_inventory().insert{{
            name = "{INGREDIENT}", count = {INGREDIENTS_PER_CRAFT * CRAFTS}
        }}
        rcon.print(helpers.table_to_json({{
            plates = inserted, crafting_speed = probe_char.character_crafting_speed_modifier,
            recipe_seconds = prototypes.recipe["{RECIPE}"].energy
        }}))
        """,
    )


def begin_crafting(client: RconClient, count: int) -> dict:
    return lua_json(
        client,
        f"""
        local queued = probe_char.begin_crafting{{count = {count}, recipe = "{RECIPE}"}}
        rcon.print(helpers.table_to_json({{
            queued = queued, queue_size = probe_char.crafting_queue_size, tick = game.tick
        }}))
        """,
    )


def read_state(client: RconClient) -> dict:
    return lua_json(
        client,
        f"""
        local inventory = probe_char.get_main_inventory()
        rcon.print(helpers.table_to_json({{
            tick = game.tick,
            queue_size = probe_char.crafting_queue_size,
            progress = probe_char.crafting_queue_progress,
            products = inventory.get_item_count("{RECIPE}"),
            plates = inventory.get_item_count("{INGREDIENT}")
        }}))
        """,
    )


def remove_character(client: RconClient) -> None:
    lua(client, "if probe_char and probe_char.valid then probe_char.destroy() end probe_char = nil")


def main() -> None:
    client = connect()
    try:
        remove_character(client)
        start = spawn_character_with_plates(client)
        print(
            f"spawned character with {start['plates']} {INGREDIENT}; recipe takes "
            f"{start['recipe_seconds']}s at speed modifier {start['crafting_speed']}"
        )

        # 1. Queue: begin_crafting should accept the crafts and consume the plates.
        queued = begin_crafting(client, CRAFTS)
        after_queue = read_state(client)
        report(
            "1. begin_crafting queues crafts",
            f"queued {CRAFTS}; queue_size 1 (same recipe collapses into one entry of "
            f"count {CRAFTS}); plates {start['plates']} -> 0",
            f"queued {queued['queued']}; queue_size {after_queue['queue_size']}; "
            f"plates {after_queue['plates']}",
        )

        # 2. Progress: let the clock run and expect the products to appear on time.
        wait_ticks(client, queued["tick"], WAIT_TICKS)
        done = read_state(client)
        ticks = done["tick"] - queued["tick"]
        report(
            "2. crafting queue advances with ticks",
            f"{CRAFTS} {RECIPE} in inventory after ~{EXPECTED_TICKS_PER_CRAFT * CRAFTS} ticks; "
            f"queue empty",
            f"{done['products']} {RECIPE} after {ticks} ticks; queue_size {done['queue_size']}; "
            f"progress {done['progress']}",
        )

        # 3. Refusal: no plates left, so another craft should not queue.
        refused = begin_crafting(client, 1)
        report(
            "3. begin_crafting without ingredients",
            "queued 0; queue_size 0",
            f"queued {refused['queued']}; queue_size {refused['queue_size']}",
        )
    finally:
        remove_character(client)
        client.close()


if __name__ == "__main__":
    main()
