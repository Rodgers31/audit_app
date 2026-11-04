# Authenticated storage metadata refresh

Observed **4 November 2026 03:56–04:10:30Z / 3 November 21:56–22:10:30 CST** after
the user restored the existing Cloudflare session. This supersedes only the
earlier signed-out access conclusion. **Live Stage A remains HELD.** These are
sanitized visible-UI observations, not a portable authenticated provider export,
object-content verification, credential-copy attestation or approval.

| Observation | Current visible result | Practical boundary |
| --- | --- | --- |
| Social bucket, 03:58:53Z | Private, Standard; no custom domains; public development URL disabled. Two historical 77 B diagnostic PNGs; 304 B displayed bucket usage. | Displayed aggregate differs from the sum of object lengths. No content was downloaded or changed; these are not app originals or backups. |
| Lifecycle and services, 03:58:53Z | Only Default Multipart Abort Rule, seven days; no completed-original expiry or bucket lock. Catalog, access logs, local uploads and on-demand migration disabled. Event notifications offer a paid-plan prerequisite. | No paid service provisioned. Multipart abort is not completed-object retention or backup. |
| CORS, 03:59:07Z | Exact origin `https://www.auditgava.com`; GET/HEAD/PUT; content-type/if-none-match; exposed ETag; max-age300 seconds. | Editor was opened for reading and cancelled without saving. CORS is not a credential restriction or exclusive-writer proof. |
| Account usage, 03:59:36Z | Cycle label October8–November8; Class A2.59k, Class B5.6k; 426.12 MB total storage; $0.00 and no billable usage incurred yet. Source bucket829 objects/376.09 MB; existing source recovery bucket5 objects/53.56 MB. | Account-wide UI totals, with source activity included. Source buckets sum429.65 MB versus426.12 MB aggregate:3.53 MB unreconciled metric/window difference, not exact headroom. No future-cost, contents or media-custody guarantee inferred. |
| Existing social token, 04:01:15Z | Account API token, Object Read & Write limited to the social bucket. Start2026-10-15; end2026-11-14; include/exclude IP filters empty. | This R2 view exposes date only; the later general account-token JSON preview below adds exact seconds/timezone. No exact midnight/grace assumption. Original deployed-identifier evidence remains dated. No token value, replacement, update, roll or deletion. |
| Other R2 authority, 04:01:15Z | Three other Account API tokens: all-bucket Admin Read Only×1 and source-bucket Object Read & Write×2. | Source-bucket restrictions do not grant social-object writes. Token listings do not reveal all secret copies or attest holder restrictions. |
| Members, 04:03:35Z | One active member, one Super Administrator – All Privileges policy covering the entire account; no additional rows/pager visible. | A privileged administrator can change authority. Identity is kept private; this is not an accepted renewal/custody appointment. |
| Workers/Pages, 04:04:04Z | Show all, empty search, no projects found. Zero projects and therefore no project R2 bindings in this account. | Does not prove no clients, copies or projects outside this account. No worker started. |
| Profile, 04:04–04:10:30Z receipt bound | No user API tokens; one current Chrome/macOS session; no connected Cloudflare OAuth applications. Global API Key View/Change controls exist. | Global key was not opened; existence/use/copies unknown. No session ended, OAuth exchange or application revoked. |

Repository metadata at approximately04:07Z found16 repository secrets and zero
environment secrets in each of three listed environments. Storage candidate
secret names belong to the receipt/source path; its configured bucket is the
source bucket. Values were unreadable and were not requested. This narrows the
visible configuration inventory; it cannot prove the hidden values, Render
environment/group holders, operator stores, stopped clients or off-system copies.

The [R2 S3 compatibility reference](https://developers.cloudflare.com/r2/api/s3/api/)
lists Get/PutBucketVersioning and Get/PutBucketReplication as unimplemented.
This is a provider API capability statement, not proof that external backup or
replication is absent. The [current pricing reference](https://developers.cloudflare.com/r2/pricing/)
describes Standard's monthly free allowance as10 GB-month,1 million Class A and
10 million Class B operations; GB-month uses daily peak averaging. A point-in-time
426.12 MB display is not an exact remaining monthly allowance. Infrequent Access
has no free allowance; no class change or spending authorization is implied.

## Subsequent exact expiry discovery, 04:17–04:18:40Z

After explicit user authorization to retrieve the expiry, the general **Manage
account → Account API tokens → existing social token** detail showed the selected
expiration `Oct 15, 16:05 – Nov 14, 15:05 CST`. Its expanded picker showed
`End: 2026-11-14 15:05`, timezone **Central Standard Time (CST)**, and placeholder
`yyyy-MM-dd HH:mm`. This initially filled only minute precision.

Without editing any field, the **Review token → JSON Payload** preview then
exposed the existing configuration at **04:18:31.412Z**:

```json
{
  "not_before": "2026-10-15T21:05:55Z",
  "expires_on": "2026-11-14T21:05:55Z"
}
```

The exact expiry is **14 November2026 21:05:55 UTC /15:05:55 CST (UTC−06:00)**.
This supersedes both earlier precision limitations. No Apply or Update token was
used; the review page was left at04:18:40Z without submitting changes. No API
credential was revealed, created or renewed. No owner API command is needed.

No Cloudflare connector, existing local Cloudflare API credential variable or
known Wrangler config was found in the bounded discovery; GitHub secret values
are unavailable. The provider UI JSON preview supplied the field directly.
It is not a direct API GET response or independently authenticated portable
provider export. The proposed10 November18:00Z renewal target is strictly earlier
than this expiry but still needs named acceptance; no grace period is inferred.

Append-only expiry-detail-v1.json preserves the minute-only observation. The final
expiry-detail-v2.json is SHA256
`7407bd3ad67b4d33bd35c3616ed8360c69f6cf1c9cfe27899e8dc9d1b5cb106c`.
Both producer-bound transcriptions preserve their actual source and scope.

Still required before intake: named
accepted renewal and secure recovery owners and a strictly earlier deadline;
complete secure-holder/copy restrictions; accepted retention/holds, appointments,
exact destination/key recovery/dependency custody and inclusive caps; qualified
real custody filesystem and browser/production resource acceptance. The accepted
seven-day private-local **database-export-only** rule remains unchanged. The
observed overdue B42 archive still needs owner reconciliation; no cleanup ran.

Private provenance is the append-only authenticated-storage-observations-v1.json
record, SHA256 `523ced9ea5c470d18eecbc193723cd6e2173a172d5e4dac91c141ff3ddfa9382`,
generated04:10:30Z from the stated UI observations. Its producer hash binds the
transcription bytes, not provider authentication. Earlier access and E05–E10
receipts remain historical. No upload, signing test, export, restore, credential
change, policy change or provider mutation was performed by this lane.
