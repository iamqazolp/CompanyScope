from scripts.manage_model_pricing import upsert_model_pricing

if __name__ == "__main__":
    res = upsert_model_pricing(
        model_name="gpt-6-luna",
        input_per_1m=0.10,
        cached_input_per_1m=0.01,
        cache_write_per_1m=0.125,
        output_per_1m=0.50,
        backfill=True,
    )
    import json

    print(json.dumps(res, indent=2))
