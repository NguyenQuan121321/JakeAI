// Go Backend AI Service & Smart Fallback Mock Engine (TypeScript)
import { GoBackendChatRequest, GoBackendChatResponse } from '../types';

export class AIService {
  private backendUrl: string;
  private sessionId: string;

  constructor(backendUrl: string = '') {
    this.backendUrl = backendUrl.replace(/\/$/, '');
    this.sessionId = this.getOrCreateSessionId();
  }

  public setBackendUrl(url: string): void {
    this.backendUrl = url.replace(/\/$/, '');
  }

  public getSessionId(): string {
    return this.sessionId;
  }

  private getOrCreateSessionId(): string {
    if (typeof window === 'undefined') return 'jake-ssr-' + Date.now();
    try {
      let id = window.sessionStorage.getItem('jakeai_session_id');
      if (!id) {
        id = 'jake-' + Math.random().toString(36).substring(2, 10) + '-' + Date.now();
        window.sessionStorage.setItem('jakeai_session_id', id);
      }
      return id;
    } catch {
      return 'jake-sess-' + Date.now();
    }
  }

  /**
   * Send chat message to the Go backend API or mock engine
   */
  public async sendMessage(userMessage: string): Promise<string> {
    if (this.backendUrl) {
      try {
        const payload: GoBackendChatRequest = {
          message: userMessage,
          sessionId: this.sessionId
        };

        const res = await fetch(`${this.backendUrl}/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
          },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          throw new Error(`Backend responded with HTTP status ${res.status}`);
        }

        const data = (await res.json()) as GoBackendChatResponse;
        return data.response || data.reply || data.message || JSON.stringify(data);
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.warn('[JakeAI] Go Backend request failed, switching to local agent:', errorMsg);
      }
    }

    // Fallback to local intelligent mock agent
    return this.generateMockResponse(userMessage);
  }

  /**
   * Built-in intelligent response engine tailored for portfolio projects
   */
  private generateMockResponse(query: string): Promise<string> {
    return new Promise((resolve) => {
      setTimeout(() => {
        const q = query.toLowerCase();

        if (q.includes('finnapi') || q.includes('finn') || q.includes('stock') || q.includes('chứng khoán')) {
          resolve(
            "📈 **FinnApiGo** là nền tảng API tài chính hiệu năng cao được xây dựng bằng **Go (Golang)**!\n\n" +
            "**Tính năng nổi bật:**\n" +
            "- Dữ liệu chứng khoán theo thời gian thực & tra cứu mã ticker\n" +
            "- Tận dụng **Goroutines** xử lý song song hàng ngàn request đồng thời với độ trễ cực thấp (< 5ms)\n" +
            "- Tích hợp tỷ giá ngoại tệ & phân tích thị trường\n\n" +
            "Bạn có thể thử yêu cầu: *'Test FinnApiGo /api/v1/quote?symbol=AAPL'* nhé!"
          );
        } else if (q.includes('vovinam') || q.includes('martial') || q.includes('võ') || q.includes('đai')) {
          resolve(
            "🥋 **VovinamApiNode** là hệ thống API chuyên biệt cho môn phái Vovinam Việt Võ Đạo xây dựng bằng **Node.js & Express**!\n\n" +
            "**Tính năng nổi bật:**\n" +
            "- Cơ sở dữ liệu kỹ thuật đầy đủ (đòn chân tấn công, thế khóa gỡ, quyền pháp)\n" +
            "- Lộ trình thi lên đai, chương trình huấn luyện & tính điểm giải đấu\n" +
            "- RESTful API chuẩn hóa JSON Schema\n\n" +
            "Hãy hỏi Jake nếu bạn muốn tra cứu danh sách kỹ thuật hay chương trình đai nhé!"
          );
        } else if (q.includes('jake') || q.includes('who are you') || q.includes('corgi') || q.includes('bạn là ai')) {
          resolve(
            "🐕 Gâu! Mình là **Jake**, chú cún Corgi hướng dẫn viên thông minh trên portfolio của **Nguyễn Hoàng Anh Quân**!\n\n" +
            "Mình chạy bằng **TypeScript + React Component**, sử dụng hardware-accelerated GPU 60 FPS, và kết nối trực tiếp với backend **Go (Golang)** để trả lời câu hỏi & test API tự động!"
          );
        } else if (q.includes('test') || q.includes('api') || q.includes('endpoint')) {
          resolve(
            "🛠️ [TOOL_CALL: test_finnapi({ \"endpoint\": \"/api/v1/quote\", \"params\": { \"symbol\": \"AAPL\" } })]\n\n" +
            "*Pawsome!* Mock API test executed successfully:\n```json\n{\n  \"status\": 200,\n  \"symbol\": \"AAPL\",\n  \"price\": 234.85,\n  \"currency\": \"USD\",\n  \"change\": \"+1.45%\"\n}\n```"
          );
        } else {
          resolve(
            "🐾 Câu hỏi tuyệt vời! Mình có thể giúp bạn khám phá:\n" +
            "- **FinnApiGo** (Backend Go tài chính & chứng khoán)\n" +
            "- **VovinamApiNode** (API võ thuật Vovinam trên Node.js)\n" +
            "- **JakeAI** (Kiến trúc TypeScript, React & Backend Go)\n" +
            "- Chạy thử trực tiếp các API endpoint!"
          );
        }
      }, 500 + Math.random() * 300);
    });
  }
}
