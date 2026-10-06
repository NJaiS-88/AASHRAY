from typing import List
from pydantic import BaseModel, Field

class SourceReference(BaseModel):
    file: str = Field(description="Source PDF filename where evidence was found")
    page: int = Field(description="Page number of the source PDF (1-indexed)")

class ResourceInstruction(BaseModel):
    resource: str = Field(description="Name of the required resource")
    required: bool = Field(default=True, description="Whether this resource is required")
    instructions: List[str] = Field(
        default_factory=list,
        description="Actionable operational instructions or steps for dispatching/handling this resource"
    )
    sources: List[SourceReference] = Field(
        default_factory=list,
        description="Citations to source file and page supporting these instructions"
    )
    evidence_sufficient: bool = Field(
        description="True if retrieved text directly supports instructions; False if insufficient source material"
    )

class FinalResponse(BaseModel):
    scenario_id: str = Field(description="Unique identifier for the scenario")
    scenario: str = Field(description="Text of the scenario")
    query_sources: List[SourceReference] = Field(
        default_factory=list,
        description="Source citations supporting the overall incident/scenario query"
    )
    resources: List[ResourceInstruction] = Field(
        default_factory=list,
        description="List of required resources with corresponding instructions and source citations"
    )
    report: str = Field(
        description="Synthesized operational dispatch report summarizing actions and resource allocations"
    )
    pipeline: str = Field(
        default="llm_llm",
        description="Identifier of the executing pipeline"
    )
