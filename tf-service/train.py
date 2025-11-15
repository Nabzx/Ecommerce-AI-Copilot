import redis
import numpy as np
import tensorflow as tf
import os

WINDOW = 200
FORECAST_HORIZON = 60  # 60-second forecast
MODEL_DIR = "model"

def load_price_history(redis_client, symbol="BTCUSD", window=1000):
    """
    Load price history from Redis LIST.
    Returns list of floats, oldest to newest.
    """
    key = f"price_history:{symbol}"
    data = redis_client.lrange(key, 0, -1)  # Get all items (oldest to newest)
    prices = []
    for x in data:
        try:
            prices.append(float(x))
        except (TypeError, ValueError):
            continue
    return prices

def fetch_training_data(redis_client):
    """
    Fetch price history from Redis LIST: price_history:BTCUSD
    Return normalized sliding windows suitable for model training.
    """
    key = "price_history:BTCUSD"
    
    # Check list length first
    list_len = redis_client.llen(key)
    if list_len < WINDOW + FORECAST_HORIZON:
        print(f"Not enough data. Need at least {WINDOW + FORECAST_HORIZON} prices, but LLEN={list_len}.")
        return None, None, None

    # Use helper to load price history
    prices = load_price_history(redis_client, symbol="BTCUSD", window=1000)
    
    if not prices or len(prices) < WINDOW + FORECAST_HORIZON:
        print(f"After loading, only {len(prices) if prices else 0} valid prices. Need at least {WINDOW + FORECAST_HORIZON}.")
        return None, None, None
    
    prices = np.array(prices)

    # Normalize
    mean = prices.mean()
    std = prices.std() if prices.std() > 0 else 1
    normalized = (prices - mean) / std

    X = []
    y = []

    for i in range(len(normalized) - WINDOW - FORECAST_HORIZON):
        window = normalized[i : i + WINDOW]
        target = normalized[i + WINDOW + FORECAST_HORIZON] - normalized[i + WINDOW]
        X.append(window)
        y.append(target)

    X = np.array(X).reshape(-1, WINDOW, 1)
    y = np.array(y)

    normalization = {"mean": mean, "std": std}

    return X, y, normalization


def train():
    print("Connecting to Redis...")
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

    print("Fetching training data...")
    X, y, normalization = fetch_training_data(redis_client)

    if X is None:
        print("Not enough data yet. Press CTRL+C and try again after letting the system run longer.")
        return

    print(f"Loaded {len(X)} samples")

    # Build model
    model = tf.keras.Sequential([
        tf.keras.layers.LSTM(128, return_sequences=True, input_shape=(WINDOW, 1)),
        tf.keras.layers.LSTM(64),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dense(1)
    ])

    model.compile(optimizer="adam", loss="mse")

    print("Training model...")
    model.fit(X, y, epochs=10, batch_size=32)

    # Create model directory
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    print("Saving model...")
    model.save(os.path.join(MODEL_DIR, "lstm_model"))

    print("Saving normalization...")
    np.save(os.path.join(MODEL_DIR, "normalization.npy"), normalization)

    print("Training complete.")


if __name__ == "__main__":
    train()
