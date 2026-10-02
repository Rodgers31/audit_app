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

# Project source observations

**PDF artifact identity**: The identity of one validated edition's actual document bytes, recorded with its source association. A download URL or cache filename does not identify those bytes.

**Extraction binding**: Evidence that an individual finding was read from a particular PDF artifact. The source document's latest edition cannot establish an older finding's binding.

**Extraction JSON hash**: A checksum of one finding's stored extraction content. It does not identify the PDF bytes.

**Historical project observation**: One publisher's project statements from an older reporting period, each retaining its own measure, locator and observation date precision.

**Historical identity candidate**: A qualified comparison of separately sourced observations for human consideration. It does not confirm project identity, combine measures, reconcile payments or verify current status.
