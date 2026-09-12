#!/usr/bin/env bash
# ==============================================================================
# JakeAI CI/CD — Deterministic Non-Interactive Cosign Keyless OIDC Signing
# ==============================================================================
# Enforces Task 1 - Task 10 requirements:
# 1. Explicit OIDC token acquisition with audience="sigstore".
# 2. Keyless signing using --identity-token (completely disables device-flow).
# 3. Bounded retries (3 attempts: 0s, 10s, 30s) requesting a fresh token per attempt.
# 4. SBOM attestation with identical retry and fresh-token semantics.
# 5. Cryptographic signature and attestation verification against narrow workflow identity.
# 6. Strict failure on exhausted retries (no bypass, no long-lived keys).
# ==============================================================================

set -euo pipefail

MAX_ATTEMPTS=3
if [ -n "${COSIGN_RETRY_DELAYS:-}" ]; then
  read -r -a BACKOFF_DELAYS <<< "${COSIGN_RETRY_DELAYS}"
else
  BACKOFF_DELAYS=(0 10 30)
fi

log_info() {
  echo "[INFO] $(date -u +'%Y-%m-%dT%H:%M:%SZ') $*"
}

log_warn() {
  echo "::warning::[WARN] $(date -u +'%Y-%m-%dT%H:%M:%SZ') $*" >&2
}

log_error() {
  echo "::error::[ERROR] $(date -u +'%Y-%m-%dT%H:%M:%SZ') $*" >&2
}

# ------------------------------------------------------------------------------
# Function: get_fresh_oidc_token
# Requests a new GitHub Actions OIDC identity token with specified audience.
# Masks the token immediately in GitHub Actions log streams.
# ------------------------------------------------------------------------------
get_fresh_oidc_token() {
  local audience="${1:-sigstore}"

  if [ -z "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ] || [ -z "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ]; then
    log_error "OIDC_CONFIG_ERROR: ACTIONS_ID_TOKEN_REQUEST_URL or ACTIONS_ID_TOKEN_REQUEST_TOKEN environment variables missing. Ensure job permissions include 'id-token: write'."
    return 1
  fi

  local resp_file
  resp_file=$(mktemp)
  local http_code

  # Query GitHub Actions runner local OIDC token broker
  http_code=$(curl -sS -w "%{http_code}" -o "${resp_file}" \
    -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
    "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${audience}" 2>/dev/null || echo "000")

  if [ "${http_code}" != "200" ]; then
    log_warn "OIDC_HTTP_ERROR: GitHub Actions OIDC token request returned HTTP ${http_code} for audience='${audience}'."
    rm -f "${resp_file}"
    return 1
  fi

  local token=""
  if command -v jq >/dev/null 2>&1; then
    token=$(jq -r '.value // empty' "${resp_file}" 2>/dev/null || true)
  elif command -v python3 >/dev/null 2>&1; then
    token=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get('value', ''))" "${resp_file}" 2>/dev/null || true)
  elif command -v python >/dev/null 2>&1; then
    token=$(python -c "import json, sys; print(json.load(open(sys.argv[1])).get('value', ''))" "${resp_file}" 2>/dev/null || true)
  else
    token=$(grep -o '"value":"[^"]*"' "${resp_file}" | cut -d'"' -f4 || true)
  fi
  rm -f "${resp_file}"

  if [ -z "${token}" ]; then
    log_warn "OIDC_PAYLOAD_ERROR: Token response JSON did not contain a valid '.value' payload."
    return 1
  fi

  # Register token for masking in GitHub Actions output streams to prevent log leakage
  # Sent to stderr so runner processes it while stdout contains solely the raw token
  echo "::add-mask::${token}" >&2
  echo "${token}"
}

# ------------------------------------------------------------------------------
# Function: sign_image
# Signs container image using explicit OIDC identity token with 3 bounded retries.
# ------------------------------------------------------------------------------
sign_image() {
  local target_image="${1:?Target image digest is required}"
  log_info "Initiating deterministic non-interactive keyless signing for: ${target_image}"

  local attempt=1
  local sign_success=false

  while [ "${attempt}" -le "${MAX_ATTEMPTS}" ]; do
    local delay="${BACKOFF_DELAYS[$((attempt - 1))]}"
    if [ "${delay}" -gt 0 ]; then
      log_info "Applying backoff delay of ${delay}s before attempt ${attempt}/${MAX_ATTEMPTS}..."
      sleep "${delay}"
    fi

    log_info "Signing attempt ${attempt}/${MAX_ATTEMPTS}: requesting fresh GitHub OIDC token (audience='sigstore')..."
    local id_token
    if ! id_token=$(get_fresh_oidc_token "sigstore"); then
      log_warn "TOKEN_FETCH_FAILURE: Attempt ${attempt}/${MAX_ATTEMPTS} failed to acquire fresh OIDC token."
      attempt=$((attempt + 1))
      continue
    fi

    log_info "Acquired fresh OIDC identity token. Invoking 'cosign sign' with explicit token (timeout=10m)..."
    local exit_code=0
    cosign sign \
      --yes \
      --identity-token "${id_token}" \
      --timeout 10m \
      "${target_image}" || exit_code=$?

    if [ "${exit_code}" -eq 0 ]; then
      log_info "CONTAINER_SIGN_SUCCESS: Image successfully signed on attempt ${attempt}/${MAX_ATTEMPTS}."
      sign_success=true
      break
    else
      log_warn "COSIGN_SIGN_FAILURE: Attempt ${attempt}/${MAX_ATTEMPTS} failed with exit code ${exit_code}."
      attempt=$((attempt + 1))
    fi
  done

  if [ "${sign_success}" != "true" ]; then
    log_error "SECURITY_GATE_FAILURE: Cryptographic container signing failed after ${MAX_ATTEMPTS} attempts. Aborting deployment."
    return 1
  fi
}

