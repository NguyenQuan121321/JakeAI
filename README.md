# JakeAI — Go Backend & AI Hub

JakeAI Backend is a high-performance API service built in Go (Golang) designed to handle AI chat completions (Gemini API) and proxy live tool calls to portfolio services (**FinnApiGo**, **VovinamApiNode**).

The frontend client is integrated directly into the developer's portfolio application.

---

## Architecture Overview

```
JakeAI/
├── backend/
│   ├── main.go          # HTTP server, CORS, chat handler
│   └── go.mod           # Go module definition
├── .gitignore
└── README.md
```

---

## API Endpoints

### 1. Health Check (`GET /health`)
```json
{
  "status": "ok",
  "service": "JakeAI Backend (Go)"
}
```

### 2. Chat Completion (`POST /chat`)
**Request Body**:
```json
{
  "message": "Explain FinnApiGo architecture",
  "sessionId": "jake-sess-123456"
}
```

**Response Body**:
```json
{
  "response": "FinnApiGo is a high-performance financial API built with Go...",
  "toolCalls": [
    {
      "tool": "test_finnapi",
      "params": {
        "endpoint": "/api/v1/quote",
        "symbol": "AAPL"
      }
    }
  ]
}
```

---

## Local Development

```bash
cd backend
go run main.go
```

The server listens on `http://localhost:8080` by default.

---

## License

MIT License. Copyright (c) Nguyen Quan.
