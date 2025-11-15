//
//  IndicatorsView.swift
//  TradeFluxMobile
//
//  Indicators tab showing RSI, MACD, and Bollinger Bands
//

import SwiftUI

struct IndicatorsView: View {
    @StateObject private var viewModel = IndicatorsViewModel()
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    if viewModel.isLoading {
                        ProgressView("Loading indicators...")
                            .padding()
                    } else if let error = viewModel.error {
                        Text("Error: \(error)")
                            .foregroundColor(.red)
                            .padding()
                    } else if let analytics = viewModel.analytics {
                        // RSI Card
                        IndicatorCard(
                            title: "RSI (14)",
                            value: analytics.rsi != nil ? String(format: "%.2f", analytics.rsi!) : "N/A",
                            status: getRSIStatus(analytics.rsi),
                            color: getRSIColor(analytics.rsi)
                        )
                        
                        // MACD Card
                        VStack(alignment: .leading, spacing: 12) {
                            Text("MACD")
                                .font(.headline)
                            
                            if let macd = analytics.macd {
                                IndicatorRow(label: "MACD Line", value: String(format: "%.4f", macd))
                                
                                if let signal = analytics.macdSignal {
                                    IndicatorRow(label: "Signal Line", value: String(format: "%.4f", signal))
                                }
                                
                                if let hist = analytics.macdHist {
                                    IndicatorRow(
                                        label: "Histogram",
                                        value: String(format: "%.4f", hist),
                                        color: hist >= 0 ? .green : .red
                                    )
                                }
                            } else {
                                Text("Not available")
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                        
                        // Bollinger Bands Card
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Bollinger Bands")
                                .font(.headline)
                            
                            if let upper = analytics.bbUpper,
                               let middle = analytics.bbMiddle,
                               let lower = analytics.bbLower {
                                IndicatorRow(label: "Upper Band", value: formatPrice(upper), color: .orange)
                                IndicatorRow(label: "Middle Band", value: formatPrice(middle), color: .gray)
                                IndicatorRow(label: "Lower Band", value: formatPrice(lower), color: .orange)
                            } else {
                                Text("Not available")
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                    }
                }
                .padding()
            }
            .navigationTitle("Indicators")
            .refreshable {
                await viewModel.loadData()
            }
            .task {
                await viewModel.loadData()
            }
        }
    }
    
    private func getRSIStatus(_ rsi: Double?) -> String {
        guard let rsi = rsi else { return "N/A" }
        if rsi > 70 { return "Overbought" }
        if rsi < 30 { return "Oversold" }
        return "Neutral"
    }
    
    private func getRSIColor(_ rsi: Double?) -> Color {
        guard let rsi = rsi else { return .gray }
        if rsi > 70 { return .red }
        if rsi < 30 { return .green }
        return .blue
    }
    
    private func formatPrice(_ price: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: price)) ?? "$0.00"
    }
}

struct IndicatorCard: View {
    let title: String
    let value: String
    let status: String
    let color: Color
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            Text(value)
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(color)
            Text(status)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct IndicatorRow: View {
    let label: String
    let value: String
    var color: Color = .primary
    
    var body: some View {
        HStack {
            Text(label)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .fontWeight(.semibold)
                .foregroundColor(color)
        }
    }
}

@MainActor
class IndicatorsViewModel: ObservableObject {
    @Published var analytics: PriceAnalytics?
    @Published var isLoading = false
    @Published var error: String?
    
    private let apiClient = ApiClient.shared
    
    func loadData() async {
        isLoading = true
        error = nil
        
        do {
            self.analytics = try await apiClient.fetchPriceAnalytics()
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
}

#Preview {
    IndicatorsView()
}

