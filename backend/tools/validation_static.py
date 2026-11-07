"""Known differences from HCM, as documented in the README (not recomputed by the tool).

These were measured with ad-hoc experiments when they were written; the numbers are copied from
the README ("Known differences from HCM"), and the Validation tab marks them as documented.
The measured items (validation_measure.py) are regenerated; these are not.
"""

DOCUMENTED = [
    {
        "id": "known_j2_right", "kind": "documented",
        "title": "Known difference: the J2 right turn serves 64% of HCM",
        "what": "132 against 207 veh/h at 980 veh/h conflicting flow. Nothing was tuned to "
        "close the gap. Attribution from the same run (saturated right turn):",
        "bullets": [
            "Fewer usable gaps than random arrivals (largest): gaps of at least 7.5 s occur 52 "
            "times per hour against 127 for a random stream of the same flow; the merged "
            "conflicting stream has a headway CV of 1.77 (1.0 for random). Where the bunching "
            "comes from is a hypothesis (the J1 signal, the lane drop, the flyover merge); not "
            "isolated.",
            "Partly offset: in a bunched stream the gaps that occur are longer, so each usable "
            "gap serves 2.5 vehicles against about 1.6 in HCM's formula.",
            "Follow-up headway: consecutive right-turners enter 4.36 s apart against HCM's "
            "3.5 s (the right-turn path is 24.8 m long and curvature-limited to about 21 km/h); "
            "worth up to about -20% for the second and later vehicles in a gap.",
            "Small: a vehicle must be at the line when the window opens (2 of 15 windows unused).",
        ],
        "reference": {"text": "HCM two-way stop-controlled capacity formula.",
                      "source": "HCM 6th ed., Ch. 20; README, Known differences from HCM"},
        "commands": ["cd backend && .venv/Scripts/python -m pytest "
                     "tests/engine/test_j2_minor_lanes.py -s -k hcm"],
    },
    {
        "id": "known_saturation", "kind": "documented",
        "title": "Known difference: stop-line saturation flow is about 1,630 veh/h, not 1,900",
        "what": "Measured, not assumed (a standing queue is released and the headways after the "
        "fourth vehicle are averaged). It decomposes for cars at J1's through movement:",
        "table": {"columns": ["experiment", "flow veh/h"], "rows": [
            ["steady-state maximum on a ring at J1's desired speed (39 km/h)", 1766],
            ["J1 queue discharge, same parameters", 1644],
            ["steady-state maximum on a ring at a 59 km/h desired speed", 2074],
            ["J1 queue discharge at a 60 km/h desired speed", 1772],
            ["the same, and a = 1.5 m/s^2", 1977]]},
        "bullets": [
            "Desired-speed ceiling: for IDM the steady flow is q(v) = v / (L + s*(v)); the "
            "(v/v0)^4 term widens the equilibrium gap near v0, so at a 40 km/h urban limit the "
            "best steady flow is about 1,766 veh/h.",
            "Start-up transient: a queue is released at a = 1.0 m/s^2 (a comfortable urban "
            "acceleration); the first four headways are 4.2, 3.1, 2.8 and 2.7 s against a "
            "steady 2.15 s, so the discharge stays about 7% below the steady-state ceiling.",
            "HCM's 1,900 comes from field data at higher speed limits with faster drivers; "
            "reproducing it needs both a higher desired speed and a = 1.5 m/s^2, i.e. a "
            "different parameter set. Sensitivities: a 1.0 to 1.5 gives +6%, T 1.0 to 1.2 "
            "gives -8%, v0 40 to 60 km/h gives +8%.",
            "This is not the motorway 'capacity drop' (jam outflow below free-flow capacity), "
            "which appears on the ring road.",
        ],
        "reference": {"text": "HCM base saturation flow 1,900 pc/h/ln.",
                      "source": "HCM 6th ed., Ch. 19; README, Known differences from HCM"},
        "commands": ["cd backend && .venv/Scripts/python -m pytest "
                     "tests/validation/test_capacity.py -s -k saturation"],
    },
]  # fmt: skip
