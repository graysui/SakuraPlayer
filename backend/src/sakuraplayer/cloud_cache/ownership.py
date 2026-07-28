from __future__ import annotations

from hashlib import sha256

from sakuraplayer.cloud_cache.cleanup import CleanupClaim
from sakuraplayer.cloud_cache.ports.cloud115 import DirectoryInfo
from sakuraplayer.cloud_cache.root_directory import (
    CACHE_ROOT_NAME,
    CACHE_ROOT_PARENT_CID,
)


def root_is_owned(claim: CleanupClaim, info: DirectoryInfo) -> bool:
    return (
        info.cid == claim.cache_root_cid
        and info.parent_cid == CACHE_ROOT_PARENT_CID
        and info.name == CACHE_ROOT_NAME
    )


def task_is_owned(claim: CleanupClaim, info: DirectoryInfo) -> bool:
    return (
        info.cid == claim.task_dir_cid
        and info.parent_cid == claim.cache_root_cid
        and info.name == claim.task_dir_name
    )


def ownership_evidence(
    claim: CleanupClaim,
    *,
    root: DirectoryInfo | None = None,
    task: DirectoryInfo | None = None,
    task_missing: bool = False,
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "account_sha256": sha256(claim.account_key.encode("utf-8")).hexdigest(),
        "binding_id": str(claim.binding_id),
        "root_cid": claim.cache_root_cid,
        "task_cid": claim.task_dir_cid,
        "task_missing": task_missing,
    }
    if root is not None:
        evidence["root_parent_cid"] = root.parent_cid
        evidence["root_name_matches"] = root.name == CACHE_ROOT_NAME
    if task is not None:
        evidence["task_parent_cid"] = task.parent_cid
        evidence["task_name_matches"] = task.name == claim.task_dir_name
    return evidence


__all__ = ["ownership_evidence", "root_is_owned", "task_is_owned"]