# ------------------------------------------------------------------------------
# Function: attest_image
# Attests CycloneDX SBOM to container image using explicit fresh OIDC identity token.
# ------------------------------------------------------------------------------
attest_image() {
  local target_image="${1:?Target image digest is required}"
  local predicate_file="${2:?Predicate file path is required}"

  if [ ! -f "${predicate_file}" ]; then
    log_error "PREDICATE_NOT_FOUND: SBOM predicate file '${predicate_file}' does not exist."
    return 1
  fi

  log_info "Initiating CycloneDX SBOM attestation for: ${target_image} (predicate: ${predicate_file})"

  local attempt=1
  local attest_success=false

  while [ "${attempt}" -le "${MAX_ATTEMPTS}" ]; do
    local delay="${BACKOFF_DELAYS[$((attempt - 1))]}"
    if [ "${delay}" -gt 0 ]; then
      log_info "Applying backoff delay of ${delay}s before attempt ${attempt}/${MAX_ATTEMPTS}..."
      sleep "${delay}"
    fi

    log_info "Attestation attempt ${attempt}/${MAX_ATTEMPTS}: requesting fresh GitHub OIDC token (audience='sigstore')..."
    local id_token
    if ! id_token=$(get_fresh_oidc_token "sigstore"); then
      log_warn "TOKEN_FETCH_FAILURE: Attempt ${attempt}/${MAX_ATTEMPTS} failed to acquire fresh OIDC token for attestation."
      attempt=$((attempt + 1))
      continue
    fi

    log_info "Acquired fresh OIDC identity token. Invoking 'cosign attest' with explicit token (timeout=10m)..."
    local exit_code=0
    cosign attest \
      --yes \
      --identity-token "${id_token}" \
      --timeout 10m \
      --predicate "${predicate_file}" \
      --type cyclonedx \
      "${target_image}" || exit_code=$?

    if [ "${exit_code}" -eq 0 ]; then
      log_info "CONTAINER_ATTEST_SUCCESS: SBOM successfully attested on attempt ${attempt}/${MAX_ATTEMPTS}."
      attest_success=true
      break
    else
      log_warn "COSIGN_ATTEST_FAILURE: Attempt ${attempt}/${MAX_ATTEMPTS} failed with exit code ${exit_code}."
      attempt=$((attempt + 1))
    fi
  done

  if [ "${attest_success}" != "true" ]; then
    log_error "SECURITY_GATE_FAILURE: Container SBOM attestation failed after ${MAX_ATTEMPTS} attempts. Aborting deployment."
    return 1
  fi
}

# ------------------------------------------------------------------------------
# Function: verify_image
# Cryptographically verifies signature and SBOM attestation against workflow identity.
# ------------------------------------------------------------------------------
verify_image() {
  local target_image="${1:?Target image digest is required}"
  local repo_exact="${GITHUB_REPOSITORY:-NguyenQuan121321/JakeAI}"
  local repo_lower
  repo_lower=$(echo "${repo_exact}" | tr '[:upper:]' '[:lower:]')

  # Constrain certificate identity strictly to this repository and cd.yml workflow
  local cert_identity_regex="^https://github\.com/(${repo_exact}|${repo_lower})/\.github/workflows/cd\.yml@refs/heads/main$"
  local expected_issuer="https://token.actions.githubusercontent.com"

  log_info "Verifying cryptographic signature for: ${target_image}"
  log_info "Enforcing Certificate Identity Regex: ${cert_identity_regex}"
  log_info "Enforcing OIDC Issuer: ${expected_issuer}"

  cosign verify \
    --certificate-identity-regexp "${cert_identity_regex}" \
    --certificate-oidc-issuer "${expected_issuer}" \
    "${target_image}"

  log_info "Signature verification succeeded."

  log_info "Verifying CycloneDX SBOM attestation for: ${target_image}"
  cosign verify-attestation \
    --type cyclonedx \
    --certificate-identity-regexp "${cert_identity_regex}" \
    --certificate-oidc-issuer "${expected_issuer}" \
    "${target_image}"

  log_info "SBOM attestation verification succeeded."
}

# ------------------------------------------------------------------------------
# Main Dispatcher
# ------------------------------------------------------------------------------
main() {
  local command="${1:-}"
  shift || true

  case "${command}" in
    sign)
      sign_image "$@"
      ;;
    attest)
      attest_image "$@"
      ;;
    verify)
      verify_image "$@"
      ;;
    *)
      echo "Usage: $0 {sign <image> | attest <image> <predicate_file> | verify <image>}" >&2
      exit 1
      ;;
  esac
}

main "$@"
