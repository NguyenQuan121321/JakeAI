import * as React from "react";
import {
  Plus,
  RefreshCw,
  RotateCcw,
  Ban,
  Trash2,
  AlertTriangle,
  Lock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/ui/status-indicator";
import {
  SUPPORTED_PROVIDERS,
  PROVIDER_DISPLAY_NAMES,
} from "@/api/services/providers.service";
import type { BYOKProviderItem } from "@/api/types/domain";
import {
  useByokKeysQuery,
  useDeleteByokKeyMutation,
  useRevokeByokKeyMutation,
} from "@/api/hooks/use-byok-query";
import { byokService } from "@/api/services/byok.service";
import { ByokValidationBadge, type ByokValidationState } from "./byok-validation-badge";
import { ByokKeyDialog } from "./byok-key-dialog";
import { ApiError } from "@/api/client/api-error";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

export function ByokVaultTable() {
  const { data: byokData, refetch } = useByokKeysQuery();
  const deleteMutation = useDeleteByokKeyMutation();
  const revokeMutation = useRevokeByokKeyMutation();

  // Dialog states
  const [dialogOpen, setDialogOpen] = React.useState<boolean>(false);
  const [dialogMode, setDialogMode] = React.useState<"add" | "rotate">("add");
  const [selectedProvider, setSelectedProvider] = React.useState<string>("openai");

  // Confirmation dialogs
  const [confirmDeleteProvider, setConfirmDeleteProvider] = React.useState<string | null>(null);
  const [confirmRevokeProvider, setConfirmRevokeProvider] = React.useState<string | null>(null);

  // Live validation states per provider
  const [validationStatuses, setValidationStatuses] = React.useState<
    Record<string, { state: ByokValidationState; error?: string | null; latencyMs?: number }>
  >({});

  const keysMap = React.useMemo(() => {
    const map = new Map<string, BYOKProviderItem>();
    for (const item of byokData?.keys || []) {
      map.set(item.provider.toLowerCase(), item);
    }
    return map;
  }, [byokData]);

  const handleValidateStored = async (provider: string) => {
    setValidationStatuses((prev) => ({
      ...prev,
      [provider]: { state: "validating", error: null },
    }));

    const startTime = performance.now();
    try {
      const res = await byokService.validateExistingKey(provider);
      const latencyMs = Math.round(performance.now() - startTime);

      if (res.is_valid) {
        setValidationStatuses((prev) => ({
          ...prev,
          [provider]: { state: "valid", error: null, latencyMs },
        }));
      } else {
        setValidationStatuses((prev) => ({
          ...prev,
          [provider]: {
            state: "invalid",
            error: res.error || "Key validation failed on provider probe",
            latencyMs,
          },
        }));
      }
    } catch (err: unknown) {
      const latencyMs = Math.round(performance.now() - startTime);
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setValidationStatuses((prev) => ({
            ...prev,
            [provider]: {
              state: "provider_unavailable",
              error: err.message || "Provider endpoint is unreachable (503)",
              latencyMs,
            },
          }));
        } else if (err.status === 429) {
          setValidationStatuses((prev) => ({
            ...prev,
            [provider]: {
              state: "rate_limited",
              error: err.message || "Quota rate limited (429)",
              latencyMs,
            },
          }));
        } else if (err.isNetworkError) {
          setValidationStatuses((prev) => ({
            ...prev,
            [provider]: {
              state: "network_error",
              error: "Network connection failed",
              latencyMs,
            },
          }));
        } else {
          setValidationStatuses((prev) => ({
            ...prev,
            [provider]: {
              state: "invalid",
              error: err.message,
              latencyMs,
            },
          }));
        }
      } else {
        setValidationStatuses((prev) => ({
          ...prev,
          [provider]: {
            state: "network_error",
            error: err instanceof Error ? err.message : "Validation error",
            latencyMs,
          },
        }));
      }
    }
  };

  const handleOpenAdd = (provider = "openai") => {
    setSelectedProvider(provider);
    setDialogMode("add");
    setDialogOpen(true);
  };

  const handleOpenRotate = (provider: string) => {
    setSelectedProvider(provider);
    setDialogMode("rotate");
    setDialogOpen(true);
  };

  const handleConfirmRevoke = async () => {
    if (!confirmRevokeProvider) return;
    try {
      await revokeMutation.mutateAsync(confirmRevokeProvider);
      setConfirmRevokeProvider(null);
      refetch();
    } catch {
      // Error handled by mutation
    }
  };

  const handleConfirmDelete = async () => {
    if (!confirmDeleteProvider) return;
    try {
      await deleteMutation.mutateAsync(confirmDeleteProvider);
      setConfirmDeleteProvider(null);
      refetch();
    } catch {
      // Error handled by mutation
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold tracking-tight">BYOK (Bring Your Own Key) Vault</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Encrypted with AES-256-GCM. Raw keys are never retained or logged.
          </p>
        </div>
        <Button size="sm" onClick={() => handleOpenAdd()} leftIcon={<Plus className="h-4 w-4" />}>
          Add Provider Key
        </Button>
      </div>

      <div className="rounded-lg border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-muted/50 border-b text-muted-foreground font-semibold">
              <tr>
                <th scope="col" className="px-4 py-3">Provider</th>
                <th scope="col" className="px-4 py-3">Masked Preview</th>
                <th scope="col" className="px-4 py-3">Vault Status</th>
                <th scope="col" className="px-4 py-3">Validation Probe</th>
                <th scope="col" className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {SUPPORTED_PROVIDERS.map((prov) => {
                const item = keysMap.get(prov);
                const isConfigured = Boolean(item && (item.configured || item.masked_key) && item.status !== "revoked");
                const isRevoked = item?.status === "revoked";
                const valInfo = validationStatuses[prov];

                return (
                  <tr key={prov} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-md bg-primary/10 text-primary">
                          <Lock className="h-3.5 w-3.5" />
                        </div>
                        <div>
                          <div className="font-medium text-foreground">
                            {PROVIDER_DISPLAY_NAMES[prov] || prov}
                          </div>
                          <div className="text-[11px] text-muted-foreground font-mono">
                            {prov}
                          </div>
                        </div>
                      </div>
                    </td>

                    <td className="px-4 py-3.5">
                      {item?.masked_key ? (
                        <span className="font-mono text-xs bg-muted px-2 py-1 rounded border">
                          {item.masked_key}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">
                          No key configured
                        </span>
                      )}
                    </td>

                    <td className="px-4 py-3.5">
                      {isRevoked ? (
                        <StatusIndicator status="failed" customLabel="Revoked" variant="badge" />
                      ) : isConfigured ? (
                        <StatusIndicator status="healthy" customLabel="Active" variant="badge" />
                      ) : (
                        <StatusIndicator status="idle" customLabel="Not Configured" variant="badge" />
                      )}
                    </td>

                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <ByokValidationBadge
                          status={valInfo?.state || (isConfigured ? "valid" : "untested")}
                          errorMessage={valInfo?.error}
                        />
                        {valInfo?.latencyMs !== undefined && (
                          <span className="text-[11px] text-muted-foreground font-mono">
                            {valInfo.latencyMs}ms
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {isConfigured ? (
                          <>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleValidateStored(prov)}
                              title="Validate Stored Key via Upstream Probe"
                              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
                            >
                              Validate
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenRotate(prov)}
                              title="Rotate Stored Key"
                              leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                            >
                              Rotate
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirmRevokeProvider(prov)}
                              className="text-amber-600 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-950/30"
                              title="Revoke Key"
                              leftIcon={<Ban className="h-3.5 w-3.5" />}
                            >
                              Revoke
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirmDeleteProvider(prov)}
                              className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                              title="Delete Key"
                              leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                            >
                              Delete
                            </Button>
                          </>
                        ) : isRevoked ? (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleOpenRotate(prov)}
                              leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                            >
                              Re-activate / Rotate
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirmDeleteProvider(prov)}
                              className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                              leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                            >
                              Delete
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenAdd(prov)}
                            leftIcon={<Plus className="h-3.5 w-3.5" />}
                          >
                            Configure Key
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add / Rotate Key Dialog */}
      <ByokKeyDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={dialogMode}
        initialProvider={selectedProvider}
        onSuccess={() => refetch()}
      />

      {/* Confirm Revoke Dialog */}
      <Dialog open={Boolean(confirmRevokeProvider)} onOpenChange={(open) => !open && setConfirmRevokeProvider(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <div className="flex items-center gap-2 text-amber-600">
              <AlertTriangle className="h-5 w-5" />
              <DialogTitle>Revoke Provider Key?</DialogTitle>
            </div>
            <DialogDescription>
              This will suspend runtime inference for {confirmRevokeProvider ? PROVIDER_DISPLAY_NAMES[confirmRevokeProvider] : ""} without wiping key metadata.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRevokeProvider(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmRevoke}
              isLoading={revokeMutation.isPending}
            >
              Confirm Revoke
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm Delete Dialog */}
      <Dialog open={Boolean(confirmDeleteProvider)} onOpenChange={(open) => !open && setConfirmDeleteProvider(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <div className="flex items-center gap-2 text-rose-600">
              <Trash2 className="h-5 w-5" />
              <DialogTitle>Permanently Delete Key?</DialogTitle>
            </div>
            <DialogDescription>
              Permanently purge the encrypted API key for {confirmDeleteProvider ? PROVIDER_DISPLAY_NAMES[confirmDeleteProvider] : ""} from the tenant vault. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDeleteProvider(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              isLoading={deleteMutation.isPending}
            >
              Confirm Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
