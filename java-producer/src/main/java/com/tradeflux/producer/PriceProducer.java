package com.tradeflux.producer;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import java.net.URI;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

public class PriceProducer {
    private static final String COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com";
    private static final String KAFKA_TOPIC = "crypto_ticks";
    private static final String KAFKA_BOOTSTRAP_SERVERS = "localhost:9092";
    private static final int INITIAL_RECONNECT_DELAY_SECONDS = 1;
    private static final int MAX_RECONNECT_DELAY_SECONDS = 30;

    private final ObjectMapper objectMapper;
    private final KafkaProducer<String, String> kafkaProducer;
    private WebSocketClient webSocketClient;
    private volatile boolean isRunning = false;
    private volatile int reconnectAttempts = 0;

    public PriceProducer() {
        this.objectMapper = new ObjectMapper();
        this.kafkaProducer = createKafkaProducer();
    }

    private KafkaProducer<String, String> createKafkaProducer() {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, KAFKA_BOOTSTRAP_SERVERS);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.ACKS_CONFIG, "1");
        props.put(ProducerConfig.RETRIES_CONFIG, 3);

        return new KafkaProducer<>(props);
    }

    private WebSocketClient createWebSocketClient() {
        try {
            URI serverUri = new URI(COINBASE_WS_URL);
            
            return new WebSocketClient(serverUri) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    System.out.println("WebSocket connection opened to Coinbase");
                    reconnectAttempts = 0;
                    
                    // Subscribe to BTC-USD ticker channel
                    try {
                        Map<String, Object> subscribeMessage = new HashMap<>();
                        subscribeMessage.put("type", "subscribe");
                        subscribeMessage.put("product_ids", new String[]{"BTC-USD"});
                        subscribeMessage.put("channels", new String[]{"ticker"});
                        
                        String subscribeJson = objectMapper.writeValueAsString(subscribeMessage);
                        send(subscribeJson);
                        System.out.println("Subscribed to BTC-USD ticker channel");
                    } catch (Exception e) {
                        System.err.println("Error sending subscription message: " + e.getMessage());
                        e.printStackTrace();
                    }
                }

                @Override
                public void onMessage(String message) {
                    try {
                        // Parse Coinbase ticker message
                        @SuppressWarnings("unchecked")
                        Map<String, Object> tickerMessage = objectMapper.readValue(message, Map.class);
                        
                        String messageType = (String) tickerMessage.get("type");
                        
                        // Only process ticker messages
                        if (!"ticker".equals(messageType)) {
                            return;
                        }
                        
                        // Extract required fields
                        String priceStr = (String) tickerMessage.get("price");
                        String productId = (String) tickerMessage.get("product_id");
                        
                        if (priceStr == null || productId == null) {
                            return;
                        }
                        
                        // Convert product_id from BTC-USD to BTCUSD
                        String symbol = productId.replace("-", "");
                        double price = Double.parseDouble(priceStr);
                        
                        // Get timestamp from message or use current time
                        long timestamp = System.currentTimeMillis() / 1000;
                        // Coinbase provides time in ISO 8601 format, but we use current time for simplicity
                        // This ensures consistent timestamp format
                        
                        // Create tick data with required format
                        Map<String, Object> tickData = new HashMap<>();
                        tickData.put("symbol", symbol);
                        tickData.put("price", price);
                        tickData.put("ts", timestamp);
                        
                        // Publish to Kafka
                        produceToKafka(tickData);
                        
                    } catch (Exception e) {
                        System.err.println("Error processing WebSocket message: " + e.getMessage());
                        // Don't print stack trace for every non-ticker message
                        if (e.getMessage() != null && !e.getMessage().contains("Cannot deserialize")) {
                            e.printStackTrace();
                        }
                    }
                }

                @Override
                public void onClose(int code, String reason, boolean remote) {
                    System.out.println("WebSocket connection closed: " + reason + " (code: " + code + ")");
                    
                    if (isRunning) {
                        scheduleReconnect();
                    }
                }

                @Override
                public void onError(Exception ex) {
                    System.err.println("WebSocket error: " + ex.getMessage());
                    ex.printStackTrace();
                }
            };
        } catch (Exception e) {
            System.err.println("Error creating WebSocket client: " + e.getMessage());
            e.printStackTrace();
            return null;
        }
    }

    private void scheduleReconnect() {
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
        int delaySeconds = Math.min(
            INITIAL_RECONNECT_DELAY_SECONDS * (1 << Math.min(reconnectAttempts, 4)),
            MAX_RECONNECT_DELAY_SECONDS
        );
        
        reconnectAttempts++;
        System.out.println("Scheduling reconnection in " + delaySeconds + " seconds (attempt " + reconnectAttempts + ")");
        
        new Thread(() -> {
            try {
                Thread.sleep(delaySeconds * 1000L);
                if (isRunning) {
                    connect();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }).start();
    }

    private void connect() {
        try {
            if (webSocketClient != null) {
                webSocketClient.close();
            }
            
            webSocketClient = createWebSocketClient();
            if (webSocketClient != null) {
                webSocketClient.connect();
            }
        } catch (Exception e) {
            System.err.println("Error connecting WebSocket: " + e.getMessage());
            e.printStackTrace();
            scheduleReconnect();
        }
    }

    private void produceToKafka(Map<String, Object> tickData) {
        try {
        String jsonMessage = objectMapper.writeValueAsString(tickData);
        ProducerRecord<String, String> record = new ProducerRecord<>(KAFKA_TOPIC, jsonMessage);
        
        kafkaProducer.send(record, (metadata, exception) -> {
            if (exception != null) {
                System.err.println("Error sending message to Kafka: " + exception.getMessage());
            } else {
                System.out.println("Published: " + jsonMessage);
            }
        });
        } catch (Exception e) {
            System.err.println("Error producing to Kafka: " + e.getMessage());
            e.printStackTrace();
        }
    }

    public void start() {
        System.out.println("Starting TradeFlux AI Price Producer (Coinbase WebSocket)...");
        System.out.println("Connecting to Coinbase WebSocket: " + COINBASE_WS_URL);
        System.out.println("Kafka Bootstrap Servers: " + KAFKA_BOOTSTRAP_SERVERS);
        System.out.println("Kafka Topic: " + KAFKA_TOPIC);
        System.out.println("Press Ctrl+C to stop\n");

        isRunning = true;

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("\nShutting down producer...");
            isRunning = false;
            if (webSocketClient != null) {
                webSocketClient.close();
            }
            kafkaProducer.close();
        }));

        // Initial connection
        connect();

        // Keep the main thread alive
        try {
            while (isRunning) {
                Thread.sleep(1000);
                }
            } catch (InterruptedException e) {
                System.out.println("Producer interrupted");
                Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) {
        PriceProducer producer = new PriceProducer();
        producer.start();
    }
}
