# TradeFlux AI - Real-Time Cryptocurrency Analytics Platform

A comprehensive real-time cryptocurrency analytics platform with technical indicators, ML forecasting, alerting, and mobile client support.

## Architecture

```
┌─────────────────┐     ┌──────────┐     ┌──────────────┐     ┌──────────┐
│  Coinbase WS    │────▶│  Kafka   │────▶│   Python     │────▶│  Redis   │
│   Producer      │     │          │     │   Consumer   │     │          │
└─────────────────┘     └──────────┘     └──────────────┘     └──────────┘
                                                                    │
                        ┌───────────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────────────────┐
        │                                                 │
        ▼                                                 ▼
┌───────────────┐                              ┌──────────────────┐
│  TensorFlow   │                              │  Next.js        │
│  LSTM Service  │                              │  Dashboard       │
└───────────────┘                              └──────────────────┘
        │                                                 │
        │                                                 │
        └──────────────────┬──────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  SwiftUI iOS    │
                  │  Mobile Client   │
                  └─────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  AWS Lambda      │
                  │  Alerting        │
                  └─────────────────┘
```

## Features

### Real-Time Data Pipeline
- **Coinbase WebSocket** producer for live BTC/USD prices
- **Kafka** message streaming
- **Redis** for analytics storage (LIST for price history, HASH for analytics)
- **Python consumer** with incremental technical indicators

### Technical Indicators
- **RSI (14)**: Relative Strength Index
- **MACD (12/26/9)**: Moving Average Convergence Divergence
- **Bollinger Bands (20, 2)**: Upper, Middle, Lower bands
- **Volatility**: 20-period standard deviation

### Machine Learning Forecasting
- **TensorFlow LSTM** model for 60-second price prediction
- FastAPI microservice for predictions
- Docker containerization

### AWS Lambda Alerting
- Price movement alerts (>1.5% in 5 minutes)
- Volatility threshold alerts
- MACD crossing alerts
- Email (SES) and Webhook support

### Professional Dashboard
- Bloomberg-style UI design
- Real-time indicator visualizations
- Forecast display
- Responsive grid layout
- Vercel deployment ready

### SwiftUI iOS Client
- Native iOS app with tabbed interface
- Real-time price updates
- Indicator visualization
- ML forecast display

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Java 17+
- Python 3.11+
- Node.js 18+
- Maven
- Xcode 14+ (for iOS app)

### Setup Python Virtual Environment

```bash
# From project root
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 1. Start Infrastructure

```bash
docker compose up -d
```

This starts:
- Zookeeper (port 2181)
- Kafka (port 9092)
- Redis (port 6379)

Verify services:
```bash
docker ps
```

### 2. Start Java Producer

**Terminal 1:**
```bash
cd java-producer
mvn clean package
java -jar target/price-producer-1.0-SNAPSHOT-jar-with-dependencies.jar
```

Expected output:
```
Starting TradeFlux AI Price Producer (Coinbase WebSocket)...
WebSocket connection opened to Coinbase
Subscribed to BTC-USD ticker channel
Published: {"symbol":"BTCUSD","price":95000.0,"ts":1234567890}
```

### 3. Start Python Consumer

**Terminal 2:**
```bash
source .venv/bin/activate
cd python-consumer
pip install -r requirements.txt
python consumer.py
```

Expected output:
```
Connected to Kafka and Redis. Waiting for messages...
Updated analytics for BTCUSD: price=95000.0, indicators={'rsi': 45.23, ...}
```

**Important**: Wait for the consumer to collect at least 260 prices before training the model.

Check Redis list length:
```bash
docker exec -it redis redis-cli LLEN price_history:BTCUSD
```

### 4. Train TensorFlow Model

**Terminal 3:**
```bash
source .venv/bin/activate
cd tf-service
pip install -r requirements.txt

# Wait for LLEN >= 260, then:
python train.py
```

Expected output:
```
Connecting to Redis...
Fetching training data...
Loaded 500 samples
Training model...
Epoch 1/10...
...
Training complete.
```

### 5. Start TensorFlow Service

**Terminal 3 (after training):**
```bash
python server.py
```

Or with Docker:
```bash
docker build -t tf-service .
docker run -p 8000:8000 --network host tf-service
```

Service runs on `http://localhost:8000`

### 6. Start Dashboard

**Terminal 4:**
```bash
cd dashboard
npm install
npm run dev
```

Visit `http://localhost:3000` to see the dashboard.

### 7. iOS App (Optional)

**Open in Xcode:**
1. Open Xcode
2. File → New → Project
3. Choose "App" template
4. Name: TradeFluxMobile
5. Copy files from `ios-app/TradeFluxMobile/` into the project
6. Build and run on simulator or device

**Note**: Update `ApiClient.swift` baseURL if dashboard is not on localhost:3000

## Project Structure

