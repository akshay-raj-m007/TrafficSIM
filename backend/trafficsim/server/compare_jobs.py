"""Background comparison jobs: process pool, per-run cache, progress, concurrency cap.

One task = one run (a scenario, a seed). Finished runs are cached on disk by a key that
covers everything that determines them, so the same comparison never runs twice and two
comparisons that share runs (the built-in experiments share their rush-hour Webster runs)
pay for them once. At most ``CompareLimits.max_jobs`` jobs run at once; another request
gets ``CompareBusy`` (HTTP 429) instead of a queue that can grow without bound.
"""

from __future__ import annotations

import itertools
import json
import multiprocessing
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import Executor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from trafficsim.network.demo import build_demo_network
from trafficsim.server.compare_spec import CompareLimits, assemble, run_specs, validate
from trafficsim.server.scenario_doc import parse, to_engine


class CompareBusy(RuntimeError):
    pass


def run_one(spec: dict) -> dict:
    """Worker (top level, so a process pool can pickle it): one run -> metrics + CPU time."""
    from trafficsim.engine.runmetrics import run_metrics

    t0 = time.process_time()
    doc = parse(spec["doc"])
    metrics = run_metrics(
        build_demo_network(doc.structure.j2_minor_lanes), to_engine(doc), spec["warmup_s"]
    )
    return {"key": spec["key"], "metrics": metrics, "cpu_s": time.process_time() - t0}


class RunCache:
    """Per-run results by key: an in-memory layer (preloaded shipped results) over files."""

    def __init__(self, directory: Path | None) -> None:
        self.dir = directory
        self.memory: dict[str, dict] = {}
        if directory:
            directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict | None:
        if key in self.memory:
            return self.memory[key]
        if self.dir and (p := self.dir / f"{key}.json").exists():
            self.memory[key] = json.loads(p.read_text(encoding="utf-8"))
            return self.memory[key]
        return None

    def put(self, key: str, result: dict) -> None:
        self.memory[key] = result
        if self.dir:
            tmp = self.dir / f"{key}.tmp"
            tmp.write_text(json.dumps(result), encoding="utf-8")
            tmp.replace(self.dir / f"{key}.json")


@dataclass
class Job:
    id: str
    total: int
    done: int = 0
    cached: int = 0
    state: str = "running"  # running | done | error | cancelled
    result: dict | None = None
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    t0: float = field(default_factory=time.perf_counter)

    def to_dict(self) -> dict:
        return {"id": self.id, "state": self.state, "total": self.total, "done": self.done,
                "cached": self.cached, "error": self.error, "result": self.result,
                "elapsed_s": round(time.perf_counter() - self.t0, 1)}  # fmt: skip


def default_workers(limits: CompareLimits) -> int:
    return limits.workers or max(1, min(4, (os.cpu_count() or 2) - 1))


class CompareManager:
    def __init__(self, limits: CompareLimits, cache: RunCache,
                 executor_factory: Callable[[int], Executor] | None = None) -> None:  # fmt: skip
        self.limits, self.cache = limits, cache
        self._factory = executor_factory or (
            lambda n: ProcessPoolExecutor(
                max_workers=n, mp_context=multiprocessing.get_context("spawn")
            )
        )
        self._executor: Executor | None = None
        self._jobs: dict[str, Job] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    @property
    def running(self) -> int:
        return sum(j.state == "running" for j in self._jobs.values())

    def submit(self, raw: dict) -> Job:
        """Validate (CompareError), enforce the job cap (CompareBusy), start the job."""
        v = validate(raw, self.limits)
        specs = run_specs(v)
        with self._lock:
            if self.running >= self.limits.max_jobs:
                raise CompareBusy(
                    f"{self.running} comparison(s) already running (limit {self.limits.max_jobs}); "
                    "try again when one finishes"
                )
            job = Job(f"c{next(self._ids)}", total=len({sp["key"] for sp in specs}))
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, v, specs), daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _pool(self) -> Executor:
        if self._executor is None:
            self._executor = self._factory(default_workers(self.limits))
        return self._executor

    def _run(self, job: Job, v, specs: list[dict]) -> None:
        try:
            results: dict[str, dict] = {}
            todo: list[dict] = []
            for sp in specs:  # identical runs (A vs A, shared runs) are computed once
                if sp["key"] in results or sp["key"] in {t["key"] for t in todo}:
                    continue
                hit = self.cache.get(sp["key"])
                if hit is not None:
                    results[sp["key"]] = hit
                    job.done += 1
                    job.cached += 1
                else:
                    todo.append(sp)
            futures = {self._pool().submit(run_one, sp): sp for sp in todo}
            for fut in as_completed(futures):
                if job.cancel.is_set():
                    for f in futures:
                        f.cancel()
                    job.state = "cancelled"
                    return
                r = fut.result()
                self.cache.put(r["key"], r)
                results[r["key"]] = r
                job.done += 1
            wall = time.perf_counter() - job.t0
            cpu = sum(results[sp["key"]]["cpu_s"] for sp in todo)
            workers = default_workers(self.limits)
            cost = {"cpu_s": round(cpu, 1), "wall_s": round(wall, 1), "workers": workers,
                    "cached_runs": job.cached, "computed_runs": len(todo)}  # fmt: skip
            job.result = assemble(v, results, cost)
            job.state = "done"
        except Exception as exc:  # report, never hang the poller
            job.state, job.error = "error", f"{type(exc).__name__}: {exc}"

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job.state == "running":
            job.cancel.set()
            return True
        return False

    def shutdown(self) -> None:
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
