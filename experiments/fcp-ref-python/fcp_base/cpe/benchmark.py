"""CPE Adapter Performance Benchmarking.

Measures token usage, latency, and cost across adapters.
Provides utilities for profiling and comparing adapter performance.

Date: 2026-03-21
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .base import CPEResponse, CPEAdapter


# Pricing tiers (as of 2026-03-21)
_PRICING: dict[str, dict[str, float]] = {
    "anthropic": {
        "claude-opus-4-6": {"input": 0.015, "output": 0.075},  # per 1M tokens
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-5-20251001": {"input": 0.0008, "output": 0.004},
    },
    "openai": {
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    },
    "google": {
        "gemini-2.0-flash": {"input": 0.075, "output": 0.3},  # per 1M tokens
        "gemini-2.0-flash-thinking-exp-01-21": {"input": 0.0, "output": 0.0},  # Free tier (experimental)
        "gemini-1.5-pro": {"input": 0.0075, "output": 0.03},
    },
    "ollama": {
        "default": {"input": 0.0, "output": 0.0},  # Local = free
    },
}


@dataclass(slots=True)
class BenchmarkResult:
    """Single invocation benchmark result."""
    adapter: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    total_tokens: int

    def __str__(self) -> str:
        return (
            f"{self.adapter:12} | {self.model:25} | "
            f"Input: {self.input_tokens:5} | Output: {self.output_tokens:5} | "
            f"Latency: {self.latency_ms:6.1f}ms | Cost: ${self.cost_usd:.6f}"
        )


@dataclass(slots=True)
class BenchmarkSuite:
    """Aggregated benchmark results across multiple runs."""
    adapter: str
    model: str
    runs: int
    total_input_tokens: int
    total_output_tokens: int
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    total_cost_usd: float
    avg_cost_per_call_usd: float

    def __str__(self) -> str:
        return (
            f"{self.adapter:12} | Runs: {self.runs:3} | "
            f"Input: {self.total_input_tokens:6} | Output: {self.total_output_tokens:6} | "
            f"Latency: {self.avg_latency_ms:6.1f}ms (min: {self.min_latency_ms:.1f}, max: {self.max_latency_ms:.1f}) | "
            f"Cost: ${self.total_cost_usd:.4f} (avg: ${self.avg_cost_per_call_usd:.6f})"
        )


def calculate_cost(adapter: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for given adapter, model, and token counts.

    Args:
        adapter: Adapter name ("anthropic", "openai", "google", "ollama")
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Cost in USD
    """
    adapter_pricing = _PRICING.get(adapter, {})
    if not adapter_pricing:
        return 0.0

    model_pricing = adapter_pricing.get(model, adapter_pricing.get("default", {}))
    if not model_pricing:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * model_pricing.get("input", 0)
    output_cost = (output_tokens / 1_000_000) * model_pricing.get("output", 0)
    return input_cost + output_cost


def benchmark_single(
    adapter: CPEAdapter,
    adapter_name: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> BenchmarkResult:
    """Benchmark a single adapter invocation.

    Args:
        adapter: CPE adapter instance
        adapter_name: Adapter name for cost calculation
        model: Model name for cost calculation
        system: System prompt
        messages: Chat history
        tools: Tool declarations

    Returns:
        BenchmarkResult with timing and cost
    """
    if tools is None:
        tools = []

    start = time.perf_counter()
    response = adapter.invoke(system, messages, tools)
    elapsed = time.perf_counter() - start
    latency_ms = elapsed * 1000

    cost = calculate_cost(adapter_name, model, response.input_tokens, response.output_tokens)

    return BenchmarkResult(
        adapter=adapter_name,
        model=model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=latency_ms,
        cost_usd=cost,
        total_tokens=response.input_tokens + response.output_tokens,
    )


def benchmark_suite(
    adapter: CPEAdapter,
    adapter_name: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    runs: int = 5,
) -> BenchmarkSuite:
    """Benchmark adapter across multiple runs.

    Args:
        adapter: CPE adapter instance
        adapter_name: Adapter name
        model: Model name
        system: System prompt
        messages: Chat history
        tools: Tool declarations
        runs: Number of runs

    Returns:
        BenchmarkSuite with aggregated results
    """
    if tools is None:
        tools = []

    results: list[BenchmarkResult] = []
    for _ in range(runs):
        try:
            result = benchmark_single(adapter, adapter_name, model, system, messages, tools)
            results.append(result)
        except Exception:
            # Skip failed runs (e.g., rate limits, network errors)
            pass

    if not results:
        raise RuntimeError(f"All {runs} runs failed for {adapter_name}")

    total_input = sum(r.input_tokens for r in results)
    total_output = sum(r.output_tokens for r in results)
    latencies = [r.latency_ms for r in results]
    total_cost = sum(r.cost_usd for r in results)

    return BenchmarkSuite(
        adapter=adapter_name,
        model=model,
        runs=len(results),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        avg_latency_ms=sum(latencies) / len(latencies),
        min_latency_ms=min(latencies),
        max_latency_ms=max(latencies),
        total_cost_usd=total_cost,
        avg_cost_per_call_usd=total_cost / len(results),
    )


def compare_adapters(
    adapters: dict[str, tuple[CPEAdapter, str]],  # name -> (adapter, model)
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    runs: int = 3,
) -> list[BenchmarkSuite]:
    """Compare performance across multiple adapters.

    Args:
        adapters: Dict mapping adapter name to (adapter instance, model name)
        system: System prompt
        messages: Chat history
        tools: Tool declarations
        runs: Number of runs per adapter

    Returns:
        List of BenchmarkSuite results
    """
    if tools is None:
        tools = []

    results: list[BenchmarkSuite] = []
    for name, (adapter, model) in adapters.items():
        try:
            suite = benchmark_suite(adapter, name, model, system, messages, tools, runs)
            results.append(suite)
        except Exception as e:
            print(f"Warning: Skipped {name}: {e}")

    return results


def print_benchmark_report(suites: list[BenchmarkSuite]) -> None:
    """Print formatted benchmark report.

    Args:
        suites: List of BenchmarkSuite results
    """
    if not suites:
        print("No benchmark results to report")
        return

    print("\n" + "=" * 150)
    print("CPE Adapter Performance Benchmark Report")
    print("=" * 150)
    print()

    for suite in suites:
        print(suite)

    print()
    print("=" * 150)
    print("Summary:")
    print(f"  Fastest:    {min(suites, key=lambda s: s.avg_latency_ms).adapter} ({min(s.avg_latency_ms for s in suites):.1f}ms)")
    print(f"  Cheapest:   {min(suites, key=lambda s: s.avg_cost_per_call_usd).adapter} (${min(s.avg_cost_per_call_usd for s in suites):.6f}/call)")
    print(f"  Most efficient: {max(suites, key=lambda s: s.total_tokens / s.total_cost_usd if s.total_cost_usd > 0 else 0).adapter}")
    print("=" * 150)
    print()
