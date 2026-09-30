"""The evaluation set: questions.yaml and the documents in corpus/."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

EVALUATION_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = EVALUATION_DIR / "questions.yaml"
CORPUS_DIR = EVALUATION_DIR / "corpus"
NOT_DOCUMENTS = frozenset({"ATTRIBUTION.md"})  # licence notes that live next to the documents


class EvalQuestion(BaseModel):
    id: str
    split: Literal["test", "dev"]
    type: Literal["answerable", "unanswerable", "injection"]
    question: str
    source: str
    pages: list[int] = Field(default_factory=list)
    evidence: str | None = None
    # Each inner list is one required fact; any one of its strings counts as a match.
    expected_facts: list[list[str]] = Field(default_factory=list)
    # Injection questions only: the right behaviour, and text that must never appear in the answer.
    expect: Literal["answer", "refuse"] | None = None
    forbidden: list[str] = Field(default_factory=list)
    notes: str | None = None

    @property
    def should_answer(self) -> bool:
        if self.type == "injection":
            return self.expect == "answer"
        return self.type == "answerable"


class EvalSet(BaseModel):
    version: int
    canary: str
    questions: list[EvalQuestion]

    def split(self, name: str) -> list[EvalQuestion]:
        return [q for q in self.questions if name in ("all", q.split)]


def load_questions(path: Path = QUESTIONS_FILE) -> EvalSet:
    with path.open(encoding="utf-8") as file:
        return EvalSet.model_validate(yaml.safe_load(file))


def corpus_files(directory: Path = CORPUS_DIR) -> list[Path]:
    return sorted(
        path for path in directory.iterdir() if path.is_file() and path.name not in NOT_DOCUMENTS
    )
