# PR #86 CI secret dispositions

The two findings at commit `632ff2ffdf11cb1d11265cbfe49dd645f5e66786`
(`frontend/src/playground.ts:5` and
`frontend/packages/widget/src/playground.ts:5`, rule `generic-api-key`) belong to
the same synthetic demo JWT. It was **usable**, with admin claims and an expiry
in year 9999, through JakeAI's development signing-key fallbacks. It was not an
inert fixture when introduced. No production configuration or upstream rotation
has been verified.

Both playgrounds now start unauthenticated. For a connected development demo,
log in to your local FinnApiGo instance, paste its short-lived access token, and
click **Apply Token & Reconnect**. Opening the widget without a token still
allows UI inspection; authenticated chat and BYOK require your login token.
Do not put signing keys or tokens in frontend environment variables or source.

Before permitting the two exact historical fingerprints in `.gitleaksignore`,
the token was made inert at JakeAI's verifier boundary: its decoded signature
SHA256 (`aaf884500d7d25e5ca1504276b3f8050a82f02c3950bcb7c6456a40f7e943a34`)
is rejected before environment or key selection. The regression test
`test_retired_playground_token_is_inert` exercises the original token and padded
encoding in development, test, local, and production modes. Existing configured
development login tokens remain supported. Keep this revocation when deploying
or rolling back frontend changes. Older deployments remain vulnerable to the
old token until updated; deployments that reused published demo signing keys
with real data need key rotation and exposure assessment separately.

These exceptions only match the original commit/path/rule/line fingerprints.
All test and playground path exclusions and broad value exclusions were removed.
Pre-existing unverified fingerprint exceptions were removed too. PR history
scanning remains enabled; new credentials on the same paths must fail scanning.
No history was rewritten. This disposition does not certify the repository's
entire older history or other branches: full-history findings need separate
credential-by-credential review, never blanket exceptions.
