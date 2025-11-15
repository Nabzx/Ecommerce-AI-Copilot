from confluent_kafka import Consumer
import redis
import json
from indicators import TechnicalIndicators

# -------------------------------
# Connect to Redis
# -------------------------------
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# -------------------------------
# Kafka Consumer Setup
# -------------------------------
consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "tradeflux-consumer-group",
    "auto.offset.reset": "earliest"
})

consumer.subscribe(["crypto_ticks"])

# Cache per-symbol indicator calculators
indicators_cache = {}

def get_indicator_calculator(symbol: str) -> TechnicalIndicators:
    """Get or create indicator calculator for a symbol, restore price history if available."""
    if symbol not in indicators_cache:
        calc = TechnicalIndicators()

        # Restore history from Redis LIST (oldest to newest)
        key = f"price_history:{symbol}"
        prices = r.lrange(key, 0, -1)

        if prices:
            # Redis LIST stores oldest first (when using rpush), so read in order
            for p in prices:
                try:
                    price_val = float(p)
                    calc.update_price(price_val)
                except (ValueError, TypeError):
                    # Skip non-float values
                    continue

        indicators_cache[symbol] = calc

    return indicators_cache[symbol]

def save_price(symbol: str, price: float) -> None:
    """
    Append price to a Redis LIST.
    Maintain a rolling window of the last 1000 prices.
    """
    key = f"price_history:{symbol}"
    r.rpush(key, price)
    r.ltrim(key, -1000, -1)


print("Connected to Kafka and Redis. Waiting for messages...")

# -------------------------------
# Main Loop
# -------------------------------
while True:
    msg = consumer.poll(1.0)

    if msg is None:
        continue

    if msg.error():
        print("Consumer error:", msg.error())
        continue

    data = json.loads(msg.value().decode("utf-8"))
    symbol = data["symbol"]

    # Normalize symbols
    if symbol == "BTCUSDT":
        symbol = "BTCUSD"

    if symbol not in ["BTCUSD"]:
        print(f"Unknown symbol {symbol}, skipping...")
        continue

    # Redis analytics key
    key = f"analytics:{symbol}"
    existing = r.hgetall(key)

    # Rolling price stats
    last_price = float(data["price"])
    count = int(existing.get("count", 0)) + 1
    sum_price = float(existing.get("sum", 0)) + last_price
    avg_price = sum_price / count

    # Min/max
    existing_min = float(existing.get("min", last_price))
    existing_max = float(existing.get("max", last_price))
    min_price = min(existing_min, last_price)
    max_price = max(existing_max, last_price)

    # Indicators
    calc = get_indicator_calculator(symbol)
    calc.update_price(last_price)
    indicators = calc.get_all_indicators()

    # Save price to Redis LIST (maintains rolling window of 1000 prices)
    save_price(symbol, last_price)

    # Map to be saved in Redis
    redis_mapping = {
        "last_price": last_price,
        "sum": sum_price,
        "count": count,
        "avg_price": avg_price,
        "min": min_price,
        "max": max_price,
    }

    # Add indicators into Redis
    for ind_key, ind_value in indicators.items():
        redis_mapping[ind_key] = ind_value

    # Save into Redis
    r.hset(key, mapping=redis_mapping)

    print(f"Updated analytics for {symbol}: price={last_price}, indicators={indicators}")
