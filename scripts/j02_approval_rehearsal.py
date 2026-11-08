"""Actual Finn identities, two Jake processes and dedicated persistent authority.

Only called inside the guarded J02 standard-hosted PR rehearsal. No standalone
entry point, credential output or local container execution.
"""

from concurrent.futures import ThreadPoolExecutor
import time


def run_approvals(harness, compose, decode, emit):
    h = harness
    for suffix in ("approver", "outsider"):
        code, _ = h.request("finn", "/api/v1/auth/register", body={
            "username": "fixture-" + suffix, "email": suffix + "@example.invalid",
            "password": h.keys["password"], "fullName": "Synthetic approval " + suffix})
        h.check("approval-register-" + suffix, code, 201)
    h.sql("INSERT INTO user_roles SELECT u.id,r.id FROM users u JOIN roles r ON u.tenant_id=r.tenant_id "
          "WHERE u.email IN ('approver@example.invalid','outsider@example.invalid') AND r.name='j02-explicit';")
    requester = h.login()[0]
    approver = h.login(email="approver@example.invalid")[0]
    outsider = h.login(email="outsider@example.invalid")[0]
    foreign = h.login("j02-b")[0]
    approver_id = decode(approver)["sub"]
    compose("up", "-d", "jake-peer")
    h.ready("jake-peer")
    def policy_update(policy, tool="calculator-v1"):
        # Owned synthetic operator provisioning, no application HTTP bypass.
        code = """import asyncio,json,sys
from app.core.approval_authority import ApprovalAuthority,POLICY_KEY,canonical
async def main():
 authority=ApprovalAuthority()
 try:
  policy=json.load(sys.stdin)
  policy['epoch']=int(await authority.store.client.incr('approval:policy-generation'))
  await authority.store.client.set(POLICY_KEY, canonical(policy))
 finally: await authority.close()
asyncio.run(main())
"""
        import json
        compose("exec", "-T", "jake", "python", "-c", code,
                data=json.dumps({"policy": policy, "tool": tool}).encode())
    policy_update("approval-calculator-v1")

    def propose(label, expires=300, assigned=None):
        code, task = h.request("jake", "/api/v1/agent/tasks", token=requester,
                               body={"goal": "Publish approved safe arithmetic: " + label})
        h.check("approval-task-" + label, code, 201)
        prefix = "/api/v1/agent/tasks/" + task["task_id"] + "/runs"
        code, run = h.request("jake", prefix, token=requester, body={"approval": {
            "approver_id": assigned or approver_id, "expression": "6 * 7", "expires_in": expires}})
        if assigned == decode(requester)["sub"]:
            h.check("approval-self-proposal-denied", code, 403)
            return None, None
        h.check("approval-run-" + label, code, 201)
        path = prefix + "/" + run["run_id"] + "/approvals/" + run["pending_approval_id"]
        code, record = h.request("jake-peer", path, token=requester)
        h.check("approval-peer-durable-read-" + label, code, 200)
        h.check("approval-immutable-bindings-" + label,
            all(record["action"][k] == v for k, v in {
                "tenant_id": "j02-a", "requester_id": decode(requester)["sub"],
                "approver_id": approver_id, "task_id": task["task_id"], "run_id": run["run_id"],
                "tool_name": "calculator", "policy_version": "approval-calculator-v1",
                "tool_version": "calculator-v1"}.items()), True)
        return path, record

    def decide(path, record, yes=True, who=None):
        return h.request("jake-peer", path, token=who or approver,
                         body={"approved": yes, "action_hash": record["action_hash"]})

    def consume(path, record, service="jake", who=None, digest=None):
        return h.request(service, path + "/consume", token=who or requester,
                         body={"action_hash": digest or record["action_hash"]})

    path, record = propose("positive")
    for label, who, expected in (("self", requester, 403), ("unassigned", outsider, 403), ("tenant", foreign, 404)):
        h.check("approval-decision-denied-" + label, decide(path, record, who=who)[0], expected)
    h.check("approval-owner-hidden", h.request("jake-peer", path, token=outsider)[0], 404)
    h.check("approval-positive-decision", decide(path, record)[0], 200)
    h.check("approval-decision-replay", decide(path, record)[0], 409)
    h.check("approval-consume-unassigned", consume(path, record, who=outsider)[0], 404)
    h.check("approval-consume-foreign", consume(path, record, who=foreign)[0], 404)
    h.check("approval-consume-hash-changed", consume(path, record, digest="0" * 64)[0], 409)
    # Kill/recreate both process images plus the real store before consume. No
    # worker has RAM task/run state; AOF volume is retained and image is unchanged.
    compose("stop", "-t", "15", "jake", "jake-peer", "approval")
    compose("up", "-d", "--force-recreate", "approval", "jake", "jake-peer")
    h.ready("jake"); h.ready("jake-peer")
    code, receipt = consume(path, record, service="jake-peer")
    h.check("approval-positive-after-process-store-recreation", code, 200)
    h.check("approval-real-calculator-publication", receipt.get("result"), {"expression": "6 * 7", "result": 42})
    h.check("approval-ciphertext-not-returned", any(k.startswith("_") for k in receipt), False)
    h.check("approval-replay-after-restart", consume(path, record)[0], 409)

    path, record = propose("race")
    h.check("approval-race-decision", decide(path, record)[0], 200)
    def race(index):
        return consume(path, record, service="jake" if index % 2 else "jake-peer")[0]
    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(race, range(12)))
    h.check("approval-two-worker-race-one-publication", statuses.count(200), 1)
    h.check("approval-two-worker-race-eleven-denials", statuses.count(409), 11)
    emit("approval_race", workers=2, attempts=12, published=statuses.count(200), conflicts=statuses.count(409))

    for terminal in ("pending", "rejected", "cancelled", "expired"):
        path, record = propose(terminal, expires=5 if terminal == "expired" else 300)
        if terminal != "pending":
            h.check("approval-terminal-decision-" + terminal, decide(path, record, yes=terminal != "rejected")[0], 200)
        if terminal == "cancelled":
            h.check("approval-cancel", h.request("jake-peer", path + "/cancel", token=requester, body={})[0], 200)
        if terminal == "expired":
            time.sleep(6)
        h.check("approval-terminal-no-effect-" + terminal, consume(path, record)[0], 409)
    propose("self", assigned=decode(requester)["sub"])

    # A fresh actual approver/session becomes stale after a real Finn epoch edit.
    path, record = propose("approver-revoked")
    h.check("approval-before-approver-revocation", decide(path, record)[0], 200)
    h.sql("UPDATE users SET auth_epoch=auth_epoch+1 WHERE email='approver@example.invalid';")
    h.check("approval-revoked-approver-no-effect", consume(path, record)[0], 401)
    approver = h.login(email="approver@example.invalid")[0]

    path, record = propose("store-outage")
    h.check("approval-before-authority-outage", decide(path, record)[0], 200)
    compose("stop", "-t", "10", "approval")
    try:
        h.check("approval-store-outage-no-effect", consume(path, record)[0], 503)
    finally:
        compose("up", "-d", "approval")
    h.check("approval-store-recovery", consume(path, record)[0], 200)

    path, record = propose("identity-outage")
    h.check("approval-before-identity-outage", decide(path, record)[0], 200)
    compose("stop", "-t", "15", "redis")
    try:
        h.check("approval-real-state-outage-no-effect", consume(path, record)[0], 503)
    finally:
        compose("start", "redis")
    h.check("approval-state-recovery", consume(path, record)[0], 200)
    path, record = propose("shared-policy-change")
    h.check("approval-before-shared-policy-change", decide(path, record)[0], 200)
    policy_update("approval-calculator-v2")
    try:
        h.check("approval-old-worker-stale-shared-policy", consume(path, record, service="jake-peer")[0], 409)
    finally:
        policy_update("approval-calculator-v1")
    h.check("approval-old-decision-cannot-return-after-policy-recovery", consume(path, record)[0], 409)
    path, record = propose("new-policy-generation")
    h.check("approval-new-policy-generation-decision", decide(path, record)[0], 200)
    h.check("approval-new-policy-generation-consume", consume(path, record)[0], 200)
    path, record = propose("requester-revoked")
    h.check("approval-before-requester-revocation", decide(path, record)[0], 200)
    h.sql("UPDATE users SET auth_epoch=auth_epoch+1 WHERE email='j02-a@example.invalid';")
    h.check("approval-revoked-requester-no-effect", consume(path, record)[0], 401)
    compose("stop", "-t", "15", "jake-peer")
    emit("approval_authority", status="PASS", store="dedicated actual Redis AOF always/noeviction",
         effect="atomic one-time publication of existing safe calculator output", unsafe_tools="DISABLED",
         general_checkpoint_resume="DISABLED", distinct_version_rollback="NOT_RUN")
