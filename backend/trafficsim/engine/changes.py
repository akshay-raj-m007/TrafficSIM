"""Live changes: validated, applied at a tick boundary, logged with that tick.

``Simulation.schedule(change)`` queues a change for the start of the next step (or for a
given future tick); ``step`` applies everything due *before* phase 1 of that tick and
appends ``(tick, change)`` to ``Simulation.change_log``. A run is therefore reproduced
exactly by the same seed, scenario and change log (``Scenario.changes`` replays one).

Closing the flyover
-------------------
The ramps stop accepting new vehicles: arrivals and entry queues are re-routed over the
surface, and so is every vehicle that can still do so. A vehicle on the deck or a ramp
finishes its trip (it cannot turn round). A vehicle upstream of the diverge is re-routed
from its current road unless it could not make the lane changes the new route needs in
the distance left: ``lanes to cross x LC_COOLDOWN_S x road speed limit`` (a vehicle
changes at most one lane per cooldown). That vehicle keeps its flyover route
("grandfathered"): stranding it at the end of a lane that no longer leads anywhere would
block the lane. Reopening applies the same rule in reverse.

Delay is measured against the fastest free-flow route on the fully OPEN network for the
vehicle's origin and destination (engine/freeflow.py ``DelayReference``), so the extra time a
closure causes counts as delay for everyone, re-routed or not.
"""

from __future__ import annotations

from trafficsim.engine.params.driving import LC_COOLDOWN_S
from trafficsim.engine.routes import lane_offset_to_good, next_seg, refresh_lane_cache
from trafficsim.engine.scenario import Change, SetDemand, SetFlyover, SetMix, SetPolicy
from trafficsim.network.routing import grade_separated_roads


def apply_change(sim, change: Change) -> None:
    if isinstance(change, SetDemand):
        sim.demand.set_demand(change.flows, sim.time_s)
        sim.current_demand = change.flows
    elif isinstance(change, SetMix):
        sim.demand.set_mix(change.mix)
        sim.current_mix = change.mix
    elif isinstance(change, SetPolicy):
        switch_policy(sim, change.policy)
    elif isinstance(change, SetFlyover):
        set_flyover(sim, change.open)
    else:  # pragma: no cover - the type union is closed
        raise TypeError(f"unknown change {change!r}")


def schedule_change(sim, change: Change, tick: int | None = None) -> int:
    """Validate now (ValueError with a clear message), queue for the start of ``tick``, apply it
    before phase 1 of that tick and log it with the tick it was applied at. Returns that tick."""
    at = sim.tick if tick is None else tick
    if at < sim.tick:
        raise ValueError(f"cannot change the past: tick {at} < current tick {sim.tick}")
    if at > sim._total_ticks:
        raise ValueError(
            f"tick {at} is after the end of the run (tick {sim._total_ticks}): "
            "the change would never be applied"
        )
    check_change(sim, change)
    if isinstance(change, SetFlyover):
        sim.flyover_pending = change.open
    sim._pending.append((at, change))
    sim._pending.sort(key=lambda p: p[0])  # stable: same-tick changes keep their order
    return at


def apply_due(sim) -> None:
    while sim._pending and sim._pending[0][0] <= sim.tick:
        _, change = sim._pending.pop(0)
        apply_change(sim, change)
        sim.change_log.append((sim.tick, change))


def check_change(sim, change: Change) -> None:
    """Reject, with a clear message, a change that cannot apply to this simulation."""
    if isinstance(change, SetPolicy) and not sim.signals:
        raise ValueError("this scenario has no signals (uncontrolled): the policy cannot change")
    if isinstance(change, SetFlyover) and change.open == sim.flyover_pending:
        raise ValueError(f"the flyover is already {'open' if change.open else 'closed'}")
    if isinstance(change, SetDemand):
        zones = {z.zone_id for z in sim.demand.zones}
        for f in change.flows:
            if f.origin not in zones or f.destination not in zones:
                raise ValueError(f"demand {f.origin}->{f.destination}: unknown zone")


def switch_policy(sim, policy: str) -> None:
    """New controller continues in the current phase and state (same amber / all-red), so
    two conflicting greens cannot occur; it decides for itself from the next green on. It is
    built from the DESIGN record of the scenario (saturation flows of the initial mix, Webster
    plan of the initial demand): live changes of mix or demand do not retime the signals."""
    from trafficsim.engine.signals import make_controllers

    new = make_controllers(sim.design, policy, sim.lg)
    for old, ctrl in zip(sim.signals, new, strict=True):
        ctrl.phase, ctrl.state, ctrl.elapsed = old.phase, old.state, old.elapsed
        ctrl.next_phase, ctrl.history = old.next_phase, old.history
    sim.signals[:] = new
    sim.policy = policy


def set_flyover(sim, open_: bool) -> None:
    sim.flyover_open = open_
    rt = sim.routes
    rt.closed = frozenset() if open_ else grade_separated_roads(sim.network)
    sim.demand.refresh_routes()
    sim.demand.remap_queued()
    sim.kpis.request_reference()
    reroute_active(sim, closing=not open_)


def reroute_active(sim, closing: bool) -> None:
    """Re-route vehicles that can still choose. A vehicle on a junction connector chooses
    from the road it is entering (its first lane is the connector's exit lane)."""
    vs, lg, rt = sim.vehicles, sim.lg, sim.routes
    fly = grade_separated_roads(sim.network)
    for i in range(vs.n):  # row order is deterministic
        seg = int(vs.seg[i])
        route, rpos = int(vs.route[i]), int(vs.rpos[i])
        if lg.is_conn[seg]:
            lane, pos = int(lg.conn_to[seg]), rpos + 1
            room = float(lg.length[seg] - vs.s[i] + lg.length[lane])
        else:
            lane, pos, room = seg, rpos, float(lg.length[seg] - vs.s[i])
        if lg.road_of[lane] in fly:  # on the flyover or entering it: finishes its trip
            continue
        new = rt.reroute(sim.network, lg, route, pos)
        if new is None or new == route:
            continue
        lanes = abs(lane_offset_to_good(rt, new, pos, int(lg.lane_index[lane])))
        if lanes and room < lanes * LC_COOLDOWN_S * float(lg.vlimit[lane]):
            if closing:
                sim.grandfathered_vids.add(int(vs.vid[i]))
            continue
        vs.route[i] = new
        if not lg.is_conn[seg]:
            refresh_lane_cache(vs, lg, rt, i)
            vs.nxt[i] = next_seg(lg, rt, new, rpos, seg)
        sim.rerouted += 1
