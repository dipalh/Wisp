"""
Pydantic schemas for the directory suggestion output.

These models are passed directly to Gemini's response_schema (structured output),
so all field descriptions act as instructions to the model.
"""
from pydantic import BaseModel, Field


class FileMapping(BaseModel):
    original_path: str = Field(description="Current file path as indexed")
    suggested_path: str = Field(
        description="Proposed relative path in the new structure, using forward slashes, no leading slash"
    )


class DirectoryProposal(BaseModel):
    name: str = Field(description="Short scheme name, e.g. 'By Project' or 'By File Type'")
    rationale: str = Field(description="1-2 sentences explaining the logic behind this structure")
    reasons: list[str] = Field(
        min_length=1,
        description="Concrete reasons this strategy is useful, e.g. grouping by project, client, or workflow.",
    )
    citations: list[str] = Field(
        min_length=1,
        description="Evidence references (file paths or IDs) supporting the proposal.",
    )
    folder_tree: list[str] = Field(
        description="List of directory paths that make up the proposed structure, e.g. ['Projects/Backend/', 'Media/Images/']"
    )
    mappings: list[FileMapping] = Field(
        description="Explicit mapping from each file's current path to its proposed new location"
    )


class DirectorySuggestions(BaseModel):
    proposals: list[DirectoryProposal] = Field(
        description="2 to 3 distinct directory organization proposals"
    )
    recommendation: str = Field(
        description="Which proposal is recommended and why, in 1-2 sentences"
    )
