"""The vehicle inspector: what the engine knows about one vehicle, for the browser.

The browser picks a vehicle by its frame id (``vid mod 65536``, frames.py). The first message
resolves it to the live vehicle and pins its full id; from then on one ``vehicle`` message is
sent with every frame until the vehicle leaves the network, then a last one with ``gone`` and
the exit time. Everything is read from the engine state, nothing is estimated:

  * class and its IDM parameters, and the global MOBIL parameters;
  * origin, destination, the road sequence of its route;
  * current lane or connector, speed, last applied acceleration;
  * delay so far = (now - t_gen) - free-flow time of its pair and class (the KPI definition,
    engine/freeflow.py); it can only grow, so while the trip is under way it is a lower bound
    of the final delay;
  * lane changes so far, counted from the engine's lane-change log.
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.params import driving
from trafficsim.engine.vehicle import VEHICLE_CLASSES

ID_MASK = 0xFFFF


class Inspector:
    def __init__(self) -> None:
        self.frame_id: int | None = None
        self.vid: int | None = None
        self._lc_ptr = 0
        self._lc = 0

    @property
    def active(self) -> bool:
        return self.frame_id is not None

    def select(self, frame_id: int | None) -> None:
        self.frame_id, self.vid, self._lc_ptr, self._lc = frame_id, None, 0, 0

    def _lane_changes(self, sim) -> int:
        log = sim.log.lane_changes
        for e in log[self._lc_ptr :]:
            self._lc += e.vid == self.vid
        self._lc_ptr = len(log)
        return self._lc

    def message(self, sim) -> dict | None:
        """The ``vehicle`` message for the current step, or None when nothing is selected."""
        if self.frame_id is None:
            return None
        vs = sim.vehicles
        if self.vid is None:
            rows = np.flatnonzero((vs.vid & ID_MASK) == self.frame_id)
            self.vid = int(vs.vid[rows[0]]) if rows.size else -1
        rows = np.flatnonzero(vs.vid == self.vid)
        if rows.size == 0:
            exits = [e for e in sim.log.exits if e.vid == self.vid]
            msg = {"type": "vehicle", "id": self.frame_id, "gone": True,
                   "t_exit": round(exits[-1].t_exit, 1) if exits else None,
                   "lane_changes": self._lane_changes(sim) if self.vid >= 0 else 0}  # fmt: skip
            self.select(None)  # the vehicle is gone: stop sending
            return msg
        return self._live(sim, int(rows[0]))

    def _live(self, sim, i: int) -> dict:
        vs, lg, rt = sim.vehicles, sim.lg, sim.routes
        route, cls = int(vs.route[i]), int(vs.cls[i])
        pair = rt.pair[route]
        c = VEHICLE_CLASSES[cls]
        ref = getattr(sim.kpis, "delay_ref", None)
        free_flow = ref.free_flow(pair, cls) if ref else None
        t = sim.time_s
        seg = int(vs.seg[i])
        return {
            "type": "vehicle", "id": self.frame_id, "vid": self.vid, "gone": False,
            "t": round(t, 1), "class": c.name,
            "idm": {"length_m": c.length_m, "width_m": c.width_m, "v0_mps": c.v0_mps,
                    "T_s": c.T_s, "a_mps2": c.a_mps2, "b_mps2": c.b_mps2, "s0_m": c.s0_m},
            "mobil": {"politeness": driving.MOBIL_POLITENESS,
                      "threshold_mps2": driving.MOBIL_THRESHOLD_MPS2,
                      "keep_left_bias_mps2": driving.KEEP_LEFT_BIAS_MPS2,
                      "b_safe_mps2": driving.MOBIL_B_SAFE_MPS2,
                      "cooldown_s": driving.LC_COOLDOWN_S},
            "origin": pair[0], "destination": pair[1], "route": list(rt.roads[route]),
            "road": lg.road_of[seg], "lane": lg.ids[seg], "s_m": round(float(vs.s[i]), 1),
            "speed_mps": round(float(vs.v[i]), 2), "acc_mps2": round(float(vs.acc[i]), 2),
            "t_gen": round(float(vs.t_gen[i]), 1), "t_ins": round(float(vs.t_ins[i]), 1),
            "free_flow_s": None if free_flow is None else round(free_flow, 1),
            "delay_s": None if free_flow is None else round(t - float(vs.t_gen[i]) - free_flow, 1),
            "lane_changes": self._lane_changes(sim),
        }  # fmt: skip
