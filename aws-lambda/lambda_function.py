"""
AWS Lambda function for TradeFlux AI alerts
Monitors Redis analytics and triggers alerts based on conditions
"""

import json
import os
import redis
import boto3
from datetime import datetime, timedelta
from typing import Dict, Optional

# Configuration from environment variables
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)

# Alert thresholds
PRICE_CHANGE_THRESHOLD = 0.015  # 1.5%
VOLATILITY_THRESHOLD = 500.0  # Adjust based on typical volatility
MACD_CROSS_THRESHOLD = 0.1  # MACD histogram threshold for crossing

# AWS Services
SES_REGION = os.environ.get('SES_REGION', 'us-east-1')
ALERT_EMAIL = os.environ.get('ALERT_EMAIL', '')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')

ses_client = None
if SES_REGION:
    ses_client = boto3.client('ses', region_name=SES_REGION)

def get_redis_client():
    """Create Redis client"""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5
    )

def get_analytics(redis_client, symbol="BTCUSD"):
    """Fetch analytics from Redis"""
    key = f"analytics:{symbol}"
    data = redis_client.hgetall(key)
    
    if not data:
        return None
    
    # Convert string values to appropriate types
    analytics = {}
    for k, v in data.items():
        try:
            if k == 'count':
                analytics[k] = int(v)
            else:
                analytics[k] = float(v)
        except (ValueError, TypeError):
            analytics[k] = v
    
    return analytics

def check_price_change_alert(analytics: Dict, prev_analytics: Optional[Dict]) -> Optional[str]:
    """Check if price moved >1.5% in <5 minutes"""
    if not prev_analytics or 'last_price' not in prev_analytics:
        return None
    
    prev_price = prev_analytics.get('last_price', 0)
    current_price = analytics.get('last_price', 0)
    
    if prev_price == 0:
        return None
    
    price_change_pct = abs((current_price - prev_price) / prev_price)
    
    if price_change_pct > PRICE_CHANGE_THRESHOLD:
        direction = "up" if current_price > prev_price else "down"
        return f"Price Alert: BTC moved {price_change_pct*100:.2f}% {direction} " \
               f"(${prev_price:.2f} → ${current_price:.2f})"
    
    return None

def check_volatility_alert(analytics: Dict) -> Optional[str]:
    """Check if volatility exceeds threshold"""
    volatility = analytics.get('volatility', 0)
    
    if volatility > VOLATILITY_THRESHOLD:
        return f"Volatility Alert: High volatility detected ({volatility:.2f})"
    
    return None

def check_macd_cross_alert(analytics: Dict, prev_analytics: Optional[Dict]) -> Optional[str]:
    """Check for MACD crossing events"""
    if not prev_analytics:
        return None
    
    prev_hist = prev_analytics.get('macd_hist', 0)
    curr_hist = analytics.get('macd_hist', 0)
    
    # Check for cross (sign change or crossing zero)
    if prev_hist * curr_hist < 0:  # Sign change
        direction = "bullish" if curr_hist > 0 else "bearish"
        macd = analytics.get('macd', 0)
        signal = analytics.get('macd_signal', 0)
        return f"MACD Cross Alert: {direction.capitalize()} cross detected " \
               f"(MACD: {macd:.4f}, Signal: {signal:.4f})"
    
    # Check for significant histogram change
    hist_change = abs(curr_hist - prev_hist)
    if hist_change > MACD_CROSS_THRESHOLD:
        return f"MACD Momentum Alert: Significant histogram change ({hist_change:.4f})"
    
    return None

def send_email_alert(subject: str, message: str):
    """Send alert via AWS SES"""
    if not ses_client or not ALERT_EMAIL:
        print(f"Email not configured. Would send: {subject}")
        return
    
    try:
        ses_client.send_email(
            Source=ALERT_EMAIL,
            Destination={'ToAddresses': [ALERT_EMAIL]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': message}}
            }
        )
        print(f"Email alert sent: {subject}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def send_webhook_alert(message: str):
    """Send alert via webhook"""
    if not WEBHOOK_URL:
        print(f"Webhook not configured. Would send: {message}")
        return
    
    import urllib.request
    import urllib.parse
    
    try:
        data = json.dumps({'text': message}).encode('utf-8')
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5)
        print(f"Webhook alert sent: {message}")
    except Exception as e:
        print(f"Failed to send webhook: {e}")

def lambda_handler(event, context):
    """
    Main Lambda handler
    Expected to be triggered by CloudWatch Events every minute
    """
    try:
        redis_client = get_redis_client()
        
        # Get current analytics
        analytics = get_analytics(redis_client, "BTCUSD")
        
        if not analytics:
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No analytics data available'})
            }
        
        # Get previous analytics from context or cache (simplified - in production use DynamoDB/ElastiCache)
        # For now, we'll check conditions that don't require previous state
        prev_analytics = None  # In production, fetch from cache/DynamoDB
        
        alerts = []
        
        # Check price change (requires previous state - simplified here)
        # price_alert = check_price_change_alert(analytics, prev_analytics)
        # if price_alert:
        #     alerts.append(price_alert)
        
        # Check volatility
        vol_alert = check_volatility_alert(analytics)
        if vol_alert:
            alerts.append(vol_alert)
        
        # Check MACD cross (requires previous state - simplified here)
        # macd_alert = check_macd_cross_alert(analytics, prev_analytics)
        # if macd_alert:
        #     alerts.append(macd_alert)
        
        # Send alerts
        for alert in alerts:
            send_email_alert("TradeFlux AI Alert", alert)
            send_webhook_alert(alert)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Alert check completed',
                'alerts_triggered': len(alerts),
                'alerts': alerts
            })
        }
        
    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

