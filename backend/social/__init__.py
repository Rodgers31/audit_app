"""Manual editorial workflow and durable social delivery contracts.

Importing this package never starts a scheduler or loads credentials.
"""
from . import models as _domain_models
from .connections import models as _connection_models

# Register the complete additive schema before callers capture its table set.
# Both supported import modes retain their own application's existing Base.
_domain_models.SOCIAL_TABLES = tuple(
    table for table in _domain_models.Base.metadata.sorted_tables
    if table.name.startswith("social_")
)
