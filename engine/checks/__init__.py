"""Automated checks: what stands between the engine and a ruined garment.

Every file goes through these, and a blocking finding means the file is not
delivered. They are deliberately structural rather than aesthetic -- they
catch what will break thread, break a needle, or sew something the customer
did not ask for. Whether a design *looks* right is a human's judgement and
always will be.
"""

from __future__ import annotations

from engine.checks.report import CheckReport, Finding, Severity
from engine.checks.rules import (
    check_budgets,
    check_calibration,
    check_density,
    check_machine_fit,
    check_not_empty,
    check_satin_width,
    check_stitch_length,
    check_ties,
)
from engine.ir.schema import IRDocument
from engine.machines.setup import MachineSetup
from engine.plan import StitchPlan
from engine.profiles.loader import FabricProfile

__all__ = ["CheckReport", "Finding", "Severity", "run_checks"]

_RULES = (
    check_not_empty,
    check_stitch_length,
    check_density,
    check_satin_width,
    check_ties,
    check_budgets,
    check_calibration,
)


def run_checks(
    doc: IRDocument,
    plan: StitchPlan,
    profile: FabricProfile,
    setup: MachineSetup | None = None,
) -> CheckReport:
    """Run every rule and collect the findings.

    Rules run in a fixed order and none of them stops the others: a report
    that gave up at the first blocker would send a reviewer round the loop
    once per problem.
    """
    findings = []
    for rule in _RULES:
        findings.extend(rule(doc, plan, profile))
    findings.extend(check_machine_fit(setup))

    return CheckReport(
        engine_version=plan.engine_version,
        profile_ref=plan.profile_ref,
        profile_overrides=list(plan.profile_overrides),
        machine_ref=setup.machine_ref if setup else None,
        findings=findings,
    )
