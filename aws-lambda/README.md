# AWS Lambda Alerting Function

This Lambda function monitors Redis analytics and triggers alerts based on market conditions.

## Alert Conditions

1. **Price Change Alert**: Triggers when price moves >1.5% in <5 minutes
2. **Volatility Alert**: Triggers when volatility exceeds threshold (default: 500)
3. **MACD Cross Alert**: Triggers on MACD signal line crossings

## Deployment Instructions

### 1. Package the Lambda Function

```bash
cd aws-lambda
pip install -r requirements.txt -t .
zip -r lambda_function.zip . -x "*.pyc" "__pycache__/*" "*.git*" "README.md"
```

### 2. Create IAM Role

1. Go to AWS IAM Console
2. Create a new role for Lambda
3. Attach policies:
   - `AWSLambdaBasicExecutionRole` (for CloudWatch logs)
   - Custom policy for SES (if using email alerts):
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [{
         "Effect": "Allow",
         "Action": ["ses:SendEmail", "ses:SendRawEmail"],
         "Resource": "*"
       }]
     }
     ```

### 3. Create Lambda Function

1. Go to AWS Lambda Console
2. Create function from scratch
3. Upload `lambda_function.zip`
4. Set handler: `lambda_function.lambda_handler`
5. Set runtime: Python 3.11
6. Set timeout: 30 seconds
7. Set memory: 256 MB
8. Attach the IAM role created above

### 4. Configure Environment Variables

In Lambda function configuration, add:

```
REDIS_HOST=<your-redis-host>
REDIS_PORT=6379
REDIS_PASSWORD=<optional>
SES_REGION=us-east-1
ALERT_EMAIL=<your-email@example.com>
WEBHOOK_URL=<optional-webhook-url>
```

### 5. Set Up CloudWatch Events Trigger

1. In Lambda function, go to "Add trigger"
2. Select "EventBridge (CloudWatch Events)"
3. Create rule:
   - Rule type: Schedule expression
   - Schedule expression: `rate(1 minute)`
4. Enable the trigger

### 6. Verify SES (for Email Alerts)

If using email alerts:
1. Go to AWS SES Console
2. Verify your email address
3. Move out of SES sandbox (if needed) for production

## Free Tier Considerations

- Lambda: 1M free requests/month, 400K GB-seconds compute
- CloudWatch Events: 1M free custom events/month
- SES: 62,000 free emails/month (if verified)

## Testing Locally

```python
from lambda_function import lambda_handler

event = {}
context = {}

result = lambda_handler(event, context)
print(result)
```

## Monitoring

- Check CloudWatch Logs for function execution
- Monitor Lambda metrics (invocations, errors, duration)
- Set up CloudWatch alarms for errors