```
TradeFluxAI/
├── java-producer/          # Coinbase WebSocket → Kafka producer
│   ├── src/main/java/
│   └── pom.xml
├── python-consumer/        # Kafka → Redis consumer with indicators
│   ├── consumer.py
│   ├── indicators.py
│   └── requirements.txt
├── tf-service/             # TensorFlow LSTM forecasting service
│   ├── train.py
│   ├── server.py
│   ├── requirements.txt
│   └── Dockerfile
├── aws-lambda/             # AWS Lambda alerting function
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── README.md
├── dashboard/              # Next.js 14 dashboard
│   ├── app/
│   │   ├── api/
│   │   │   ├── price/route.ts
│   │   │   ├── history/route.ts
│   │   │   └── forecast/route.ts
│   │   └── page.tsx
│   ├── components/
│   └── lib/redis.ts
├── ios-app/                # SwiftUI iOS client
│   └── TradeFluxMobile/
│       ├── TradeFluxMobileApp.swift
│       ├── ContentView.swift
│       ├── Models.swift
│       ├── Services/ApiClient.swift
│       └── Views/
├── docker-compose.yml      # Infrastructure services
└── README.md
```

## API Endpoints

### Dashboard API

- `GET /api/price` - Get current analytics and indicators
- `GET /api/history` - Get recent price history (last 200 points)
- `GET /api/forecast` - Get 60-second price forecast

### TensorFlow Service

- `GET /predict?symbol=BTCUSD` - Get price prediction
- `GET /health` - Health check

## Redis Data Structure

**Analytics (Hash)**:
```
analytics:BTCUSD
  - last_price: float
  - avg_price: float
  - min: float
  - max: float
  - count: int
  - sum: float
  - rsi: float
  - macd: float
  - macd_signal: float
  - macd_hist: float
  - bb_upper: float
  - bb_middle: float
  - bb_lower: float
  - volatility: float
```

**Price History (LIST)**:
```
price_history:BTCUSD
  - Redis LIST containing up to 1000 prices
  - Oldest prices first (when using RPUSH)
  - Automatically trimmed to last 1000 entries
  - Used for TensorFlow training (requires LLEN >= 260)
  - Check length: redis-cli LLEN price_history:BTCUSD
```

## Environment Variables

### Dashboard (.env)

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
TF_SERVICE_URL=http://localhost:8000
```

### AWS Lambda

```env
REDIS_HOST=<redis-host>
REDIS_PORT=6379
REDIS_PASSWORD=<optional>
SES_REGION=us-east-1
ALERT_EMAIL=<your-email>
WEBHOOK_URL=<optional-webhook>
```

## Deployment

### Vercel Dashboard Deployment

1. **Install Vercel CLI**:
   ```bash
   npm i -g vercel
   ```

2. **Set Environment Variables**:
   ```bash
   cd dashboard
   vercel env add REDIS_HOST
   vercel env add REDIS_PORT
   vercel env add REDIS_PASSWORD
   vercel env add TF_SERVICE_URL
   ```

3. **Deploy**:
   ```bash
   vercel
   ```

### AWS Lambda Deployment

See `aws-lambda/README.md` for detailed instructions.

1. Package the function:
   ```bash
   cd aws-lambda
   pip install -r requirements.txt -t .
   zip -r lambda_function.zip . -x "*.pyc" "__pycache__/*"
   ```

2. Create Lambda function in AWS Console
3. Upload `lambda_function.zip`
4. Configure environment variables
5. Set up CloudWatch Events trigger (rate: 1 minute)

## Technical Details

### Technical Indicators

All indicators are calculated incrementally without recomputing full history:

- **RSI**: Uses rolling gain/loss windows
- **MACD**: Exponential moving averages with state persistence
- **Bollinger Bands**: 20-period SMA with 2 standard deviations
- **Volatility**: 20-period standard deviation

### TensorFlow Model

- **Architecture**: LSTM (128 → 64 → 32 → 1)
- **Input**: Last 200 prices
- **Output**: 60-second price delta prediction
- **Training**: Uses price history from Redis LIST
- **Normalization**: Mean/std normalization stored with model

### Price History Storage

- **Format**: Redis LIST (not STRING/JSON)
- **Operations**: `RPUSH` to append, `LTRIM` to maintain window
- **Window**: Last 1000 prices
- **Training Requirement**: Minimum 260 prices (WINDOW + FORECAST_HORIZON)

## Troubleshooting

### Producer not connecting
- Check Coinbase WebSocket URL
- Verify Kafka is running: `docker ps`
- Check logs for connection errors

### Consumer not processing
- Verify Kafka topic exists: `docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092`
- Check Redis connection
- Ensure indicators have enough data (need 20+ prices for most indicators)

### Training fails
- Check Redis list length: `docker exec -it redis redis-cli LLEN price_history:BTCUSD`
- Need at least 260 prices
- Verify list is actually a LIST: `docker exec -it redis redis-cli TYPE price_history:BTCUSD` (should return "list")

### Dashboard not loading
- Check Redis connection
- Verify API routes are accessible
- Check browser console for errors
- Ensure environment variables are set

### Forecast unavailable
- Ensure TensorFlow service is running
- Verify model is trained (`model/lstm_model` directory exists)
- Check `TF_SERVICE_URL` environment variable
- Verify Redis has enough price history

### iOS app not connecting
- Ensure dashboard is running on `http://localhost:3000`
- Check network permissions in Info.plist
- Update `baseURL` in `ApiClient.swift` if needed


## Contributing

Contributions welcome! Please open an issue or submit a PR.
