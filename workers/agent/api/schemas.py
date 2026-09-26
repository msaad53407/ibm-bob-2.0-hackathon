"""HTTP shapes: Agent API contract (:8003/decide, /propose, /execute)."""
from typing import Literal

from pydantic import BaseModel, field_validator

# Domain concept: the only legal Traffic flip targets (ADR-0002).
Target = Literal["stable", "canary"]


class DecideOut(BaseModel):
    verdict: str
    reasons: list[str]


class ProposalSet(BaseModel):
    id: int | None
    verdict: str
    reasons: list[str]
    proposals: list[dict]


class Approve(BaseModel):
    target: Target
    approver: str = "human"
    proposal_id: int  # required: Execution accepts only approved Proposal IDs

    @field_validator("approver")
    @classmethod
    def _approver_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("approver must not be empty")
        return v
