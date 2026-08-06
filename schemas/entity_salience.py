from pydantic import BaseModel

class EntitySalience(BaseModel):
    salience_score: int
    current_associations: list[str]
    missing_concepts: list[str]