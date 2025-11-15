//
//  ApiClient.swift
//  TradeFluxMobile
//
//  API client for TradeFlux AI backend
//

import Foundation

class ApiClient: ObservableObject {
    static let shared = ApiClient()
    
    private let baseURL = "http://localhost:3000/api"
    
    private init() {}
    
    func fetchPriceAnalytics() async throws -> PriceAnalytics {
        guard let url = URL(string: "\(baseURL)/price") else {
            throw ApiError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ApiError.invalidResponse
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(PriceAnalytics.self, from: data)
    }
    
    func fetchForecast() async throws -> Forecast {
        guard let url = URL(string: "\(baseURL)/forecast") else {
            throw ApiError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ApiError.invalidResponse
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(Forecast.self, from: data)
    }
    
    func fetchPriceHistory() async throws -> PriceHistory {
        guard let url = URL(string: "\(baseURL)/history") else {
            throw ApiError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ApiError.invalidResponse
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(PriceHistory.self, from: data)
    }
}

enum ApiError: Error {
    case invalidURL
    case invalidResponse
    case decodingError
}

