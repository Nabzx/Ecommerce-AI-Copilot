//
//  OverviewView.swift
//  TradeFluxMobile
//
//  Overview tab showing key metrics and price chart
//

import SwiftUI
import Charts

struct OverviewView: View {
    @StateObject private var viewModel = OverviewViewModel()
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    if viewModel.isLoading {
                        ProgressView("Loading data...")
                            .padding()
                    } else if let error = viewModel.error {
                        Text("Error: \(error)")
                            .foregroundColor(.red)
                            .padding()
                    } else if let analytics = viewModel.analytics {
                        // Key Metrics Cards
                        VStack(spacing: 12) {
                            MetricCard(
                                title: "Last Price",
                                value: formatPrice(analytics.lastPrice),
                                color: .green
                            )
                            
                            HStack(spacing: 12) {
                                MetricCard(
                                    title: "Average",
                                    value: formatPrice(analytics.avgPrice),
                                    color: .blue
                                )
                                
                                MetricCard(
                                    title: "Volatility",
                                    value: analytics.volatility != nil ? String(format: "%.2f", analytics.volatility!) : "N/A",
                                    color: .purple
                                )
                            }
                            
                            HStack(spacing: 12) {
                                MetricCard(
                                    title: "Min",
                                    value: formatPrice(analytics.min),
                                    color: .red
                                )
                                
                                MetricCard(
                                    title: "Max",
                                    value: formatPrice(analytics.max),
                                    color: .orange
                                )
                            }
                        }
                        .padding(.horizontal)
                        
                        // Price Chart
                        if let history = viewModel.history, !history.history.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Price History")
                                    .font(.headline)
                                    .padding(.horizontal)
                                
                                Chart {
                                    ForEach(Array(history.history.enumerated()), id: \.offset) { index, price in
                                        LineMark(
                                            x: .value("Time", index),
                                            y: .value("Price", price)
                                        )
                                        .foregroundStyle(.orange)
                                        .interpolationMethod(.catmullRom)
                                    }
                                }
                                .frame(height: 200)
                                .padding()
                                .background(Color(.systemGray6))
                                .cornerRadius(12)
                                .padding(.horizontal)
                            }
                        }
                        
                        // Data Points
                        Text("Data Points: \(analytics.count)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding()
                    }
                }
                .padding(.vertical)
            }
            .navigationTitle("TradeFlux AI")
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

struct MetricCard: View {
    let title: String
    let value: String
    let color: Color
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundColor(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

@MainActor
class OverviewViewModel: ObservableObject {
    @Published var analytics: PriceAnalytics?
    @Published var history: PriceHistory?
    @Published var isLoading = false
    @Published var error: String?
    
    private let apiClient = ApiClient.shared
    
    func loadData() async {
        isLoading = true
        error = nil
        
        do {
            async let analyticsTask = apiClient.fetchPriceAnalytics()
            async let historyTask = apiClient.fetchPriceHistory()
            
            let (analyticsResult, historyResult) = try await (analyticsTask, historyTask)
            
            self.analytics = analyticsResult
            self.history = historyResult
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
}

#Preview {
    OverviewView()
}

