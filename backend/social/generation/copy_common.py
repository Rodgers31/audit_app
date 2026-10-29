"""Display-only exact-decimal quantities, shared by generated post templates."""
from decimal import Decimal, ROUND_HALF_UP, localcontext


def compact_value(fact):
    """Return (readable quantity, approximate); never alter the evidence cell."""
    with localcontext() as context:
        context.prec = 80
        multiplier = {'units': 1, 'thousands': 1000, 'millions': 1000000, 'billions': 1000000000}
        value = Decimal(fact.value) * multiplier[fact.scale]
        scales = [(Decimal(1000000000), 'billion'), (Decimal(1000000), 'million'), (Decimal(1000), 'thousand')]
        selected = next(((size, label) for size, label in scales if abs(value) >= size), None)
        if selected is None:
            return format(value.normalize() if value else Decimal(0), ',f'), False
        size, label = selected
        rounded = (value / size).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        if abs(rounded) >= 1000 and label != 'billion':
            size *= 1000
            label = 'million' if label == 'thousand' else 'billion'
            rounded = (value / size).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        number = format(rounded, ',f').rstrip('0').rstrip('.')
        return f'{number} {label}', rounded * size != value
