import copy
import pytest
from seeding.domains.debt_timeline.parser import parse_debt_timeline_payload

ROW={'year':2025,'external':400,'domestic':600,'total':1000,'gdp':2000,'gdp_ratio':50}

@pytest.mark.parametrize('field,value', [('year',True),('year','2025'),('total',True),('total',float('nan')),('domestic',float('inf')),('gdp',0),('external',-1)])
def test_parser_refuses_hostile_values_before_any_write(field,value):
    row={**ROW,field:value}
    with pytest.raises(ValueError): parse_debt_timeline_payload({'timeline':[row]})


def test_parser_refuses_duplicate_years():
    with pytest.raises(ValueError): parse_debt_timeline_payload({'timeline':[copy.deepcopy(ROW),copy.deepcopy(ROW)]})


def test_future_month_cannot_be_observed_actual_debt():
    from datetime import date
    from seeding.domains.national_debt.cbk_bulletin import parse_public_debt_table
    future=date.today().year+2
    assert parse_public_debt_table(f'4.1.3 Deficit Financing and Public Debt\nShillings million\n{future}/{future+1}\nDecember 600000 400000 1000000')=={}
