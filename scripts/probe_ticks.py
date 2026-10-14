"""Milestone 0 probe: can the world be frozen and stepped exactly N ticks over RCON?

Run with the Docker server up:

    FACTORIO_RCON_PASSWORD=<value from .env> uv run python scripts/probe_ticks.py

PLAN.md §4's time model needs three things from the engine, checked here in order:

1. `game.tick_paused = true` stops the clock, and RCON still answers while paused.
2. `game.ticks_to_run = N` advances exactly N ticks and then stops again.
3. A character action started before stepping (walking) progresses during the step
   and not otherwise, so "one step = N ticks of consequence" holds.

It also covers two other checklist items that are cheap once connected: the reach
attributes read as real numbers on an unattached character, and a reply larger than
8 KB survives the RCON round trip intact.
"""

import time

from probe_lib import RconClient, connect, lua, lua_json, report

STEP_TICKS = 60
FREEZE_SECONDS = 1.0
# Character running speed in the base game, from the character prototype.
EXPECTED_TILES_PER_TICK = 0.15
BIG_REPLY_BYTES = 9000


def spawn_character(client: RconClient) -> None:
    lua(
        client,
        """
        local surface = game.surfaces[1]
        local spot = surface.find_non_colliding_position("character", {0, 0}, 50, 1)
        probe_char = surface.create_entity{name = "character", position = spot, force = "player"}
        """,
    )


def remove_character(client: RconClient) -> None:
    lua(client, "if probe_char and probe_char.valid then probe_char.destroy() end probe_char = nil")


def tick_and_x(client: RconClient) -> dict:
    return lua_json(
        client,
        """
        rcon.print(helpers.table_to_json({
            tick = game.tick, paused = game.tick_paused, x = probe_char.position.x
        }))
        """,
    )


def set_paused(client: RconClient, paused: bool) -> None:
    lua(client, f"game.tick_paused = {'true' if paused else 'false'}")


def step(client: RconClient, ticks: int) -> None:
    lua(client, f"game.ticks_to_run = {ticks}")


def wait_until_stepping_finishes(client: RconClient, target_tick: int) -> dict:
    """ticks_to_run runs at normal speed in the background; poll until it lands."""
    deadline = time.time() + 10
    while time.time() < deadline:
        state = tick_and_x(client)
        if state["tick"] >= target_tick:
            time.sleep(0.2)  # give it a chance to overshoot, if it is going to
            return tick_and_x(client)
        time.sleep(0.05)
    raise TimeoutError(f"tick never reached {target_tick}")


def reach_attributes(client: RconClient) -> dict:
    return lua_json(
        client,
        """
        rcon.print(helpers.table_to_json({
            reach_distance = probe_char.reach_distance,
            build_distance = probe_char.build_distance,
            resource_reach_distance = probe_char.resource_reach_distance,
            item_pickup_distance = probe_char.item_pickup_distance,
            drop_item_distance = probe_char.drop_item_distance
        }))
        """,
    )


def main() -> None:
    client = connect()
    try:
        remove_character(client)
        spawn_character(client)
        set_paused(client, False)

        # 1. Freeze: pause, wait a real second, the tick must not move and RCON must answer.
        set_paused(client, True)
        frozen = tick_and_x(client)
        time.sleep(FREEZE_SECONDS)
        still = tick_and_x(client)
        report(
            "1. tick_paused freezes the clock; RCON still answers",
            f"tick unchanged over {FREEZE_SECONDS}s; paused True",
            f"tick {frozen['tick']} -> {still['tick']}; paused {still['paused']}",
        )

        # 2. Step exactly N: ticks_to_run should advance N and stop.
        before = tick_and_x(client)
        step(client, STEP_TICKS)
        after = wait_until_stepping_finishes(client, before["tick"] + STEP_TICKS)
        report(
            f"2. ticks_to_run = {STEP_TICKS} advances exactly {STEP_TICKS}",
            f"tick +{STEP_TICKS}; paused True afterwards",
            f"tick +{after['tick'] - before['tick']}; paused {after['paused']}",
        )

        # 3. Consequence only during the step: start walking while frozen, step, measure.
        lua(
            client,
            "probe_char.walking_state = {walking = true, direction = defines.direction.east}",
        )
        time.sleep(0.5)
        frozen_walk = tick_and_x(client)
        step(client, STEP_TICKS)
        after_walk = wait_until_stepping_finishes(client, frozen_walk["tick"] + STEP_TICKS)
        lua(
            client,
            "probe_char.walking_state = {walking = false, direction = defines.direction.east}",
        )
        report(
            "3. walking happens during the step, not while frozen",
            f"0.00 tiles while frozen; ~{EXPECTED_TILES_PER_TICK * STEP_TICKS:.1f} tiles after "
            f"stepping {STEP_TICKS}",
            f"{frozen_walk['x'] - after['x']:.2f} tiles while frozen; "
            f"{after_walk['x'] - frozen_walk['x']:.2f} tiles after stepping "
            f"{after_walk['tick'] - frozen_walk['tick']}",
        )

        # 4. Reach attributes on an unattached character.
        print("4. reach attributes:", reach_attributes(client))

        # 5. A reply bigger than 8 KB round-trips intact.
        big = client.command(f"/sc rcon.print(string.rep('x', {BIG_REPLY_BYTES}))")
        report(
            "5. >8 KB reply round-trips",
            f"{BIG_REPLY_BYTES} x's (plus newline)",
            f"{len(big.strip())} chars, all x: {set(big.strip()) == {'x'}}",
        )
    finally:
        set_paused(client, False)
        remove_character(client)
        client.close()


if __name__ == "__main__":
    main()
