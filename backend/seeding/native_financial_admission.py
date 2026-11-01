"""Prospective source qualification; independent of social draft generation."""
import os

SOURCE_ADMISSION_FLAG = 'SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED'


def source_admission_enabled(values=None):
    """Only an explicit literal true admits newly verified native source cells.

    This grants no source authority by itself and does not enable a generation
    hook, draft, publication, media operation or worker. Existing writer/current
    reader evidence, lineage and quarantine checks remain mandatory.
    """
    raw = (os.environ if values is None else values).get(SOURCE_ADMISSION_FLAG)
    return type(raw) is str and raw == 'true'
