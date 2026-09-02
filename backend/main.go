package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

type ChatRequest struct {
	Message   string `json:"message"`
	SessionID string `json:"sessionId"`
}

type ChatResponse struct {
	Response  string     `json:"response"`
	ToolCalls []ToolCall `json:"toolCalls,omitempty"`
}

type ToolCall struct {
	Tool   string                 `json:"tool"`
	Params map[string]interface{} `json:"params"`
}

func enableCORS(w http.ResponseWriter) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
}

func handleChat(w http.ResponseWriter, r *http.Request) {
	enableCORS(w)
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusOK)
		return
	}

	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON payload", http.StatusBadRequest)
		return
	}

	// Scaffold: AI Response logic (Gemini API integration point)
	resp := ChatResponse{
		Response: fmt.Sprintf("Woof! Received query: %s. (JakeAI Go Backend is initialized)", req.Message),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	enableCORS(w)
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"ok","service":"JakeAI Backend (Go)"}`))
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	http.HandleFunc("/chat", handleChat)
	http.HandleFunc("/health", handleHealth)

	log.Printf("JakeAI Go Backend running on port %s...", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
