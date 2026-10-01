# County debt accounting

County borrowing and unpaid bills describe different obligations. A total of selected borrowing contracts does not establish complete county liability coverage.

## Language

**County debt instrument**: One county borrowing contract identified by its issuer's explicit reference within a declared identity namespace.
_Avoid_: Lender bucket, report snapshot

**Debt stock observation**: One source's account of an instrument's outstanding balance at a stated reporting date; missing and zero balances are distinct.
_Avoid_: Redemption line, new borrowing

**Creditor aggregate**: A national balance grouped by creditor, which may cover many contracts.
_Avoid_: Individual instrument

**Redemption line**: Face value redeeming on one security maturity date, without asserting outstanding stock coverage.
_Avoid_: Debt total

**Pending bills**: Unpaid obligations reported separately from borrowing instruments.
_Avoid_: Loan principal
