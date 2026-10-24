# Independently pinned disabled admission policy — B67

This policy release deliberately retains `accepted: false`. Database identity,
role, schema, revision and implementation expectations remain absent; receipt
storage remains unaccepted. It grants no authority, reads no credential and
cannot manufacture a baseline from a target.

Policy bytes are committed independently of the implementation and workflow
packaging. The workflow must checkout this exact policy commit separately and
bind its SHA256. Changing implementation bytes cannot change that policy pin.
The complete B67 executable review and final package readback must cover both
immutable commits before the author round is pushed.

A future accepted policy needs a separate reviewed commit after the immutable
implementation identity exists. Its expectations must be independently supplied,
not learned by the inspector. The owner-admitted exact workflow SHA is supplied
only after the reviewed workflow commit exists. None of that admission is
provisioned here; Actions and all standing activation switches remain OFF.

Disabled policy SHA256: `f04d2960f0d069a5d5798af5a953d6f0efafe41b75ada5043546e51d7fa29407`.

Local exact-hash admission returns exit2 / ADMISSION_DISABLED, with attempted
policy/config/source bindings. This is a refusal control, not hosted database,
writer-custody, receipt-backend or Free-plan acceptance.
