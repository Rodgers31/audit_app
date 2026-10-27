"""One vocabulary for CoB fiscal subperiod parsing and annual-authority refusal."""
import re

# Cover descriptor -> (published subperiod label, fiscal end month).
# Financial parsing keeps its existing ordered descriptors and period values.
COB_PERIOD_DESCRIPTORS = (
    ('FIRST NINE MONTHS', '9M', 3),
    ('FIRST SIX MONTHS', 'H1', 12),
    ('FIRST HALF', 'H1', 12),
    ('FIRST QUARTER', 'Q1', 9),
    ('HALF YEAR', 'H1', 12),
)
_SUBPERIOD = re.compile(r'\b(?:'+ '|'.join(re.escape(item[0]) for item in COB_PERIOD_DESCRIPTORS)
    + r'|FIRST THREE MONTHS|(?:SECOND|THIRD|FOURTH) QUARTER|QUARTER\s*[1-4]|Q[1-4])\b', re.I)


def has_subperiod_scope(text):
    # Actual cover/foreword line wrapping and hyphenation do not change scope.
    normalized = ' '.join(re.sub(r'[-_.]', ' ', text).split())
    return _SUBPERIOD.search(normalized) is not None
