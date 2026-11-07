"""Road-level fastest-path routing by free-flow travel time.

Cost of a road = its length / its speed limit; cost of a connector = its path length /
the lower speed limit of the two roads it joins. Ties are broken by road id, so routes
are deterministic. Lane choice along the route is left to the lane-change model.
"""

from __future__ import annotations

import heapq

from trafficsim.network.types import Network


def road_graph(net: Network) -> dict[str, list[tuple[str, float]]]:
    """Adjacency: road -> [(next road, connector traversal time [s])], deduplicated."""
    best: dict[tuple[str, str], float] = {}
    for c in net.connectors:
        a, b = net.road_of(c.from_lane), net.road_of(c.to_lane)
        t = c.length_m / min(a.speed_limit_mps, b.speed_limit_mps)
        key = (a.id, b.id)
        if key not in best or t < best[key]:
            best[key] = t
    graph: dict[str, list[tuple[str, float]]] = {r.id: [] for r in net.roads}
    for (a, b), t in sorted(best.items()):
        graph[a].append((b, t))
    return graph


def free_flow_time(net: Network, road_id: str) -> float:
    r = net.road(road_id)
    return r.length_m / r.speed_limit_mps


def grade_separated_roads(net: Network) -> frozenset[str]:
    """Roads of the flyover: the deck and its ramps (what "flyover closed" removes)."""
    return frozenset(r.id for r in net.roads if r.kind in ("flyover", "ramp"))


def shortest_road_path(
    net: Network, start: str, goal: str, closed: frozenset[str] = frozenset()
) -> list[str] | None:
    """Fastest road sequence from road ``start`` to road ``goal`` avoiding ``closed`` roads.

    ``start`` itself may be closed (a vehicle already on it finishes its trip)."""
    graph = road_graph(net)
    dist = {start: free_flow_time(net, start)}
    prev: dict[str, str] = {}
    heap = [(dist[start], start)]
    while heap:
        d, rid = heapq.heappop(heap)
        if d > dist.get(rid, float("inf")):
            continue
        if rid == goal:
            path = [rid]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return path[::-1]
        for nxt, t_conn in graph[rid]:
            if nxt in closed:
                continue
            nd = d + t_conn + free_flow_time(net, nxt)
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                prev[nxt] = rid
                heapq.heappush(heap, (nd, nxt))
    return None


def fastest_route(
    net: Network, origin_zone: str, destination_zone: str, closed: frozenset[str] = frozenset()
) -> list[str] | None:
    """Sequence of road ids from the origin's entry road to the destination's exit road."""
    return shortest_road_path(
        net, net.zone(origin_zone).entry_road, net.zone(destination_zone).exit_road, closed
    )


def route_free_flow_time(net: Network, route: list[str]) -> float:
    graph = road_graph(net)
    total = free_flow_time(net, route[0])
    for a, b in zip(route[:-1], route[1:], strict=True):
        total += dict(graph[a])[b] + free_flow_time(net, b)
    return total
