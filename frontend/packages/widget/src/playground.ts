import { JakeAI } from "./index";

// Start unauthenticated. Paste a short-lived access token from your local
// FinnApiGo login; no signing key or privileged credential belongs in this page.
const tokenInput = document.getElementById("jwt-token") as HTMLInputElement | null;
const backendUrlInput = document.getElementById("backend-url") as HTMLInputElement | null;
const updateBtn = document.getElementById("update-token-btn") as HTMLButtonElement | null;
const openBtn = document.getElementById("open-widget-btn") as HTMLButtonElement | null;

if (tokenInput) {
  tokenInput.value = "";
  tokenInput.placeholder = "Paste a short-lived FinnApiGo access token from your local login";
}

// Initialize widget
const widget = JakeAI.init({
  apiUrl: backendUrlInput?.value || "http://127.0.0.1:8000/api/v1/chat/stream",
  token: "",
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

    if (!token) {
      byokStatus.textContent = "Sign in to FinnApiGo and apply an access token first.";
      return;
    }

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
