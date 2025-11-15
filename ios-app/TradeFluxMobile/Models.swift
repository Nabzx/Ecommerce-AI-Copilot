//
//  Models.swift
//  TradeFluxMobile
//
//  Data models for TradeFlux AI API responses
//

import Foundation

struct PriceAnalytics: Decodable {
    let lastPrice: Double
    let avgPrice: Double
    let count: Int
    let min: Double
    let max: Double
    let rsi: Double?
    let macd: Double?
    let macdSignal: Double?
    let macdHist: Double?
    let bbUpper: Double?
    let bbMiddle: Double?
    let bbLower: Double?
    let volatility: Double?
    
    enum CodingKeys: String, CodingKey {
        case lastPrice = "last_price"
        case avgPrice = "avg_price"
        case count
        case min
        case max
        case rsi
        case macd
        case macdSignal = "macd_signal"
        case macdHist = "macd_hist"
        case bbUpper = "bb_upper"
        case bbMiddle = "bb_middle"
        case bbLower = "bb_lower"
        case volatility
    }
}

struct Forecast: Decodable {
    let symbol: String
    let currentPrice: Double
    let forecastPrice: Double
    let delta: Double
    let confidence: Double?
    
    enum CodingKeys: String, CodingKey {
        case symbol
        case currentPrice = "current_price"
        case forecastPrice = "forecast_price"
        case delta
        case confidence
    }
}

struct PriceHistory: Decodable {
    let history: [Double]
    let timestamps: [Int64]
}

