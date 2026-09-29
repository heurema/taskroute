"""Small evidence-bound delivery receipt; never an independent semantic acceptance."""

import hashlib
import json
from pathlib import Path


def receipt(packet, run):
    run = Path(run)
    manifest = json.loads((run / "manifest.json").read_text())
    if manifest.get("mode") != "repository":
        raise ValueError("RECEIPT_REQUIRES_REPOSITORY")
    reasons = list(packet.get("reasons", []))
    if packet.get("status") != "READY_FOR_LEAD_REVIEW":
        reasons.append("DELIVERY_NOT_READY")
    hashes = packet.get("file_hashes", {})
    if not hashes or not set(manifest["files"]) <= set(hashes):
        reasons.append("MISSING_FILE_BINDING")
    allowed = set(manifest["files"]) | set(manifest["writable_paths"])
    for name, expected in hashes.items():
        path = run / "workspace" / name
        if (
            name not in allowed
            or path.is_symlink()
            or not path.resolve().is_relative_to((run / "workspace").resolve())
        ):
            raise ValueError("RECEIPT_SCOPE_MISMATCH")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("RECEIPT_CANDIDATE_CHANGED")
    review = packet.get("reviewer_outcome") or {}
    if review.get("verdict") != "APPROVE":
        reasons.append("REVIEW_NOT_APPROVED")
    for section, state in [("acceptance", "MET"), ("non_goals", "KEPT")]:
        rows = review.get(section, [])
        if sorted(x.get("id", "") for x in rows) != sorted(x["id"] for x in manifest[section]):
            reasons.append("INCOMPLETE_REVIEW:" + section)
        if any(x.get("status") != state for x in rows):
            reasons.append("UNRESOLVED_REVIEW:" + section)
    checks = {}
    for source in ["worker_checks", "independent_checks"]:
        rows = packet.get(source, [])
        if sorted(c.get("name", "") for c in rows) != sorted(c["name"] for c in manifest["checks"]):
            reasons.append("INCOMPLETE_CHECKS:" + source)
        if any(c.get("exit_code") != 0 for c in rows):
            reasons.append("FAILED_CHECKS:" + source)
        checks[source] = [{"name": c.get("name"), "exit_code": c.get("exit_code")} for c in rows]
    coordinator = packet.get("coordinator_outcome") or {}
    if coordinator.get("status") != "READY_FOR_LEAD":
        reasons.append("COORDINATOR_NOT_READY")
    originals = json.loads((run / "originals.json").read_text())
    changed = sorted(
        n
        for n, h in hashes.items()
        if hashlib.sha256(originals.get(n, "").encode()).hexdigest() != h
    )
    full = run / "acceptance-packet.json"
    if json.loads(full.read_text()) != packet:
        raise ValueError("RECEIPT_PACKET_MISMATCH")
    return dict(
        status="BLOCKED" if reasons else "CLAUDE_VERIFIED",
        reasons=reasons,
        verification_owner="Claude coordinator and independent reviewer; deterministic checks",
        independent_astra_code_review=False,
        changed_files=changed,
        result=coordinator,
        checks=checks,
        review_findings=review,
        limitations=packet.get("limitations", []),
        backlog=packet.get("backlog", {"status": "UNOBSERVED"}),
        evidence=dict(packet=str(full), sha256=hashlib.sha256(full.read_bytes()).hexdigest()),
        meaning="Reported completion with bound evidence, not proof of semantic correctness or publication authority",
    )
