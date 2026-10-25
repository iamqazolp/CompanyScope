import argparse
import base64
import datetime
import json
import re
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, TraceFlags
import requests

from src.agent import compute_gpt6_luna_usage_and_cost
from src.config import (
    LANGFUSE_HOST,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    PROJECT_ROOT,
)

PRICING_FILE = PROJECT_ROOT / "src" / "model_pricing.json"


def load_pricing_registry() -> dict[str, dict[str, Any]]:
    if not PRICING_FILE.exists():
        return {}
    try:
        with open(PRICING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_pricing_registry(registry: dict[str, dict[str, Any]]) -> None:
    PRICING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRICING_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")


def _iso_to_exact_ns(iso_str: str) -> int:
    """Converts an ISO-8601 millisecond timestamp string to exact integer nanoseconds."""
    dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    ms = round(dt.timestamp() * 1000)
    return int(ms * 1_000_000)


def sync_model_in_langfuse(
    model_name: str,
    input_per_1m: float,
    cached_input_per_1m: float,
    cache_write_per_1m: float,
    output_per_1m: float,
    match_pattern: str | None = None,
    tokenizer_id: str = "openai",
) -> dict[str, Any]:
    """
    Upserts a custom model definition in Langfuse (/api/public/models) with per-token USD rates.
    """
    base = LANGFUSE_HOST.rstrip("/")
    auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)

    if not match_pattern:
        escaped = re.escape(model_name)
        match_pattern = f"(?i)^([a-z0-9_-]+/)?({escaped})$"

    input_rate = round(input_per_1m / 1_000_000.0, 12)
    cached_rate = round(cached_input_per_1m / 1_000_000.0, 12)
    cache_write_rate = round(cache_write_per_1m / 1_000_000.0, 12)
    output_rate = round(output_per_1m / 1_000_000.0, 12)

    # Paginate through all models to remove any prior custom definition with the same modelName or matchPattern
    page = 1
    while True:
        r_list = requests.get(
            f"{base}/api/public/models?limit=100&page={page}",
            auth=auth,
            timeout=15,
        )
        if not r_list.ok:
            break
        body = r_list.json()
        models_page = body.get("data") or []
        for m in models_page:
            if not m.get("isLangfuseManaged", True) and (
                m.get("modelName", "").lower() == model_name.lower()
                or m.get("matchPattern") == match_pattern
            ):
                requests.delete(
                    f"{base}/api/public/models/{m['id']}", auth=auth, timeout=10
                )
        total_pages = (body.get("meta") or {}).get("totalPages", 1)
        if page >= total_pages or not models_page:
            break
        page += 1

    payload: dict[str, Any] = {
        "modelName": model_name,
        "matchPattern": match_pattern,
        "unit": "TOKENS",
        "tokenizerId": tokenizer_id,
        "tokenizerConfig": {
            "tokensPerMessage": 3,
            "tokensPerName": 1,
            "tokenizerModel": "gpt-4",
        },
        "pricingTiers": [
            {
                "name": "Standard",
                "isDefault": True,
                "priority": 0,
                "conditions": [],
                "prices": {
                    "input": input_rate,
                    "input_tokens": input_rate,
                    "input_cached_tokens": cached_rate,
                    "input_cache_read": cached_rate,
                    "cache_read_input_tokens": cached_rate,
                    "cache_write_tokens": cache_write_rate,
                    "input_cache_write_tokens": cache_write_rate,
                    "input_cache_creation": cache_write_rate,
                    "cache_creation_input_tokens": cache_write_rate,
                    "output": output_rate,
                    "output_tokens": output_rate,
                    "output_reasoning_tokens": output_rate,
                },
            }
        ],
    }

    r_create = requests.post(
        f"{base}/api/public/models", auth=auth, json=payload, timeout=15
    )
    r_create.raise_for_status()
    return dict(r_create.json())


