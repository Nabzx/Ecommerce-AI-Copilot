import { NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';

export async function GET() {
  try {
    const redis = getRedisClient();
    // Try BTCUSD first (Coinbase), fallback to BTCUSDT (Binance)
    let key = 'price_history:BTCUSD';
    let prices = await redis.lrange(key, 0, -1);
    
    // Fallback to BTCUSDT if BTCUSD doesn't exist
    if (!prices || prices.length === 0) {
      key = 'price_history:BTCUSDT';
      prices = await redis.lrange(key, 0, -1);
    }

    if (!prices || prices.length === 0) {
      return NextResponse.json({
        history: [],
        timestamps: [],
      });
    }

    // Get last 200 prices
    const recentPrices = prices.slice(-200);
    
    // Generate timestamps (synthesize from current time, going backwards)
    const now = Date.now();
    const timestamps = recentPrices.map((_, index) => {
      // Assume prices arrive roughly every second, go backwards
      const secondsAgo = recentPrices.length - index - 1;
      return now - (secondsAgo * 1000);
    });

    // Convert prices to numbers
    const priceValues = recentPrices.map(p => parseFloat(p as string)).filter(p => !isNaN(p));

    return NextResponse.json({
      history: priceValues,
      timestamps: timestamps,
    });
  } catch (error) {
    console.error('Error fetching price history:', error);
    return NextResponse.json(
      { error: 'Failed to fetch price history' },
      { status: 500 }
    );
  }
}

