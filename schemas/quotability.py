from pydantic import BaseModel

class Quotability(BaseModel):
    has_quotable_sentence: bool
    quotable_sentence: str
    reason: str
    generated_quotable_sentence: str
    missing_elements: list[str]