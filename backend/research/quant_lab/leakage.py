"""Time-bound validation that prevents future labels entering earlier partitions."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from research.quant_lab.contracts import ChronologicalSplit, DateWindow


PartitionName = Literal["train", "validation", "test"]


class FeatureLabelObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    partition: PartitionName
    feature_as_of: date
    label_from: date
    label_to: date

    @model_validator(mode="after")
    def validate_sequence(self) -> "FeatureLabelObservation":
        if not self.feature_as_of < self.label_from <= self.label_to:
            raise ValueError("forward label must begin after feature_as_of")
        return self


def validate_observation(
    observation: FeatureLabelObservation,
    split: ChronologicalSplit,
) -> None:
    window: DateWindow = getattr(split, observation.partition)
    if observation.feature_as_of < window.start:
        raise ValueError("feature observation starts before its partition")
    if observation.label_to > window.end:
        raise ValueError("forward label crosses its partition boundary")


def validate_observations(
    observations: list[FeatureLabelObservation],
    split: ChronologicalSplit,
) -> None:
    for observation in observations:
        validate_observation(observation, split)
