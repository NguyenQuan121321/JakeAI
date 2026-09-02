export declare class AIService {
    private backendUrl;
    private sessionId;
    constructor(backendUrl?: string);
    setBackendUrl(url: string): void;
    getSessionId(): string;
    private getOrCreateSessionId;
    /**
     * Send chat message to the Go backend API or mock engine
     */
    sendMessage(userMessage: string): Promise<string>;
    /**
     * Built-in intelligent response engine tailored for portfolio projects
     */
    private generateMockResponse;
}
