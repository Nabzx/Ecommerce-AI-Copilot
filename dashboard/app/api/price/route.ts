import { NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';

export async function GET() {
  try {
    const redis = getRedisClient();
    // Try BTCUSD first (Coinbase), fallback to BTCUSDT (Binance)
    let key = 'analytics:BTCUSD';
    let data = await redis.hgetall(key);
    
    // Fallback to BTCUSDT if BTCUSD doesn't exist
    if (!data || Object.keys(data).length === 0) {
      key = 'analytics:BTCUSDT';
      data = await redis.hgetall(key);
    }

    if (!data || Object.keys(data).length === 0) {
      return NextResponse.json({
        last_price: 0,
        avg_price: 0,
        min: 0,
        max: 0,
        count: 0,
        rsi: null,
        macd: null,
        macd_signal: null,
        macd_hist: null,
        bb_upper: null,
        bb_middle: null,
        bb_lower: null,
        volatility: null,
      });
    }

    return NextResponse.json({
      last_price: parseFloat(data.last_price || '0'),
      avg_price: parseFloat(data.avg_price || '0'),
      min: parseFloat(data.min || '0'),
      max: parseFloat(data.max || '0'),
      count: parseInt(data.count || '0'),
      rsi: data.rsi ? parseFloat(data.rsi) : null,
      macd: data.macd ? parseFloat(data.macd) : null,
      macd_signal: data.macd_signal ? parseFloat(data.macd_signal) : null,
      macd_hist: data.macd_hist ? parseFloat(data.macd_hist) : null,
      bb_upper: data.bb_upper ? parseFloat(data.bb_upper) : null,
      bb_middle: data.bb_middle ? parseFloat(data.bb_middle) : null,
      bb_lower: data.bb_lower ? parseFloat(data.bb_lower) : null,
      volatility: data.volatility ? parseFloat(data.volatility) : null,
    });
  } catch (error) {
    console.error('Error fetching price data:', error);
    return NextResponse.json(
      { error: 'Failed to fetch price data' },
      { status: 500 }
    );
  }
}
