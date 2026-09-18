import * as React from "react";
import { KeyRound, Eye, EyeOff, RefreshCw } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  SUPPORTED_PROVIDERS,
  PROVIDER_DISPLAY_NAMES,
} from "@/api/services/providers.service";
import {
  useStoreByokKeyMutation,
  useRotateByokKeyMutation,
  useValidateByokKeyMutation,
} from "@/api/hooks/use-byok-query";
import { ByokValidationBadge, type ByokValidationState } from "./byok-validation-badge";
import { ApiError } from "@/api/client/api-error";

export interface ByokKeyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode?: "add" | "rotate";
  initialProvider?: string;
  onSuccess?: () => void;
}

export function ByokKeyDialog({
  open,
  onOpenChange,
  mode = "add",
  initialProvider = "openai",
  onSuccess,
}: ByokKeyDialogProps) {
  const [provider, setProvider] = React.useState<string>(initialProvider);
  // Zero-retention: raw key is strictly transient in component state, wiped on close
  const [apiKey, setApiKey] = React.useState<string>("");
  const [showKey, setShowKey] = React.useState<boolean>(false);
  const [validationState, setValidationState] = React.useState<ByokValidationState>("untested");
  const [validationError, setValidationError] = React.useState<string | null>(null);
  const [validateOnSave, setValidateOnSave] = React.useState<boolean>(true);

  const storeMutation = useStoreByokKeyMutation();
  const rotateMutation = useRotateByokKeyMutation(provider);
  const validateCandidateMutation = useValidateByokKeyMutation();

  // Reset state when opening/closing dialog - zero key retention
  React.useEffect(() => {
    if (open) {
      setProvider(initialProvider);
      setApiKey("");
      setShowKey(false);
      setValidationState("untested");
      setValidationError(null);
    } else {
      setApiKey("");
      setValidationError(null);
      setValidationState("untested");
    }
  }, [open, initialProvider]);

  // Clean up on unmount
  React.useEffect(() => {
    return () => {
      setApiKey("");
    };
  }, []);

  const handleProbeValidation = async () => {
    if (!apiKey.trim()) return;
    setValidationState("validating");
    setValidationError(null);

    try {
      const res = await validateCandidateMutation.mutateAsync({
        provider,
        api_key: apiKey.trim(),
      });

      if (res.is_valid) {
        setValidationState("valid");
        setValidationError(null);
      } else {
        setValidationState("invalid");
        setValidationError(res.error || "Upstream provider rejected the key.");
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setValidationState("provider_unavailable");
          setValidationError(err.message || "Provider endpoint is unavailable (503).");
        } else if (err.status === 429) {
          setValidationState("rate_limited");
          setValidationError(err.message || "Rate limit exceeded on provider endpoint (429).");
        } else if (err.isNetworkError) {
          setValidationState("network_error");
          setValidationError("Network connection failed.");
        } else {
          setValidationState("invalid");
          setValidationError(err.message || "Validation failed.");
        }
      } else {
        setValidationState("network_error");
        setValidationError(err instanceof Error ? err.message : "Validation failed.");
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) return;

    try {
      if (mode === "rotate") {
        await rotateMutation.mutateAsync({
          new_api_key: apiKey.trim(),
          validate_key: validateOnSave,
        });
      } else {
        await storeMutation.mutateAsync({
          provider,
          api_key: apiKey.trim(),
          validate_key: validateOnSave,
        });
      }

      // Wipe key from state immediately
      setApiKey("");
      onOpenChange(false);
      onSuccess?.();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setValidationState("provider_unavailable");
        } else if (err.status === 429) {
          setValidationState("rate_limited");
        } else {
          setValidationState("invalid");
        }
        setValidationError(err.message);
      } else {
        setValidationError(err instanceof Error ? err.message : "Failed to store key.");
      }
    }
  };

  const isPending = storeMutation.isPending || rotateMutation.isPending || validateCandidateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <KeyRound className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle>
                {mode === "rotate"
                  ? `Rotate Key: ${PROVIDER_DISPLAY_NAMES[provider] || provider}`
                  : "Add Provider API Key"}
              </DialogTitle>
              <DialogDescription>
                Zero-retention vault: Encrypted with tenant AES-256-GCM. Never logged or exposed.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          {/* Provider Selection (only for Add mode) */}
          {mode === "add" && (
            <div className="space-y-1.5">
              <label htmlFor="byok-provider-select" className="text-xs font-semibold text-foreground">
                Provider
              </label>
              <select
                id="byok-provider-select"
                aria-label="Target Provider"
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  setValidationState("untested");
                  setValidationError(null);
                }}
                disabled={isPending}
                className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {SUPPORTED_PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {PROVIDER_DISPLAY_NAMES[p] || p}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Secret API Key Input */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="byok-key-input" className="text-xs font-semibold text-foreground">
                {mode === "rotate" ? "New Provider API Key" : "Provider API Key"}
              </label>
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                aria-label={showKey ? "Hide secret key" : "Show secret key"}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                {showKey ? (
                  <>
                    <EyeOff className="h-3 w-3" /> Hide
                  </>
                ) : (
                  <>
                    <Eye className="h-3 w-3" /> Show
                  </>
                )}
              </button>
            </div>
            <Input
              id="byok-key-input"
              type={showKey ? "text" : "password"}
              placeholder="Paste secret API key (min 8 characters)..."
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setValidationState("untested");
                setValidationError(null);
              }}
              autoComplete="off"
              spellCheck={false}
              disabled={isPending}
              required
              minLength={8}
            />
          </div>

          {/* Validation UX Section */}
          <div className="rounded-lg border p-3 bg-muted/30 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">Live Probe Validation:</span>
              <ByokValidationBadge status={validationState} errorMessage={validationError} />
            </div>

            {validationError && (
              <p className="text-xs text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40 p-2 rounded border border-rose-200 dark:border-rose-900">
                {validationError}
              </p>
            )}

            <div className="flex items-center justify-between pt-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleProbeValidation}
                disabled={!apiKey.trim() || apiKey.trim().length < 8 || isPending}
                leftIcon={<RefreshCw className={`h-3 w-3 ${validationState === "validating" ? "animate-spin" : ""}`} />}
              >
                Probe Test Key
              </Button>

              <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={validateOnSave}
                  onChange={(e) => setValidateOnSave(e.target.checked)}
                  className="rounded border-input text-primary focus:ring-primary"
                />
                Validate before saving
              </label>
            </div>
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setApiKey("");
                onOpenChange(false);
              }}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!apiKey.trim() || apiKey.trim().length < 8 || isPending}
              isLoading={storeMutation.isPending || rotateMutation.isPending}
            >
              {mode === "rotate" ? "Confirm Rotation" : "Encrypt & Store Key"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
