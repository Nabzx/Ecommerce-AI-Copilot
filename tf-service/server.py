"""
FastAPI server for TensorFlow price prediction
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import tensorflow as tf
import numpy as np
import redis
import json
import os
from typing import Optional

app = FastAPI(title="TradeFlux AI Prediction Service")

MODEL_DIR = "model"
MODEL_PATH = os.path.join(MODEL_DIR, "lstm_model")
NORM_PATH = os.path.join(MODEL_DIR, "normalization.npy")
WINDOW_SIZE = 200

# Global model and normalization
model = None
normalization = None

class PredictionResponse(BaseModel):
    symbol: str = "BTCUSD"
    current_price: float
    forecast_price: float
    delta: float
    confidence: float

def load_model():
    """Load model and normalization parameters"""
    global model, normalization
    
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Please run train.py first.")
    
    if not os.path.exists(NORM_PATH):
        raise FileNotFoundError(f"Normalization file not found at {NORM_PATH}")
    
    model = tf.keras.models.load_model(MODEL_PATH)
    
    # Load normalization from .npy file
    norm_data = np.load(NORM_PATH, allow_pickle=True).item()
    normalization = {
        'X_mean': norm_data['mean'],
        'X_std': norm_data['std'],
        'y_mean': 0.0,  # Not used in new format
        'y_std': 1.0    # Not used in new format
    }
    
    print("Model loaded successfully")

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

def get_price_history(redis_client, symbol="BTCUSD"):
    """Fetch last WINDOW_SIZE prices from Redis LIST"""
    # Check if list exists and has enough data
    key = f"price_history:{symbol}"
    list_len = redis_client.llen(key)
    if list_len < WINDOW_SIZE:
        return None
    
    # Load all prices and take last WINDOW_SIZE
    all_prices = load_price_history(redis_client, symbol, window=WINDOW_SIZE)
    
    if len(all_prices) < WINDOW_SIZE:
        return None
    
    # Return last WINDOW_SIZE prices
    return all_prices[-WINDOW_SIZE:]

@app.on_event("startup")
async def startup_event():
    """Load model on startup"""
    try:
        load_model()
    except Exception as e:
        print(f"Warning: Could not load model: {e}")
        print("Service will start but predictions will fail until model is trained")

@app.get("/")
async def root():
    return {"service": "TradeFlux AI Prediction Service", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "model_loaded": model is not None}

@app.get("/predict", response_model=PredictionResponse)
async def predict(symbol: str = "BTCUSD"):
    """
    Predict next 60-second price delta
    """
    if model is None or normalization is None:
        raise HTTPException(status_code=503, detail="Model not loaded. Please train the model first.")
    
    # Connect to Redis
    try:
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Redis: {e}")
    
    # Get price history
    prices = get_price_history(redis_client, symbol)
    
    if prices is None or len(prices) < WINDOW_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient price history. Need at least {WINDOW_SIZE} prices."
        )
    
    current_price = prices[-1]
    
    # Normalize input using saved normalization
    prices_array = np.array(prices)
    prices_normalized = (prices_array - normalization['X_mean']) / (normalization['X_std'] + 1e-8)
    
    # Reshape for model (1, WINDOW_SIZE, 1)
    X = prices_normalized.reshape((1, WINDOW_SIZE, 1))
    
    # Predict (output is normalized delta)
    prediction_normalized = model.predict(X, verbose=0)[0][0]
    
    # Denormalize: prediction is normalized delta, need to convert back to price space
    # Since we normalized the entire price series, the delta is also in normalized space
    # We need to convert it back: delta_normalized * std = delta_actual
    # But we need the actual price delta, so we use the std from normalization
    predicted_delta = prediction_normalized * normalization['X_std']
    predicted_price = current_price + predicted_delta
    
    # Simple confidence metric (based on prediction magnitude)
    confidence = min(1.0, max(0.0, 1.0 - abs(predicted_delta) / (current_price * 0.01)))
    
    return PredictionResponse(
        symbol=symbol,
        current_price=float(current_price),
        forecast_price=float(predicted_price),
        delta=float(predicted_delta),
        confidence=float(confidence)
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

