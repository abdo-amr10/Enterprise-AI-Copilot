"""Offline latency audit analysis script for Enterprise AI Copilot.

Parses structured JSONL audit logs, correlates events strictly by request_id,
and generates comprehensive statistical breakdowns, percentiles (P50/P90/P95/P99),
throughput metrics, and forensic anomaly alerts.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def percentile(data: list[float], pct: float) -> float:
    """Calculate the given percentile (0.0 to 100.0) using linear interpolation."""
    if not data:
        return 0.0
    sorted_d = sorted(data)
    if len(sorted_d) == 1:
        return sorted_d[0]
    k = (len(sorted_d) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_d[int(k)]
    d0 = sorted_d[int(f)] * (c - k)
    d1 = sorted_d[int(c)] * (k - f)
    return d0 + d1


def avg(data: list[float]) -> float:
    return sum(data) / len(data) if data else 0.0


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title.upper()}")
    print("=" * 80)


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs/latency_audit.jsonl")

    if not log_path.exists():
        print(f"[!] Audit log file not found at: {log_path.resolve()}")
        print("    Run pipeline requests first to generate audit telemetry.")
        return

    events: list[dict[str, Any]] = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception as e:
                print(f"[!] Skipped malformed JSON on line {line_num}: {e}")

    if not events:
        print(f"[!] Audit log file is empty: {log_path}")
        return

    print_section(f"Latency Audit Report: {log_path.name}")
    print(f"Total Log Events Loaded: {len(events)}")

    # Strictly partition events by request_id
    requests_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    standalone_events: list[dict[str, Any]] = []

    for ev in events:
        req_id = ev.get("request_id")
        if req_id:
            requests_map[req_id].append(ev)
        else:
            standalone_events.append(ev)

    # 1. Pipeline Request Overview
    summaries: list[dict[str, Any]] = []
    for req_id, req_events in requests_map.items():
        summary_ev = next((e for e in req_events if e.get("event") == "request_summary"), None)
        if summary_ev:
            summaries.append(summary_ev)

    if summaries:
        total_reqs = len(summaries)
        successful_reqs = sum(1 for s in summaries if s.get("success", False))
        failed_reqs = total_reqs - successful_reqs

        total_latencies = [float(s.get("total_duration_ms", 0.0)) for s in summaries]
        unaccounted_latencies = [float(s.get("unaccounted_ms", 0.0)) for s in summaries]

        print_section("1. Pipeline Request Overview (Correlated by Request ID)")
        print(f"  Total Pipeline Requests : {total_reqs}")
        print(f"  Successful Requests     : {successful_reqs} ({successful_reqs/total_reqs*100:.1f}%)")
        print(f"  Failed Requests         : {failed_reqs} ({failed_reqs/total_reqs*100:.1f}%)")
        print("-" * 80)
        print(f"  Total Latency Avg       : {avg(total_latencies):,.2f} ms ({avg(total_latencies)/1000:.2f} s)")
        print(f"  Total Latency P50       : {percentile(total_latencies, 50):,.2f} ms")
        print(f"  Total Latency P90       : {percentile(total_latencies, 90):,.2f} ms")
        print(f"  Total Latency P95       : {percentile(total_latencies, 95):,.2f} ms")
        print(f"  Total Latency P99       : {percentile(total_latencies, 99):,.2f} ms")
        print(f"  Total Latency Min / Max : {min(total_latencies):,.2f} ms / {max(total_latencies):,.2f} ms")
        print("-" * 80)
        overall_avg = avg(total_latencies) or 1.0
        print(f"  Unaccounted Latency Avg : {avg(unaccounted_latencies):,.2f} ms ({avg(unaccounted_latencies)/overall_avg*100:.1f}%)")
        print(f"  Unaccounted Latency P95 : {percentile(unaccounted_latencies, 95):,.2f} ms")

        # 2. Stage Breakdown (Correlated Leaf Spans)
        stage_times: dict[str, list[float]] = defaultdict(list)
        for s in summaries:
            leaf_stages = s.get("leaf_stages_ms", {})
            for stg, dur in leaf_stages.items():
                stage_times[stg].append(float(dur))

        if stage_times:
            print_section("2. Stage Latency Breakdown (Correlated Leaf Spans)")
            print(f"{'STAGE':<28} | {'AVG (ms)':<10} | {'P50 (ms)':<10} | {'P95 (ms)':<10} | {'MAX (ms)':<10} | {'% TOTAL':<8}")
            print("-" * 86)
            for stg, times in sorted(stage_times.items(), key=lambda item: avg(item[1]), reverse=True):
                stg_avg = avg(times)
                stg_p50 = percentile(times, 50)
                stg_p95 = percentile(times, 95)
                stg_max = max(times)
                pct = (stg_avg / overall_avg) * 100.0
                print(f"{stg:<28} | {stg_avg:<10.2f} | {stg_p50:<10.2f} | {stg_p95:<10.2f} | {stg_max:<10.2f} | {pct:<7.1f}%")

    # 3. Pipeline-Correlated LLM Calls
    pipeline_llm_events = [
        e for req_id, req_events in requests_map.items()
        for e in req_events if e.get("event") == "llm_complete"
    ]

    if pipeline_llm_events:
        print_section("3. Pipeline LLM Inference Metrics (Correlated to Requests)")
        print(f"  Total In-Pipeline LLM Invocations: {len(pipeline_llm_events)}")

        stages = sorted(list(set(e.get("stage", "unknown") for e in pipeline_llm_events)))
        for stg in stages:
            stg_llm = [e for e in pipeline_llm_events if e.get("stage") == stg]
            prompt_tokens = [float(e.get("prompt_eval_count") or 0) for e in stg_llm if e.get("prompt_eval_count") is not None]
            output_tokens = [float(e.get("eval_count") or 0) for e in stg_llm if e.get("eval_count") is not None]
            prompt_eval_ms = [float(e.get("prompt_eval_duration_ms") or 0) for e in stg_llm]
            eval_ms = [float(e.get("eval_duration_ms") or 0) for e in stg_llm]
            load_ms = [float(e.get("load_duration_ms") or 0) for e in stg_llm]
            prompt_tps = [float(e.get("prompt_tps") or 0) for e in stg_llm if e.get("prompt_tps")]
            gen_tps = [float(e.get("generation_tps") or 0) for e in stg_llm if e.get("generation_tps")]
            cold_count = sum(1 for e in stg_llm if e.get("is_cold_load"))

            print(f"\n  [Stage: {stg}] ({len(stg_llm)} calls, {cold_count} cold reloads)")
            print(f"    Prompt Tokens Avg / P95   : {avg(prompt_tokens):.1f} / {percentile(prompt_tokens, 95):.1f} tokens")
            print(f"    Output Tokens Avg / P95   : {avg(output_tokens):.1f} / {percentile(output_tokens, 95):.1f} tokens")
            print(f"    Prompt Eval Duration Avg  : {avg(prompt_eval_ms):.2f} ms")
            print(f"    Generation Duration Avg   : {avg(eval_ms):.2f} ms")
            print(f"    Model Load Duration Avg   : {avg(load_ms):.2f} ms")
            print(f"    Prompt Eval Speed (TPS)   : {avg(prompt_tps):.2f} tokens/s (P50: {percentile(prompt_tps, 50):.2f})")
            print(f"    Decode Generation Speed   : {avg(gen_tps):.2f} tokens/s (P50: {percentile(gen_tps, 50):.2f})")

    # 4. Pipeline Prompt Assembly & Truncation Forensics
    pipeline_prompts = [
        e for req_id, req_events in requests_map.items()
        for e in req_events if e.get("event") == "prompt_assembly"
    ]
    if pipeline_prompts or pipeline_llm_events:
        print_section("4. Pipeline Prompt Assembly & Truncation Forensics")
        if pipeline_prompts:
            prompt_chars = [float(p.get("prompt_chars", 0)) for p in pipeline_prompts]
            est_tokens = [float(p.get("estimated_prompt_tokens", 0)) for p in pipeline_prompts]
            print(f"  Total Prompts Assembled   : {len(pipeline_prompts)}")
            print(f"  Prompt Chars Avg / P95    : {avg(prompt_chars):,.1f} / {percentile(prompt_chars, 95):,.1f} chars")
            print(f"  Estimated Tokens Avg / P95: {avg(est_tokens):,.1f} / {percentile(est_tokens, 95):,.1f} tokens")

        truncated_calls = [e for e in pipeline_llm_events if e.get("prompt_truncated") is True]
        trunc_rate = (len(truncated_calls) / len(pipeline_llm_events) * 100.0) if pipeline_llm_events else 0.0
        print(f"  Prompt Truncation Rate    : {trunc_rate:.1f}% ({len(truncated_calls)} / {len(pipeline_llm_events)} LLM calls)")
        if truncated_calls:
            est_lost = [float(e.get("truncated_tokens_estimate") or 0) for e in truncated_calls]
            print(f"  Tokens Truncated Avg      : {avg(est_lost):,.1f} tokens lost per truncated call")

    # 5. AI -> Backend HTTP Calls
    backend_calls = [
        e for req_id, req_events in requests_map.items()
        for e in req_events if e.get("event") == "backend_http_call"
    ]
    if backend_calls:
        print_section("5. Pipeline AI -> Backend HTTP Round-Trip Profile")
        durations = [float(b.get("duration_ms", 0.0)) for b in backend_calls]
        print(f"  Total Backend HTTP Calls  : {len(backend_calls)}")
        print(f"  Round-Trip Latency Avg    : {avg(durations):.2f} ms")
        print(f"  Round-Trip Latency P95    : {percentile(durations, 95):.2f} ms")
        print(f"  Round-Trip Latency Max    : {max(durations):.2f} ms")

        endpoints: dict[str, list[float]] = defaultdict(list)
        for b in backend_calls:
            ep = f"{b.get('http_method', 'GET')} {b.get('endpoint', '/')}"
            endpoints[ep].append(float(b.get("duration_ms", 0.0)))

        print("\n  Endpoint Call Breakdown:")
        for ep, durs in sorted(endpoints.items(), key=lambda item: len(item[1]), reverse=True):
            print(f"    {ep:<45}: {len(durs):>3} calls (Avg: {avg(durs):.1f} ms, P95: {percentile(durs, 95):.1f} ms)")

    # 6. Standalone / Uncorrelated Invocations (Integration Tests or Direct SDK Calls)
    if standalone_events:
        standalone_llm = [e for e in standalone_events if e.get("event") == "llm_complete"]
        if standalone_llm:
            print_section("6. Standalone / Uncorrelated LLM Invocations (Non-Pipeline / Tests)")
            print(f"  Total Standalone LLM Calls (request_id is null): {len(standalone_llm)}")
            for idx, call in enumerate(standalone_llm, 1):
                print(f"\n  [Standalone Call #{idx}]")
                print(f"    Total Duration        : {call.get('total_duration_ms', 0):,.2f} ms ({call.get('total_duration_ms', 0)/1000:.2f} s)")
                print(f"    Model Load Duration   : {call.get('load_duration_ms', 0):,.2f} ms (Cold: {call.get('is_cold_load')})")
                print(f"    Prompt Eval Duration  : {call.get('prompt_eval_duration_ms', 0):,.2f} ms ({call.get('prompt_eval_count')} tokens @ {call.get('prompt_tps')} tok/s)")
                print(f"    Generation Duration   : {call.get('eval_duration_ms', 0):,.2f} ms ({call.get('eval_count')} tokens @ {call.get('generation_tps')} tok/s)")
                print(f"    Options Sent          : {call.get('options_sent')}")

    # 7. Suspicious Patterns & Anomalies
    print_section("7. Suspicious Patterns & Forensic Alerts")
    alerts: list[str] = []

    cold_loads = [e for e in pipeline_llm_events if e.get("is_cold_load")]
    if cold_loads:
        alerts.append(f"[!] COLD MODEL LOADS: {len(cold_loads)} pipeline calls suffered cold load penalties (>1s load duration).")

    truncations = [e for e in pipeline_llm_events if e.get("prompt_truncated") is True]
    if truncations:
        alerts.append(f"[!] PROMPT TRUNCATION: {len(truncations)} pipeline calls exceeded Ollama's slot budget and were truncated.")

    dup_prompts = sum(s.get("counts", {}).get("duplicate_prompts", 0) for s in summaries)
    if dup_prompts > 0:
        alerts.append(f"[!] DUPLICATE PROMPTS: {dup_prompts} identical prompts assembled across requests.")

    dup_sql = sum(s.get("counts", {}).get("duplicate_sql", 0) for s in summaries)
    if dup_sql > 0:
        alerts.append(f"[!] DUPLICATE SQL VALIDATIONS: {dup_sql} identical SQL strings validated.")

    dup_backend = sum(s.get("counts", {}).get("duplicate_backend_calls", 0) for s in summaries)
    if dup_backend > 0:
        alerts.append(f"[!] DUPLICATE BACKEND CALLS: {dup_backend} identical Backend endpoints queried within requests.")

    slow_gens = [e for e in pipeline_llm_events if e.get("generation_tps") and e.get("generation_tps") < 5.0]
    if slow_gens:
        alerts.append(f"[!] LOW GENERATION THROUGHPUT: {len(slow_gens)} pipeline calls generated at < 5.0 tokens/s (CPU offload signature).")

    if alerts:
        for alert in alerts:
            print(f"  {alert}")
    else:
        print("  [✓] No critical anomalies detected in the analyzed audit logs.")

    print("\n" + "=" * 80)
    print("  End of Latency Audit Report")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
