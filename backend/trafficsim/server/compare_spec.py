"""A/B comparison request: validation, run specs, cache keys and result assembly.

A request names two scenario documents (A and B), a number of paired runs, a duration and
a warm-up. Run i of A and run i of B use the same seed ``base_seed + i`` (paired runs /
common random numbers: arrivals are drawn when a vehicle is generated, independent of
the network state, so A and B see identical demand when demand and mix match; the result
says when they do not). Nothing is clamped: limits and invalid input are errors.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from trafficsim.engine.constants import DT
from trafficsim.engine.pairedstats import paired_difference
from trafficsim.engine.runmetrics import METRICS, METRICS_VERSION
from trafficsim.engine.sourcedigest import source_digest
from trafficsim.network.structure import Structure as NetStructure
from trafficsim.server.scenario_doc import MAX_SEED, ScenarioError, parse

ALLOWED_RUNS: Final[tuple[int, ...]] = (3, 5, 10)
DEFAULT_WARMUP_S: Final[float] = 300.0  # > longest free-flow trip (242 s), see README
DEFAULT_DURATION_S: Final[float] = 900.0
MULTIPLE_COMPARISONS_NOTE: Final[str] = (
    "About a dozen metrics are compared at once with unadjusted 95% intervals: one "
    "'significant' among them is expected by chance now and then, so read a single one with care."
)


class CompareError(ValueError):
    def __init__(self, items: list[dict[str, str]]) -> None:
        self.items = items
        super().__init__("; ".join(f"{i['path']}: {i['message']}" for i in items))


@dataclass(frozen=True, slots=True)
class CompareLimits:
    """What a (hosted) server allows; every field is a config knob (server/config.py)."""

    max_runs: int = 10
    max_duration_s: float = 1800.0
    max_jobs: int = 1  # comparison jobs running at once
    workers: int = 0  # worker processes; 0 = automatic


@dataclass(frozen=True, slots=True)
class Validated:
    a: dict  # validated scenario documents
    b: dict
    runs: int
    duration_s: float
    warmup_s: float
    base_seed: int

    @property
    def seeds(self) -> list[int]:
        return [self.base_seed + i for i in range(self.runs)]


def _is_tick_multiple(x: float) -> bool:
    return abs(x / DT - round(x / DT)) < 1e-6


def validate(raw: dict, limits: CompareLimits) -> Validated:
    errors: list[dict[str, str]] = []
    err = lambda path, msg: errors.append({"path": path, "message": msg})  # noqa: E731
    if not isinstance(raw, dict):
        raise CompareError([{"path": "(request)", "message": "must be a JSON object"}])
    extra = set(raw) - {"a", "b", "runs", "duration_s", "warmup_s", "base_seed"}
    for k in sorted(extra):
        err(k, "unknown field")
    runs = raw.get("runs", 5)
    if runs not in ALLOWED_RUNS:
        err("runs", f"must be one of {list(ALLOWED_RUNS)}, got {runs!r}")
    elif runs > limits.max_runs:
        err("runs", f"this server allows at most {limits.max_runs} runs, got {runs}")
    dur = raw.get("duration_s", DEFAULT_DURATION_S)
    warm = raw.get("warmup_s", DEFAULT_WARMUP_S)
    base = raw.get("base_seed", 1)
    num = lambda v: isinstance(v, int | float) and not isinstance(v, bool) and v == v  # noqa: E731
    if not num(dur) or dur <= 0 or not _is_tick_multiple(dur):
        err("duration_s", f"must be a positive multiple of {DT} s, got {dur!r}")
    elif dur > limits.max_duration_s:
        err("duration_s", f"this server allows at most {limits.max_duration_s:g} s, got {dur:g}")
    if not num(warm) or warm < 0 or not _is_tick_multiple(warm):
        err("warmup_s", f"must be a non-negative multiple of {DT} s, got {warm!r}")
    elif num(dur) and warm >= dur:
        err("warmup_s", f"warm-up {warm:g} s must be shorter than the duration {dur:g} s")
    if not isinstance(base, int) or isinstance(base, bool) or not 0 <= base <= MAX_SEED - 10:
        err("base_seed", f"must be a whole number from 0 to {MAX_SEED - 10}, got {base!r}")
    docs = {}
    for side in ("a", "b"):
        if not isinstance(raw.get(side), dict):
            err(side, "scenario document required")
            continue
        doc = deepcopy(raw[side])
        if num(dur) and dur > 0:
            doc["duration_s"] = dur  # the comparison's duration replaces the document's
        if isinstance(base, int):
            doc["seed"] = base  # replaced per run; validated here once
        try:
            parse(doc)
        except ScenarioError as exc:
            errors += [{"path": f"{side}.{i['path']}", "message": i["message"]} for i in exc.items]
        docs[side] = doc
    if errors:
        raise CompareError(errors)
    return Validated(docs["a"], docs["b"], runs, float(dur), float(warm), base)


@lru_cache(maxsize=32)
def model_digest(structure: NetStructure) -> str:
    """Digest of the network and every model constant (same one that guards the tables)."""
    from trafficsim.engine.freeflow import input_digest
    from trafficsim.engine.lanegraph import compile_network
    from trafficsim.network.demo import build_demo_network

    net = build_demo_network(structure)
    return input_digest(net, compile_network(net))


def run_key(doc: dict, warmup_s: float) -> str:
    """Cache key of one run: everything that determines it (the name is only a label)."""
    body = {k: v for k, v in doc.items() if k != "name"}
    payload = {
        "doc": body,
        "warmup_s": warmup_s,
        "metrics_version": METRICS_VERSION,
        "model": model_digest(NetStructure(**doc["structure"])),
        "source": source_digest(),  # engine / network logic, not only constants
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def run_specs(v: Validated) -> list[dict]:
    """One spec per (side, seed): everything the worker needs, picklable."""
    specs = []
    for side, base in (("a", v.a), ("b", v.b)):
        for seed in v.seeds:
            doc = deepcopy(base)
            doc["seed"] = seed
            specs.append({"side": side, "seed": seed, "doc": doc, "warmup_s": v.warmup_s,
                          "key": run_key(doc, v.warmup_s)})  # fmt: skip
    return specs


def _demand_total(doc: dict) -> float:
    return float(sum(r["veh_per_h"] for r in doc["initial"]["demand"]))


def pairing(a: dict, b: dict) -> tuple[bool, str | None]:
    """Do A and B generate the same arrivals? (same initial demand and mix and the same
    demand / mix changes)."""
    keyed = lambda d: sorted((r["origin"], r["destination"], r["veh_per_h"])  # noqa: E731
                             for r in d)  # fmt: skip
    same_demand = keyed(a["initial"]["demand"]) == keyed(b["initial"]["demand"])
    same_mix = a["initial"]["mix"] == b["initial"]["mix"]
    sel = lambda d: [c for c in d["changes"] if c["type"] in ("set_demand", "set_mix")]  # noqa: E731
    same_changes = sel(a) == sel(b)
    if same_demand and same_mix and same_changes:
        return True, None
    return (
        False,
        "A and B differ in demand or mix: arrivals are not paired (same seed, different demand).",
    )


def assemble(v: Validated, results: dict[str, dict], cost: dict) -> dict:
    """The comparison: one paired-difference row per metric, plus the per-run values."""
    per_side = {s: [results[sp["key"]] for sp in run_specs(v) if sp["side"] == s] for s in "ab"}
    rows = []
    for mid, (label, unit) in METRICS.items():
        pd = paired_difference([r["metrics"][mid] for r in per_side["a"]],
                               [r["metrics"][mid] for r in per_side["b"]])  # fmt: skip
        rows.append({"id": mid, "label": label, "unit": unit, **pd})
    ok, why = pairing(v.a, v.b)
    describe = lambda d: {  # noqa: E731
        "name": d["name"], "demand_veh_h": _demand_total(d),
        "structure": d["structure"], "policy": d["initial"]["policy"],
        "flyover_open": d["initial"]["flyover_open"], "changes": len(d["changes"]),
    }  # fmt: skip
    mean_counts = lambda rs: {  # noqa: E731
        k: sum(r["metrics"]["counts"][k] for r in rs) / len(rs)
        for k in ("cohort", "completed", "unfinished", "too_young")
    }  # fmt: skip
    return {
        "meta": {
            "runs": v.runs, "seeds": v.seeds, "duration_s": v.duration_s,
            "warmup_s": v.warmup_s, "base_seed": v.base_seed, "metrics_version": METRICS_VERSION,
            "a": describe(v.a), "b": describe(v.b), "paired_arrivals": ok, "pairing_note": why,
            "mean_counts": {s: mean_counts(per_side[s]) for s in "ab"}, "cost": cost,
        },
        "metrics": rows,
        "runs": {s: [{"seed": sd, **{k: r[k] for k in ("key", "metrics", "cpu_s")}}
                     for sd, r in zip(v.seeds, per_side[s], strict=True)] for s in "ab"},
        "note": MULTIPLE_COMPARISONS_NOTE,
    }  # fmt: skip
