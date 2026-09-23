import { JakeAI } from "./index";

// Validly signed JWT token matching backend JWT_SECRET_KEY (a8f3e2b1c9d7f6e5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2)
// Payload: {"sub":"user-demo-001","uid":101,"tid":"tenant-demo","role":"admin","perms":["chat:write","rag:read"],"type":"access","exp":253402300799}
const DEFAULT_DEV_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJzdWIiOiJ1c2VyLWRlbW8tMDAxIiwidWlkIjoxMDEsInRpZCI6InRlbmFudC1kZW1vIiwicm9sZSI6ImFkbWluIiwicGVybXMiOlsiY2hhdDp3cml0ZSIsInJhZzpyZWFkIl0sInR5cGUiOiJhY2Nlc3MiLCJleHAiOjI1MzQwMjMwMDc5OX0." +
  "vjTAyaIxrc6JwGmere5k8Up9kADaamq27HPSVU6wi3c";

const tokenInput = document.getElementById("jwt-token") as HTMLInputElement | null;
const backendUrlInput = document.getElementById("backend-url") as HTMLInputElement | null;
const updateBtn = document.getElementById("update-token-btn") as HTMLButtonElement | null;
const openBtn = document.getElementById("open-widget-btn") as HTMLButtonElement | null;

if (tokenInput) {
  tokenInput.value = DEFAULT_DEV_TOKEN;
}

// Initialize widget
const widget = JakeAI.init({
  apiUrl: backendUrlInput?.value || "http://127.0.0.1:8000/api/v1/chat/stream",
  token: DEFAULT_DEV_TOKEN,
  theme: "dark",
  initialOpen: false,
});

if (updateBtn && tokenInput && backendUrlInput) {
  updateBtn.addEventListener("click", () => {
    const newToken = tokenInput.value.trim();
    const newUrl = backendUrlInput.value.trim();
    widget.configure({
      apiUrl: newUrl,
      token: newToken,
    });
    alert("JakeAI widget configuration updated!");
  });
}

if (openBtn) {
  openBtn.addEventListener("click", () => {
    JakeAI.open();
  });
}

// BYOK Key Registration Handler
const byokBtn = document.getElementById("save-byok-btn") as HTMLButtonElement | null;
const byokKeyInput = document.getElementById("byok-key") as HTMLInputElement | null;
const byokProviderSelect = document.getElementById("byok-provider") as HTMLSelectElement | null;
const byokStatus = document.getElementById("byok-status") as HTMLDivElement | null;

if (byokBtn && byokKeyInput && byokProviderSelect && byokStatus && tokenInput) {
  byokBtn.addEventListener("click", async () => {
    const apiKey = byokKeyInput.value.trim();
    const provider = byokProviderSelect.value;
    const token = tokenInput.value.trim();

    if (!apiKey) {
      alert("Please enter an API key.");
      return;
    }

    byokStatus.textContent = "Encrypting and registering key with AES-256-GCM...";
    byokStatus.style.color = "#58a6ff";

    try {
      const resp = await fetch("http://127.0.0.1:8000/api/v1/byok/keys", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ provider, api_key: apiKey }),
      });

      if (resp.ok) {
        const data = await resp.json();
        byokStatus.textContent = `✅ Successfully encrypted and stored ${data.provider} key (${data.masked_key}). JakeAI is now proxying with your API key and reducing tokens!`;
        byokStatus.style.color = "#3fb950";
      } else {
        const err = await resp.json();
        byokStatus.textContent = `❌ Error: ${err.detail || "Failed to register key"}`;
        byokStatus.style.color = "#f85149";
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      byokStatus.textContent = `❌ Network Error: ${message}`;
      byokStatus.style.color = "#f85149";
    }
  });
}
