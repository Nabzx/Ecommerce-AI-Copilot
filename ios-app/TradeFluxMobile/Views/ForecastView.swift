//
//  ForecastView.swift
//  TradeFluxMobile
//
//  Forecast tab showing ML predictions
//

import SwiftUI

struct ForecastView: View {
    @StateObject private var viewModel = ForecastViewModel()
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    if viewModel.isLoading {
                        ProgressView("Loading forecast...")
                            .padding()
                    } else if let error = viewModel.error {
                        VStack(spacing: 12) {
                            Image(systemName: "exclamationmark.triangle")
                                .font(.largeTitle)
                                .foregroundColor(.orange)
                            Text("Forecast Unavailable")
                                .font(.headline)
                            Text(error)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .padding()
                    } else if let forecast = viewModel.forecast {
                        // Forecast Card
                        VStack(spacing: 16) {
                            Text("60-Second Forecast")
                                .font(.headline)
                                .foregroundColor(.secondary)
                            
                            // Current Price
                            VStack(spacing: 4) {
                                Text("Current Price")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(formatPrice(forecast.currentPrice))
                                    .font(.title)
                                    .fontWeight(.bold)
                            }
                            
                            // Delta with Arrow
                            HStack(spacing: 8) {
                                Image(systemName: forecast.delta >= 0 ? "arrow.up" : "arrow.down")
                                    .font(.title2)
                                    .foregroundColor(forecast.delta >= 0 ? .green : .red)
                                
                                Text(formatPrice(abs(forecast.delta)))
                                    .font(.title2)
                                    .fontWeight(.semibold)
                                    .foregroundColor(forecast.delta >= 0 ? .green : .red)
                            }
                            
                            Divider()
                            
                            // Forecast Price
                            VStack(spacing: 4) {
                                Text("Forecast Price")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(formatPrice(forecast.forecastPrice))
                                    .font(.title)
                                    .fontWeight(.bold)
                                    .foregroundColor(forecast.delta >= 0 ? .green : .red)
                            }
                            
                            // Confidence
                            if let confidence = forecast.confidence {
                                VStack(spacing: 8) {
                                    Text("Confidence")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    
                                    ProgressView(value: confidence, total: 1.0)
                                        .tint(.orange)
                                    
                                    Text("\(Int(confidence * 100))%")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        }
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(Color(.systemGray6))
                        .cornerRadius(16)
                        
                        // Info Text
                        Text("Prediction based on LSTM neural network trained on historical price data.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                }
                .padding()
            }
            .navigationTitle("Forecast")
            .refreshable {
                await viewModel.loadData()
            }
            .task {
                await viewModel.loadData()
            }
        }
    }
    
    private func formatPrice(_ price: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: price)) ?? "$0.00"
    }
}

@MainActor
class ForecastViewModel: ObservableObject {
    @Published var forecast: Forecast?
    @Published var isLoading = false
    @Published var error: String?
    
    private let apiClient = ApiClient.shared
    
    func loadData() async {
        isLoading = true
        error = nil
        
        do {
            self.forecast = try await apiClient.fetchForecast()
        } catch {
            self.error = "Unable to fetch forecast. Ensure the TensorFlow service is running."
        }
        
        isLoading = false
    }
}

#Preview {
    ForecastView()
}

