"""Validated configurable segmentation ontology."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OntologyClass(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    class_id: int = Field(alias="id", ge=0)
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class LabelOntology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str
    classes: tuple[OntologyClass, ...]
    confidence: dict[str, str]

    @model_validator(mode="after")
    def _unique_and_complete(self) -> "LabelOntology":
        ids = [entry.class_id for entry in self.classes]
        names = [entry.name for entry in self.classes]
        if ids != list(range(11)):
            raise ValueError("initial ontology must contain ordered class IDs 0 through 10")
        if len(names) != len(set(names)):
            raise ValueError("ontology class names must be unique")
        required = {"verified", "high", "medium", "low", "unknown"}
        if set(self.confidence) != required:
            raise ValueError("ontology must define all confidence meanings")
        return self


def load_ontology(path: str | Path) -> LabelOntology:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return LabelOntology.model_validate(payload)
