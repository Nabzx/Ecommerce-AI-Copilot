# TradeFlux AI - Deployment Guide

## Local Development Setup

### 1. Start Infrastructure

```bash
docker compose up -d
```

Verify services are running:
```bash
docker ps
```

### 2. Start Producer

Terminal 1:
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

### 3. Start Consumer

Terminal 2:
```bash
cd python-consumer
pip install -r requirements.txt
python consumer.py
```

Expected output:
```
Connected to Kafka and Redis. Waiting for messages...
Updated analytics for BTCUSD: price=95000.0, indicators={'rsi': 45.23, 'macd': 12.34, ...}
```

### 4. Train TensorFlow Model (First Time)

Terminal 3:
```bash
cd tf-service
pip install -r requirements.txt

# Wait for consumer to collect some data (100+ prices), then:
python train.py
```

This will:
- Fetch price history from Redis
- Train LSTM model
- Save model to `model/price_predictor.h5`

### 5. Start TensorFlow Service

Terminal 3 (after training):
```bash
python server.py
```

Or with Docker:
```bash
docker build -t tf-service .
docker run -p 8000:8000 --network host tf-service
```

### 6. Start Dashboard

Terminal 4:
```bash
cd dashboard
npm install
npm run dev
```

Visit: `http://localhost:3000`

## Vercel Deployment

### Prerequisites
- Vercel account
- Redis instance (AWS ElastiCache, Redis Cloud, etc.)
- TensorFlow service deployed (optional)

### Steps

1. **Install Vercel CLI**:
   ```bash
   npm i -g vercel
   ```

2. **Login to Vercel**:
   ```bash
   vercel login
   ```

3. **Navigate to dashboard**:
   ```bash
   cd dashboard
   ```

4. **Set Environment Variables**:
   ```bash
   vercel env add REDIS_HOST
   # Enter your Redis host (e.g., your-redis.redis.cache.amazonaws.com)
   
   vercel env add REDIS_PORT
   # Enter: 6379
   
   vercel env add REDIS_PASSWORD
   # Enter your Redis password (or leave empty if none)
   
   vercel env add TF_SERVICE_URL
   # Enter your TensorFlow service URL (e.g., https://tf-service.vercel.app)
   ```

5. **Deploy**:
   ```bash
   vercel
   ```

6. **Production Deployment**:
   ```bash
   vercel --prod
   ```

### Vercel Configuration

The `vercel.json` file is already configured. For custom domains:
1. Go to Vercel Dashboard
2. Select your project
3. Go to Settings → Domains
4. Add your custom domain

## AWS Lambda Deployment

### Prerequisites
- AWS Account
- AWS CLI configured
- Redis accessible from Lambda (ElastiCache, etc.)

### Steps

1. **Package Lambda Function**:
   ```bash
   cd aws-lambda
   pip install -r requirements.txt -t .
   zip -r lambda_function.zip . -x "*.pyc" "__pycache__/*" "*.git*" "README.md" "*.md"
   ```

2. **Create IAM Role**:
   - Go to AWS IAM Console
   - Create role for Lambda
   - Attach policies:
     - `AWSLambdaBasicExecutionRole`
     - Custom SES policy (if using email alerts)

3. **Create Lambda Function**:
   - Go to AWS Lambda Console
   - Create function from scratch
   - Upload `lambda_function.zip`
   - Handler: `lambda_function.lambda_handler`
   - Runtime: Python 3.11
   - Timeout: 30 seconds
   - Memory: 256 MB

4. **Configure Environment Variables**:
   ```
   REDIS_HOST=<your-redis-host>
   REDIS_PORT=6379
   REDIS_PASSWORD=<optional>
   SES_REGION=us-east-1
   ALERT_EMAIL=<your-email@example.com>
   WEBHOOK_URL=<optional-webhook-url>
   ```

5. **Set Up CloudWatch Events**:
   - In Lambda function, go to "Add trigger"
   - Select "EventBridge (CloudWatch Events)"
   - Create rule:
     - Rule type: Schedule expression
     - Schedule: `rate(1 minute)`
   - Enable trigger

6. **Verify SES** (for email alerts):
   - Go to AWS SES Console
   - Verify your email address
   - Request production access (if needed)

## Docker Compose for Full Stack

Create `docker-compose.full.yml`:

```yaml
version: '3.8'

services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    # ... existing config

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    # ... existing config

  redis:
    image: redis:7-alpine
    # ... existing config

  tf-service:
    build: ./tf-service
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
```

Run:
```bash
docker compose -f docker-compose.full.yml up -d
```

## Monitoring & Troubleshooting

### Check Kafka Topics
```bash
docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092
```

### Check Redis Data
```bash
docker exec -it redis redis-cli
> KEYS *
> HGETALL analytics:BTCUSD
```

### Check TensorFlow Service
```bash
curl http://localhost:8000/health
curl http://localhost:8000/predict?symbol=BTCUSD
```

### Lambda Logs
- Go to AWS CloudWatch → Log Groups
- Find `/aws/lambda/your-function-name`
- View recent logs

## Production Checklist

- [ ] Redis persistence enabled
- [ ] Kafka replication factor > 1
- [ ] Environment variables set in Vercel
- [ ] TensorFlow model trained and deployed
- [ ] Lambda function tested
- [ ] SES email verified
- [ ] Monitoring alerts configured
- [ ] Backup strategy in place
- [ ] SSL/TLS enabled for all services
- [ ] Rate limiting configured

## Cost Optimization

### Free Tier Friendly
- **Vercel**: Free tier includes 100GB bandwidth
- **AWS Lambda**: 1M free requests/month
- **CloudWatch Events**: 1M free custom events/month
- **SES**: 62,000 free emails/month (verified emails)

### Cost Saving Tips
1. Use Redis Cloud free tier (30MB)
2. Deploy Lambda in same region as Redis
3. Use CloudWatch Logs retention (7 days free)
4. Optimize Lambda execution time
5. Cache forecast predictions

## Support

For issues or questions:
1. Check logs in respective services
2. Verify environment variables
3. Ensure all services are running
4. Check network connectivity
5. Review README.md for common issues

