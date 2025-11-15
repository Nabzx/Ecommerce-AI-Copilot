import { NextResponse } from 'next/server';

const TF_SERVICE_URL = process.env.TF_SERVICE_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const response = await fetch(`${TF_SERVICE_URL}/predict?symbol=BTCUSD`, {
      next: { revalidate: 10 }, // Cache for 10 seconds
    });

    if (!response.ok) {
      throw new Error('Forecast service unavailable');
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching forecast:', error);
    return NextResponse.json(
      { 
        error: 'Forecast unavailable',
        symbol: 'BTCUSD',
        current_price: 0,
        forecast_price: 0,
        delta: 0,
        confidence: 0,
      },
      { status: 503 }
    );
  }
}

