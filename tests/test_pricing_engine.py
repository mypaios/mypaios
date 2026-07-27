"""PriceBook unit tests — unit conversions and provider cache-billing semantics.

These encode the two classic integration bugs (OpenRouter's USD-per-single-token
strings ×1e6; cache-token double-billing) plus the honesty rules (unknown model
→ None, local → free)."""
from services.pricing import get_price, compute_cost, normalize_openrouter_pricing
from services.pricing.pricebook import is_local_url


def test_openrouter_pricing_normalizes_per_token_strings_to_per_million():
    p = normalize_openrouter_pricing({
        "prompt": "0.000003", "completion": "0.000015",
        "input_cache_read": "0.0000003", "request": "0",
    })
    assert p["in_per_m"] == 3.0
    assert p["out_per_m"] == 15.0
    assert p["cache_read_per_m"] == 0.3
    assert "request_usd" not in p  # "0" = no per-request fee


def test_snapshot_lookup_exact_and_prefixed():
    pr = get_price("gpt-4o")
    assert pr and pr["source"] == "litellm" and pr["in_per_m"] > 0
    # vendor-prefixed OpenRouter-style id resolves via prefix match
    assert get_price("anthropic/claude-sonnet-4") is not None


def test_openai_style_cached_tokens_are_a_subset_no_double_billing():
    usage = {"input_tokens": 10000, "output_tokens": 1000, "cached_tokens": 8000}
    price = {"in_per_m": 3.0, "out_per_m": 15.0, "cache_read_per_m": 0.3, "source": "litellm"}
    c = compute_cost(usage, price, "openai")
    expected = (2000 * 3.0 + 8000 * 0.3 + 1000 * 15.0) / 1e6
    assert abs(c - expected) < 1e-9


def test_anthropic_input_excludes_cache_buckets():
    usage = {"input_tokens": 2000, "output_tokens": 1000,
             "cached_tokens": 8000, "cache_write_tokens": 500}
    price = {"in_per_m": 3.0, "out_per_m": 15.0,
             "cache_read_per_m": 0.3, "cache_write_per_m": 3.75, "source": "litellm"}
    c = compute_cost(usage, price, "anthropic")
    expected = (2000 * 3.0 + 8000 * 0.3 + 500 * 3.75 + 1000 * 15.0) / 1e6
    assert abs(c - expected) < 1e-9


def test_local_is_free_and_unknown_is_honest():
    assert compute_cost({"input_tokens": 9, "output_tokens": 9},
                        get_price("qwen3-vl:30b-a3b", is_local=True), "ollama") == 0.0
    assert get_price("totally-unknown-model-xyz-9000") is None
    assert compute_cost({"input_tokens": 9}, None, "openai") is None


def test_local_url_classification():
    assert is_local_url("http://localhost:11434/v1")
    assert is_local_url("http://192.168.1.5:8000/v1")
    assert is_local_url("http://100.101.1.2:8000/v1")      # tailnet
    assert not is_local_url("https://openrouter.ai/api/v1")
    assert not is_local_url("https://api.openai.com/v1")
