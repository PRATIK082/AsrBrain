"""Provenance-first registry (Phase 2).

The registry is the *evidence spine* of the workspace: it records which artifact
was ingested, in which version, what was extracted from it, where every claim
came from and which deterministic tool validated it.

Design rules (ADR-0002, ADR-0003):

* the existing ``canonical.db`` stays the retrieval source of truth — the registry
  is **additive** and never rewrites it;
* the DDL is **portable** so the same migrations can run on SQLite (dev) and
  PostgreSQL (system of record, ADR-0010) without being written twice;
* every stored fact carries its provenance: artifact version, source location,
  extraction method, confidence and lifecycle state.
"""
from .models import (
    AnswerAudit,
    Artifact,
    ArtifactVersion,
    Citation,
    EvidenceClaim,
    Job,
    Project,
    SourceLocation,
    ValidationResult,
    Workspace,
)
from .migrator import apply_migrations, current_version, migration_files
from .store import RegistryStore
from .jobs import JobStore, run_worker

__all__ = [
    "AnswerAudit",
    "Artifact",
    "ArtifactVersion",
    "Citation",
    "EvidenceClaim",
    "Job",
    "JobStore",
    "Project",
    "RegistryStore",
    "SourceLocation",
    "ValidationResult",
    "Workspace",
    "apply_migrations",
    "current_version",
    "migration_files",
    "run_worker",
]
