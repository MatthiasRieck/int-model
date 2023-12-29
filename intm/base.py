"""Base classes"""

from typing import Optional
from humps.camel import case

from pydantic import BaseModel, Extra


class RootModel(BaseModel):
    """Root Graph QL Class"""

    typename: Optional[str] = None

    class Config:
        """Pydantic Config for GraphQlBase"""

        alias_generator = case
        allow_population_by_field_name = True
        populate_by_name = True
        extra = Extra.forbid
