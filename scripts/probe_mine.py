"""Milestone 0 probe: does an unattached character mine when a script tells it to?

Run with the Docker server up:

    FACTORIO_RCON_PASSWORD=<value from .env> uv run python scripts/probe_mine.py

PLAN.md §3 says mining via `mining_state` is documented but unconfirmed for a
character with no player attached. If it works, the mod sets `mining_state` and the
engine does the timing. If it doesn't, the fallback is `LuaEntity.mine`, which moves
the ore instantly and leaves the mod to charge the tick cost and enforce reach itself.

Steps 1 and 2 test the direct route, once and re-asserted every tick. Step 3 tests
the fallback. Step 4 asks whether the fallback enforces reach. The last line prints
the prototype numbers the mod needs to compute a tick cost.

Measured 2026-10-14 on 2.0.77: the direct route does nothing (step 2 gains zero ore
even when re-asserted ~every tick), the fallback works, and it ignores reach.
"""

from probe_lib import RconClient, connect, lua, lua_json, report, wait_ticks

MINE_TICKS = 300
# Base game: stone/iron mining_time 1 second, character mining speed 0.5, so one ore
# every 2 seconds = 120 ticks. 300 ticks would yield 2, with a third in progress.
EXPECTED_ORE_PER_TICK = 0.5 / 60
# Character resource reach in the base game is 2.7 tiles; 6 is well outside.
OUT_OF_REACH_TILES = 6


def spawn_character_beside_ore(client: RconClient) -> dict:
    """Create the character next to the nearest ore patch and return where things are."""
    return lua_json(
        client,
        """
        local surface = game.surfaces[1]
        local ores = surface.find_entities_filtered{
            type = "resource", position = {0, 0}, radius = 200
        }
        local nearest, best = nil, math.huge
        for _, ore in pairs(ores) do
            if ore.prototype.mineable_properties.minable then
                local d = ore.position.x ^ 2 + ore.position.y ^ 2
                if d < best then nearest, best = ore, d end
            end
        end
        probe_ore = nearest
        local spot = surface.find_non_colliding_position(
            "character", {probe_ore.position.x - 1.5, probe_ore.position.y}, 5, 0.5)
        probe_char = surface.create_entity{name = "character", position = spot, force = "player"}
        rcon.print(helpers.table_to_json({
            ore = probe_ore.name, ore_x = probe_ore.position.x, ore_y = probe_ore.position.y,
            x = probe_char.position.x, y = probe_char.position.y,
            can_reach = probe_char.can_reach_entity(probe_ore)
        }))
        """,
    )


def set_mining_and_read_tick(client: RconClient) -> int:
    """Set mining_state and return the tick it was set on, in one round trip."""
    return int(
        lua(
            client,
            """
            probe_char.mining_state = {mining = true, position = probe_ore.position}
            rcon.print(game.tick)
            """,
        )
    )


def stop_mining(client: RconClient) -> None:
    lua(client, "probe_char.mining_state = {mining = false}")


def read_state(client: RconClient) -> dict:
    return lua_json(
        client,
        """
        rcon.print(helpers.table_to_json({
            tick = game.tick,
            mining = probe_char.mining_state.mining,
            progress = probe_char.character_mining_progress,
            in_inventory = probe_char.get_main_inventory().get_item_count(probe_ore.name),
            ore_left = probe_ore.valid and probe_ore.amount or 0
        }))
        """,
    )


def mine_once_with_fallback(client: RconClient) -> bool:
    reply = lua(client, "rcon.print(probe_ore.mine{inventory = probe_char.get_main_inventory()})")
    return reply.strip() == "true"


def teleport_away_from_ore(client: RconClient) -> bool:
    """Move the character out of reach and return whether it can still reach the ore."""
    return lua_json(
        client,
        f"""
        local spot = game.surfaces[1].find_non_colliding_position(
            "character",
            {{probe_ore.position.x - {OUT_OF_REACH_TILES}, probe_ore.position.y}}, 5, 0.5)
        probe_char.teleport(spot)
        rcon.print(helpers.table_to_json({{can_reach = probe_char.can_reach_entity(probe_ore)}}))
        """,
    )["can_reach"]


def mining_constants(client: RconClient) -> dict:
    return lua_json(
        client,
        """
        rcon.print(helpers.table_to_json({
            ore_mining_time_seconds = probe_ore.prototype.mineable_properties.mining_time,
            character_mining_speed = prototypes.entity["character"].mining_speed,
            character_resource_reach_tiles = probe_char.resource_reach_distance
        }))
        """,
    )


def remove_character(client: RconClient) -> None:
    lua(client, "if probe_char and probe_char.valid then probe_char.destroy() end probe_char = nil")


def main() -> None:
    client = connect()
    try:
        remove_character(client)
        start = spawn_character_beside_ore(client)
        print(
            f"spawned character at ({start['x']:.2f}, {start['y']:.2f}) beside {start['ore']} "
            f"at ({start['ore_x']:.1f}, {start['ore_y']:.1f}); can_reach={start['can_reach']}"
        )

        # 1. Set mining_state once, let the clock run, count ore in the inventory.
        before = read_state(client)
        set_mining_and_read_tick(client)
        wait_ticks(client, before["tick"], MINE_TICKS)
        after = read_state(client)
        ticks = after["tick"] - before["tick"]
        report(
            "1. mining_state set once",
            f"~{EXPECTED_ORE_PER_TICK * ticks:.1f} ore over {ticks} ticks if it persists",
            f"{after['in_inventory'] - before['in_inventory']} ore gained; "
            f"mining_state.mining={after['mining']} one tick later; progress={after['progress']}",
        )

        # 2. Re-assert mining_state on every round trip (close to every tick) for 300 ticks.
        before = read_state(client)
        round_trips = 0
        while set_mining_and_read_tick(client) < before["tick"] + MINE_TICKS:
            round_trips += 1
        after = read_state(client)
        stop_mining(client)
        ticks = after["tick"] - before["tick"]
        report(
            "2. mining_state re-asserted every tick",
            f"~{EXPECTED_ORE_PER_TICK * ticks:.1f} ore over {ticks} ticks "
            f"if per-tick re-assertion is what the engine wants",
            f"{after['in_inventory'] - before['in_inventory']} ore gained after "
            f"{round_trips} re-assertions over {ticks} ticks; progress={after['progress']}",
        )

        # 3. Fallback: LuaEntity.mine moves one ore instantly.
        before = read_state(client)
        mined = mine_once_with_fallback(client)
        after = read_state(client)
        report(
            "3. fallback LuaEntity.mine, in reach",
            "1 ore gained; ore_left down by 1 (the boolean means 'entity removed', so it "
            "is false while ore remains in the patch)",
            f"returned {mined}; {after['in_inventory'] - before['in_inventory']} ore gained; "
            f"ore_left {before['ore_left']} -> {after['ore_left']}",
        )

        # 4. Does the fallback enforce reach? If not, the mod must check can_reach_entity.
        can_reach = teleport_away_from_ore(client)
        before = read_state(client)
        mined = mine_once_with_fallback(client)
        after = read_state(client)
        report(
            "4. fallback LuaEntity.mine, out of reach",
            f"can_reach False; if reach were enforced, 0 ore gained from "
            f"{OUT_OF_REACH_TILES} tiles away",
            f"can_reach {can_reach}; returned {mined}; "
            f"{after['in_inventory'] - before['in_inventory']} ore gained",
        )

        print("mining constants for the tick-cost formula:", mining_constants(client))
    finally:
        remove_character(client)
        client.close()


if __name__ == "__main__":
    main()
