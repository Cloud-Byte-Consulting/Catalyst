"""Construct-address validation for the Catalyst API.

The regex below is duplicated client-side in
``clients/catalyst-cli/catalyst_cli.py`` as ``CONSTRUCT_RE``. Parity is
enforced by ``services/catalyst-api/tests/test_construct_pattern_parity.py``
(#172). If you change this pattern, update the CLI in the same PR.
"""

import re

from pydantic import BaseModel, Field, field_validator


CONSTRUCT_PATTERN = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+$")


class ConstructAddress(BaseModel):
    value: str = Field(description="tenant/env/lz/project/app")

    @field_validator("value")
    @classmethod
    def validate_construct(cls, value: str) -> str:
        if not CONSTRUCT_PATTERN.match(value):
            raise ValueError("construct address must be tenant/env/lz/project/app")
        return value
