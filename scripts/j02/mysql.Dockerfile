# Isolated non-root rehearsal artifact, not a production database deployment.
FROM mysql@sha256:a0225d1ea6631c8bc2385dc4c2faba17bbf1834ecf369e1659a9a382bd8d5dd7

# The rehearsal uses the native mysql client/server as UID 999. mysql-shell's
# bundled Python environment and the root-only gosu helper are not required.
# Remove their vulnerable code, update the remaining OS packages, then scan
# this exact resulting artifact under the unchanged HIGH/CRITICAL policy.
USER root
RUN microdnf remove -y mysql-shell \
    && microdnf upgrade -y \
    && microdnf clean all \
    && rm -f /usr/local/bin/gosu
USER 999:999