def backfill_model_generations(model_name: str | None = None) -> dict[str, Any]:
    """
    Fetches historical GENERATION observations in Langfuse (filtered by model_name if given),
    recomputes mutually-exclusive usage_details and cost_details from src/model_pricing.json,
    and exports the updated spans in-place via OTLPSpanExporter.
    """
    base = LANGFUSE_HOST.rstrip("/")
    auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)

    all_obs: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        url = (
            f"{base}/api/public/v2/observations"
            "?type=GENERATION&limit=100&fields=core,basic,time,io,metadata,model,usage"
        )
        if cursor:
            url += f"&cursor={cursor}"
        r = requests.get(url, auth=auth, timeout=20)
        r.raise_for_status()
        body = r.json()
        data = body.get("data") or []
        all_obs.extend(data)
        cursor = (body.get("meta") or {}).get("cursor")
        if not cursor or not data:
            break

    b64 = base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode("utf-8")
    ).decode("ascii")
    exporter = OTLPSpanExporter(
        endpoint=f"{base}/api/public/otel/v1/traces",
        headers={
            "Authorization": f"Basic {b64}",
            "x-langfuse-sdk-name": "python",
            "x-langfuse-sdk-version": "4.7.1",
            "x-langfuse-public-key": LANGFUSE_PUBLIC_KEY,
        },
    )

    spans_to_export: list[ReadableSpan] = []
    backfilled_ids: list[str] = []
    total_cost_backfilled = 0.0

    # Deduplicate by (id, startTime) in case multiple versions exist
    seen_keys: set[tuple[str, int]] = set()

    for obs in all_obs:
        obs_model = str(obs.get("model") or "gpt-6-luna")
        if model_name and model_name.lower() not in obs_model.lower():
            continue

        st_ns = _iso_to_exact_ns(obs["startTime"])
        dedup_key = (str(obs["id"]), st_ns)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        existing_usage = obs.get("usageDetails") or {}
        input_str = obs.get("input") or ""
        output_str = obs.get("output") or ""

        raw_usage: dict[str, Any] = {}
        if existing_usage:
            in_tok = int(existing_usage.get("input") or 0)
            cached_tok = int(
                existing_usage.get("input_cached_tokens")
                or existing_usage.get("cache_read_input_tokens")
                or 0
            )
            cw_tok = int(
                existing_usage.get("cache_write_tokens")
                or existing_usage.get("input_cache_creation")
                or 0
            )
            out_tok = int(existing_usage.get("output") or 0)
            raw_usage = {
                "prompt_tokens": in_tok + cached_tok + cw_tok,
                "completion_tokens": out_tok,
                "prompt_tokens_details": {
                    "cached_tokens": cached_tok,
                    "cache_write_tokens": cw_tok,
                },
            }

        usage_details, cost_details = compute_gpt6_luna_usage_and_cost(
            raw_usage if raw_usage else None,
            fallback_input_text=str(input_str),
            fallback_output_text=str(output_str),
            model_name=obs_model,
        )
        total_cost_backfilled += float(cost_details.get("total", 0.0))

        et_ns = (
            _iso_to_exact_ns(obs["endTime"])
            if obs.get("endTime")
            else st_ns + 1_000_000
        )

        trace_id_int = int(obs["traceId"], 16)
        span_id_int = int(obs["id"], 16)
        ctx = SpanContext(
            trace_id=trace_id_int,
            span_id=span_id_int,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        parent_id = obs.get("parentObservationId")
        p_ctx = (
            SpanContext(
                trace_id=trace_id_int,
                span_id=int(parent_id, 16),
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
            if parent_id
            else None
        )

        attrs: dict[str, Any] = {
            "langfuse.observation.type": "generation",
            "langfuse.observation.model.name": obs_model,
            "langfuse.observation.input": str(input_str),
            "langfuse.observation.output": str(output_str),
            "langfuse.observation.usage_details": json.dumps(usage_details),
            "langfuse.observation.cost_details": json.dumps(cost_details),
        }

        span = ReadableSpan(
            name=obs.get("name") or "llm_chat_completion",
            context=ctx,
            parent=p_ctx,
            resource=Resource.create({"service.name": "company-scope"}),
            attributes=attrs,
            start_time=st_ns,
            end_time=et_ns,
            instrumentation_scope=InstrumentationScope(
                "langfuse-sdk",
                "4.7.1",
                attributes={"public_key": LANGFUSE_PUBLIC_KEY},
            ),
        )
        spans_to_export.append(span)
        backfilled_ids.append(obs["id"])

    if spans_to_export:
        exporter.export(spans_to_export)

    return {
        "target_model": model_name or "ALL",
        "total_generations_scanned": len(all_obs),
        "generations_backfilled": len(spans_to_export),
        "total_backfilled_cost_usd": round(total_cost_backfilled, 6),
        "backfilled_observation_ids": backfilled_ids,
    }


def upsert_model_pricing(
    model_name: str,
    input_per_1m: float,
    output_per_1m: float,
    cached_input_per_1m: float | None = None,
    cache_write_per_1m: float | None = None,
    match_pattern: str | None = None,
    backfill: bool = False,
) -> dict[str, Any]:
    """
    Saves a model's pricing in src/model_pricing.json, syncs its custom model definition
    in Langfuse, and optionally backfills historical generations.
    """
    actual_cached = (
        cached_input_per_1m
        if cached_input_per_1m is not None
        else round(input_per_1m * 0.10, 6)
    )
    actual_cache_write = (
        cache_write_per_1m
        if cache_write_per_1m is not None
        else round(input_per_1m * 1.25, 6)
    )
    escaped = re.escape(model_name)
    actual_pattern = match_pattern or f"(?i)^([a-z0-9_-]+/)?({escaped})$"

    registry = load_pricing_registry()
    registry[model_name] = {
        "match_pattern": actual_pattern,
        "input_per_1m": input_per_1m,
        "cached_input_per_1m": actual_cached,
        "cache_write_per_1m": actual_cache_write,
        "output_per_1m": output_per_1m,
        "tokenizer_id": "openai",
    }
    save_pricing_registry(registry)

    lf_model = sync_model_in_langfuse(
        model_name=model_name,
        input_per_1m=input_per_1m,
        cached_input_per_1m=actual_cached,
        cache_write_per_1m=actual_cache_write,
        output_per_1m=output_per_1m,
        match_pattern=actual_pattern,
    )

    result: dict[str, Any] = {
        "model": model_name,
        "pricing_per_1m_usd": registry[model_name],
        "langfuse_model_id": lf_model.get("id"),
    }

    if backfill:
        result["backfill"] = backfill_model_generations(model_name=model_name)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add or update LLM model pricing in CompanyScope + Langfuse, with optional historical trace backfill."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all configured models and pricing in src/model_pricing.json",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Model name (e.g. gpt-6-luna, gpt-5.6-luna, llama-3.3-70b-versatile)",
    )
    parser.add_argument(
        "--input",
        type=float,
        dest="input_price",
        help="Standard input token price in USD per 1M tokens (e.g. 0.10)",
    )
    parser.add_argument(
        "--cached-input",
        type=float,
        dest="cached_input_price",
        default=None,
        help="Cached input token price in USD per 1M tokens (defaults to 10%% of --input)",
    )
    parser.add_argument(
        "--cache-write",
        type=float,
        dest="cache_write_price",
        default=None,
        help="Cache write token price in USD per 1M tokens (defaults to 1.25x of --input)",
    )
    parser.add_argument(
        "--output",
        type=float,
        dest="output_price",
        help="Output token price in USD per 1M tokens (e.g. 0.50)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=None,
        help="Optional regex match pattern for Langfuse model definition",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill all existing historical generations for this model in Langfuse",
    )
    parser.add_argument(
        "--backfill-only",
        action="store_true",
        help="Run backfill for --model (or all models if --model is omitted) using current src/model_pricing.json",
    )

    args = parser.parse_args()

    if args.list:
        reg = load_pricing_registry()
        print(json.dumps(reg, indent=2))
        return

    if args.backfill_only:
        res = backfill_model_generations(model_name=args.model)
        print(json.dumps(res, indent=2))
        return

    # Interactive mode if --model wasn't supplied on CLI
    if not args.model:
        print("=== CompanyScope Model Pricing & Langfuse Backfill Manager ===")
        model_name = input("Model name [gpt-6-luna]: ").strip() or "gpt-6-luna"
        in_str = input("Input price ($ per 1M tokens) [0.10]: ").strip() or "0.10"
        input_price = float(in_str)

        default_cached = round(input_price * 0.10, 6)
        cached_str = input(
            f"Cached input price ($ per 1M tokens) [{default_cached}]: "
        ).strip()
        cached_price = float(cached_str) if cached_str else default_cached

        default_cw = round(input_price * 1.25, 6)
        cw_str = input(
            f"Cache write price ($ per 1M tokens) [{default_cw}]: "
        ).strip()
        cw_price = float(cw_str) if cw_str else default_cw

        out_str = input("Output price ($ per 1M tokens) [0.50]: ").strip() or "0.50"
        output_price = float(out_str)

        bf_ans = (
            input("Backfill historical Langfuse traces now? [Y/n]: ").strip().lower()
        )
        do_backfill = bf_ans in ("", "y", "yes")

        out = upsert_model_pricing(
            model_name=model_name,
            input_per_1m=input_price,
            output_per_1m=output_price,
            cached_input_per_1m=cached_price,
            cache_write_per_1m=cw_price,
            backfill=do_backfill,
        )
        print(json.dumps(out, indent=2))
        return

    if args.input_price is None or args.output_price is None:
        parser.error("--input and --output are required when adding/updating a model.")

    out = upsert_model_pricing(
        model_name=args.model,
        input_per_1m=args.input_price,
        output_per_1m=args.output_price,
        cached_input_per_1m=args.cached_input_price,
        cache_write_per_1m=args.cache_write_price,
        match_pattern=args.pattern,
        backfill=args.backfill,
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
