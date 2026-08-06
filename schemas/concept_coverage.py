from pydantic import BaseModel

class ConceptCoverage(BaseModel):
    covered_concepts: list[str]
    missing_concepts: list[str]
    coverage_score: int
    most_impactful_missing: str