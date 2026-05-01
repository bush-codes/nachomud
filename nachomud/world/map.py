"""ASCII map rendering of the explored world.

`render_map(world_id, current_room_id, visited_rooms)` plots each
visited room at its stored grid coordinates — no BFS placement, no
collisions, no off-grid section. With the grid invariant enforced at
generation time, two rooms can never share a cell.

The current room is marked `[*Name*]`; others appear as `[ Name ]`.
Rooms on a different z-layer (stairs, ladders) are listed underneath
the grid. Per-actor fog-of-war: only rooms in `visited_rooms` (plus
their immediate neighbors via the world graph) are drawn.
"""
from __future__ import annotations

import nachomud.world.store as world_store


_MIN_NAME_W = 6


def render_map(world_id: str, current_room_id: str,
               visited_rooms: list[str], *, max_rooms: int = 200) -> str:
    visited: set[str] = set(visited_rooms or []) | {current_room_id}

    # Fog-of-war reveal: a visited room "sees" its immediate neighbors
    # via the world graph, even if the player hasn't stepped into them.
    graph = world_store.load_graph(world_id)
    eligible: set[str] = set(visited)
    for rid in visited:
        for dest in graph.get(rid, {}).values():
            if isinstance(dest, str):
                eligible.add(dest)

    placed: dict[str, tuple[int, int, int]] = {}
    names: dict[str, str] = {}
    for rid in eligible:
        if not world_store.room_exists(world_id, rid):
            continue
        try:
            r = world_store.load_room(world_id, rid)
        except Exception:
            continue
        if world_store.is_orphan_coords(r.coords):
            continue
        placed[rid] = r.coords
        names[rid] = r.name or rid
        if len(placed) >= max_rooms:
            break

    if current_room_id not in placed:
        return "(map unavailable — current room not in the world store)"

    cur_z = placed[current_room_id][2]
    same_z: dict[str, tuple[int, int]] = {
        rid: (c[0], c[1]) for rid, c in placed.items() if c[2] == cur_z
    }
    other_z: list[tuple[str, int]] = sorted(
        [(rid, c[2]) for rid, c in placed.items() if c[2] != cur_z],
        key=lambda t: (t[1], names.get(t[0], "")),
    )

    name_counts: dict[str, int] = {}
    for nm in names.values():
        name_counts[nm] = name_counts.get(nm, 0) + 1
    for rid, nm in list(names.items()):
        if name_counts[nm] > 1:
            tail = rid.rsplit(".", 1)[-1][:6]
            names[rid] = f"{nm} #{tail}"

    placed_names = [names[rid] for rid in same_z]
    name_w = max((len(n) for n in placed_names), default=_MIN_NAME_W)
    name_w = max(name_w, _MIN_NAME_W)
    cell_w = name_w + 4

    xs = [p[0] for p in same_z.values()]
    ys = [p[1] for p in same_z.values()]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    cols = maxx - minx + 1
    rows = maxy - miny + 1

    h_pad = 3
    v_pad = 1

    canvas_w = cols * cell_w + max(0, cols - 1) * h_pad
    canvas_h = rows + max(0, rows - 1) * v_pad
    canvas: list[list[str]] = [[' '] * canvas_w for _ in range(canvas_h)]

    def cell_origin(x: int, y: int) -> tuple[int, int]:
        col = (x - minx) * (cell_w + h_pad)
        row = (y - miny) * (1 + v_pad)
        return row, col

    label_span: dict[str, tuple[int, int, int]] = {}
    for rid, (x, y) in same_z.items():
        row, col = cell_origin(x, y)
        nm = names[rid][:name_w]
        label = f"[*{nm}*]" if rid == current_room_id else f"[ {nm} ]"
        pad_left = (cell_w - len(label)) // 2
        label_start = col + pad_left
        label_end = label_start + len(label)
        label_span[rid] = (row, label_start, label_end)
        for i, ch in enumerate(label):
            if 0 <= row < canvas_h and 0 <= label_start + i < canvas_w:
                canvas[row][label_start + i] = ch

    for rid in same_z:
        if rid not in label_span:
            continue
        row_a, start_a, end_a = label_span[rid]
        for direction, dest in graph.get(rid, {}).items():
            if dest not in label_span:
                continue
            delta = world_store.coord_delta(direction)
            if delta is None or delta[2] != 0:
                continue
            row_b, start_b, _ = label_span[dest]
            if delta[0] == 1 and row_a == row_b:  # east
                for c in range(end_a, start_b):
                    if 0 <= c < canvas_w and canvas[row_a][c] == ' ':
                        canvas[row_a][c] = '─'
            elif delta[1] == 1:  # south
                center_col = (start_a + end_a) // 2
                for r in range(row_a + 1, row_b):
                    if (0 <= r < canvas_h and 0 <= center_col < canvas_w
                            and canvas[r][center_col] == ' '):
                        canvas[r][center_col] = '│'

    grid_lines = ["".join(r).rstrip() for r in canvas]
    out = "\n".join(grid_lines)

    cur_graph = graph.get(current_room_id, {})
    notes: list[str] = []
    for direction in ("up", "down"):
        dest = cur_graph.get(direction)
        if dest and dest in placed:
            arrow = "↑" if direction == "up" else "↓"
            notes.append(f"  {arrow} {direction}: {names.get(dest, dest)}")
    if notes:
        out += "\n\nVertical exits from here:\n" + "\n".join(notes)

    if other_z:
        out += "\n\nVisited rooms on other layers:"
        for rid, z in other_z:
            out += f"\n  • {names[rid]}  (z={z})"

    return out
