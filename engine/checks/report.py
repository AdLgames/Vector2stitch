"""The check report.

Structured, not printed: the editor overlays it on the canvas, the service
decides whether to deliver on it, and CI compares it between engine versions.
Formatting for a terminal is one view of it, not what it is.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """What a finding means for delivery."""

    BLOCK = "block"
    """This file must not be delivered. It will break thread, break a needle,
    or sew something the customer did not ask for."""
    WARN = "warn"
    """Worth a human's attention. Costs machine time or looks wrong, but will
    sew."""
    PASS = "pass"
    """Recorded so the report says what was actually checked, rather than
    leaving silence to mean either "fine" or "never looked"."""


class Finding(BaseModel):
    """One rule's verdict."""

    model_config = ConfigDict(frozen=True)

    rule: str
    severity: Severity
    message: str
    object_id: str | None = None
    """Which object is at fault, where the rule can tell. Checks point at
    objects because that is what a reviewer edits -- a stitch index is not
    something anyone can act on."""
    location_mm: tuple[float, float] | None = None
    value: float | None = None
    limit: float | None = None


class CheckReport(BaseModel):
    """Everything the checks found, and enough context to reproduce it."""

    model_config = ConfigDict(frozen=True)

    engine_version: str
    profile_ref: str
    profile_overrides: list[str] = Field(default_factory=list)
    machine_ref: str | None = None
    findings: list[Finding] = Field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.BLOCK]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARN]

    @property
    def ok(self) -> bool:
        """Deliverable. Warnings do not stop a file; blockers do."""
        return not self.blockers

    def summary(self) -> str:
        checked = len({f.rule for f in self.findings})
        return (
            f"{len(self.blockers)} blocking, {len(self.warnings)} warning, "
            f"{checked} rules run"
        )

    def format(self, show_passes: bool = False) -> str:
        """A terminal view of the report."""
        lines = []
        for finding in self.findings:
            if finding.severity is Severity.PASS and not show_passes:
                continue
            where = f" [{finding.object_id}]" if finding.object_id else ""
            lines.append(
                f"{finding.severity.value.upper():<5} {finding.rule}{where}: {finding.message}"
            )
        lines.append(self.summary())
        return "\n".join(lines)
