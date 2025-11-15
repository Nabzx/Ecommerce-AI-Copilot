//
//  ContentView.swift
//  TradeFluxMobile
//
//  Main tab view for TradeFlux AI mobile app
//

import SwiftUI

struct ContentView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            OverviewView()
                .tabItem {
                    Label("Overview", systemImage: "chart.line.uptrend.xyaxis")
                }
                .tag(0)
            
            IndicatorsView()
                .tabItem {
                    Label("Indicators", systemImage: "waveform.path.ecg")
                }
                .tag(1)
            
            ForecastView()
                .tabItem {
                    Label("Forecast", systemImage: "crystal.ball")
                }
                .tag(2)
        }
        .accentColor(.orange)
    }
}

#Preview {
    ContentView()
}

