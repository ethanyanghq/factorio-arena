"""Milestone 0 probe: does an unattached character walk when a script tells it to?

Run with the Docker server up:

    FACTORIO_RCON_PASSWORD=<value from .env> uv run python scripts/probe_walk.py

The question this answers (PLAN.md §3, "the fact the whole project rests on"): a
`character` entity with no player attached, given `walking_state` once over RCON,
either keeps walking on its own for many ticks, or moves one tick and stops. The
first means the mod can set direction and let the engine run; the second means the
mod needs an on_tick handler that re-asserts walking every tick.

Each step prints what it expected and what it saw. Read the numbers, not the code.
"""

import json
import os
import time

from factorio_arena.rcon import RconClient

HOST = "127.0.0.1"
PORT = 27015
TICKS_PER_SECOND = 60
WALK_TICKS = 60
# Character running speed in the base game, from the character prototype.
EXPECTED_TILES_PER_TICK = 0.15
# A stone wall placed this many tiles east of the character's start.
WALL_OFFSET_TILES = 3


def lua(client: RconClient, code: str) -> str:
    """Run Lua on the server and return what rcon.print produced."""
    return client.command("/sc " + " ".join(code.split()))


def lua_json(client: RconClient, code: str) -> dict:
    """Run Lua that ends by printing a table as JSON, and parse it."""
    return json.loads(lua(client, code))


def arm_lua_console(client: RconClient) -> None:
    """The first Lua command on a fresh server only prints an achievements warning and
    asks you to repeat it. Send a throwaway command so the real ones go through."""
    lua(client, "rcon.print('armed')")


def spawn_character(client: RconClient) -> dict:
    return lua_json(
        client,
        """
        local surface = game.surfaces[1]
        local spot = surface.find_non_colliding_position("character", {0, 0}, 50, 1)
        probe_char = surface.create_entity{name = "character", position = spot, force = "player"}
        rcon.print(helpers.table_to_json({
            x = probe_char.position.x, y = probe_char.position.y, tick = game.tick
        }))
        """,
    )


def start_walking_east(client: RconClient) -> None:
    lua(client, "probe_char.walking_state = {walking = true, direction = defines.direction.east}")


def stop_walking(client: RconClient) -> None:
    lua(client, "probe_char.walking_state = {walking = false, direction = defines.direction.east}")


def read_state(client: RconClient) -> dict:
    return lua_json(
        client,
        """
        rcon.print(helpers.table_to_json({
            x = probe_char.position.x, y = probe_char.position.y, tick = game.tick,
            walking = probe_char.walking_state.walking
        }))
        """,
    )


def place_wall_east_of(client: RconClient, x: float, y: float) -> None:
    """Build a three-tile wall column east of (x, y).

    One tile is not enough: a stone wall's collision box (±0.29 around the tile
    centre) is smaller than the tile, and a character at y=0.0 walks past a wall
    centred at y=0.5 without touching it. Measured on 2026-10-14.
    """
    for row in (-1, 0, 1):
        lua(
            client,
            f"""
            game.surfaces[1].create_entity{{
                name = "stone-wall", position = {{{x + WALL_OFFSET_TILES}, {y + row}}},
                force = "player"
            }}
            """,
        )


def remove_walls(client: RconClient) -> None:
    lua(
        client,
        """
        for _, wall in pairs(game.surfaces[1].find_entities_filtered{name = "stone-wall"}) do
            wall.destroy()
        end
        """,
    )


def remove_character(client: RconClient) -> None:
    lua(client, "if probe_char and probe_char.valid then probe_char.destroy() end probe_char = nil")


def wait_ticks(client: RconClient, start_tick: int, ticks: int) -> int:
    """Sleep until the game clock has advanced at least `ticks` past start_tick.
    Returns the tick it actually reached."""
    deadline = time.time() + 10 * ticks / TICKS_PER_SECOND
    while time.time() < deadline:
        now = read_state(client)["tick"]
        if now >= start_tick + ticks:
            return now
        time.sleep(0.05)
    raise TimeoutError(f"game clock did not advance {ticks} ticks; is the server paused?")


def report(label: str, expected: str, observed: str) -> None:
    print(f"{label}\n    expected: {expected}\n    observed: {observed}")


def main() -> None:
    password = os.environ.get("FACTORIO_RCON_PASSWORD")
    if not password:
        raise SystemExit("set FACTORIO_RCON_PASSWORD to the value in .env")
    client = RconClient(HOST, PORT, password)
    try:
        arm_lua_console(client)
        remove_character(client)
        start = spawn_character(client)
        print(f"spawned character at ({start['x']:.2f}, {start['y']:.2f}) on tick {start['tick']}")

        # 1. Walks: set walking_state once, let the clock run, measure displacement.
        start_walking_east(client)
        before = read_state(client)
        wait_ticks(client, before["tick"], WALK_TICKS)
        after = read_state(client)
        ticks = after["tick"] - before["tick"]
        moved = after["x"] - before["x"]
        report(
            "1. walks after one walking_state command",
            f"~{EXPECTED_TILES_PER_TICK * ticks:.1f} tiles east over {ticks} ticks "
            f"if walking persists; ~{EXPECTED_TILES_PER_TICK:.2f} if it lasts one tick",
            f"{moved:.2f} tiles east over {ticks} ticks; walking_state.walking={after['walking']}",
        )

        # 2. Stops: clear walking_state, let the clock run, expect no movement.
        stop_walking(client)
        before = read_state(client)
        wait_ticks(client, before["tick"], WALK_TICKS)
        after = read_state(client)
        report(
            "2. stops when told",
            "0.00 tiles moved",
            f"{after['x'] - before['x']:.2f} tiles moved; walking_state.walking={after['walking']}",
        )

        # 3. Stalls on collision: wall column 3 tiles east, walk 60 ticks, expect to stop short.
        here = read_state(client)
        place_wall_east_of(client, here["x"], here["y"])
        start_walking_east(client)
        wait_ticks(client, here["tick"], WALK_TICKS)
        after = read_state(client)
        stop_walking(client)
        report(
            "3. stalls on collision",
            f"stops just short of {WALL_OFFSET_TILES} tiles east (the wall), "
            f"not ~{EXPECTED_TILES_PER_TICK * WALK_TICKS:.1f}; no sideways drift",
            f"{after['x'] - here['x']:.2f} tiles east, {after['y'] - here['y']:.2f} tiles south; "
            f"walking_state.walking={after['walking']}",
        )
    finally:
        remove_walls(client)
        remove_character(client)
        client.close()


if __name__ == "__main__":
    main()
