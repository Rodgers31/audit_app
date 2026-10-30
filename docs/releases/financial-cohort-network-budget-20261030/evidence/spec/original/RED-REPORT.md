# PR858 hard-phase review: independently reproduced RED

Valid P2 hard-phase protection gap on immutable candidate 7, matching commit `d0da4996327213049614cd8f09b373bcaa856a23`. This is a defense/contract gap, not evidence of a source-authority or publication bypass. The integration retains its cooperative 600-second deadline checks.

The independent real-SIGALRM regression scaled the actual financial phase constant to 1 second and its selector/receipt reserve to 3 seconds, making the common CLI envelope 4 seconds. An inert financial dispatch slept 1.5 seconds. It completed after 1.500279 seconds, with no timeout receipt: the desired hard 1-second phase regression fails. A separate 5-second inert dispatch was interrupted by the actual envelope alarm at 4.004722 seconds, proving the alarm implementation was live. Result: one desired failure, one passing alarm control.

Commands, XML, source pins and exact observations are adjacent. Project code ran in owned capped network-off Docker; no database, provider, production or worker action occurred during this reproduction. No product edits.

A narrow repair is sequential phase-specific hard alarms, each capped by one common absolute envelope deadline. Preserve the original whole-run deadline/cleanup reserve, the confirmed financial outcome if a later report phase times out, and the distinction between unstarted zero work and started unknown work. Do not nest SIGALRM contexts or give each phase a fresh complete envelope. Final patched review is pending.
