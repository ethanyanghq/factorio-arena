"""Shared helpers for the milestone 0 probes in this directory.

A probe is a script that asks the live server one question about engine behavior
and prints expected versus observed. These helpers cover the parts every probe needs:
connecting, running Lua, waiting for the game clock, and printing the comparison.
"""

import json
import os
import time

from factorio_arena.rcon import RconClient

HOST = "127.0.0.1"
PORT = 27015
TICKS_PER_SECOND = 60


def connect() -> RconClient:
    """Connect using the password in FACTORIO_RCON_PASSWORD and arm the Lua console.

    The first Lua command on a fresh server only prints an achievements warning and
    asks you to repeat it, so a throwaway command is sent before returning.
    """
    password = os.environ.get("FACTORIO_RCON_PASSWORD")
    if not password:
        raise SystemExit("set FACTORIO_RCON_PASSWORD to the value in .env")
    client = RconClient(HOST, PORT, password)
    lua(client, "rcon.print('armed')")
    return client


def lua(client: RconClient, code: str) -> str:
    """Run Lua on the server and return what rcon.print produced."""
    return client.command("/sc " + " ".join(code.split()))


def lua_json(client: RconClient, code: str) -> dict:
    """Run Lua that ends by printing a table as JSON, and parse it."""
    return json.loads(lua(client, code))


def current_tick(client: RconClient) -> int:
    return int(lua(client, "rcon.print(game.tick)"))


def wait_ticks(client: RconClient, start_tick: int, ticks: int) -> int:
    """Sleep until the game clock has advanced at least `ticks` past start_tick.
    Returns the tick it actually reached."""
    deadline = time.time() + 10 * ticks / TICKS_PER_SECOND
    while time.time() < deadline:
        now = current_tick(client)
        if now >= start_tick + ticks:
            return now
        time.sleep(0.05)
    raise TimeoutError(f"game clock did not advance {ticks} ticks; is the server paused?")


def report(label: str, expected: str, observed: str) -> None:
    print(f"{label}\n    expected: {expected}\n    observed: {observed}")
