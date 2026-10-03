# Social accounts and brand configuration

Account changes and verification were performed earlier in this conversation on **2026-10-03**. This document preserves those observations; this documentation/egress task did not modify or reconnect accounts. Public profile setup is separate from future OAuth developer-app authorization.

## Final recorded account state

| Platform | Public profile | Display / handle | Type/category | Branding / website | Remaining limitation |
|---|---|---|---|---|---|
| Facebook | [AuditGava](https://www.facebook.com/AuditGava) | AuditGava / @AuditGava | Organization Page; Education website | Existing logo, generated cover, bio, website and Learn more CTA verified | Developer API grants/app review not done |
| Instagram | [AuditGava](https://www.instagram.com/auditgava/) | AuditGava / @auditgava | Public Business; Education website | Existing logo and bio verified | Dedicated website field requires mobile editing; URL in bio is a stopgap, not proof of a clickable website field |
| Threads | [AuditGava](https://www.threads.com/@auditgava) | AuditGava / @auditgava | Public profile linked to Instagram | Logo, bio and website verified | Future separate Threads API authorization required |
| TikTok | [AuditGava](https://www.tiktok.com/@auditgava) | AuditGava / @auditgava | Public profile; exact business/category state not established in desktop UI | Logo and bio verified | Mobile category/business/website eligibility checks remain; no claim of API eligibility |
| X | [AuditGava](https://x.com/AuditGava) | AuditGava / @AuditGava | Standard public account | Logo, header, bio and website verified | Optional professional category not configured; paid API access is separate |

Primary website: **https://auditgava.com**. No unverified phone, postal address, personal contact information or legal nonprofit designation was invented.

### Facebook personal profile versus Page

The original managing login was a personal profile named “Audit Gava.” A new public organization Page was created and branded. The personal login remains the manager; it was not converted, deleted or made into an API publishing destination. The user completed Facebook's password confirmation directly to save the available `@AuditGava` username. The agent did not receive or enter that password.

The public Page and Business Suite UI can show different identifiers. Future connection code must discover and store the authorized API Page ID through OAuth, rather than treating a URL/Business Suite asset identifier as interchangeable. The correct destination is the organization Page.

### Why these categories and assets

AuditGava is a product that explains public financial data. **Education website** accurately describes the current public service and gives Instagram professional-account capabilities without claiming legal nonprofit status, government ownership, political affiliation or a newsroom operation.

The organization's existing logo is the appropriate profile image. The website's forest/dark green, cream and restrained gold were retained. Header copy emphasizes public-finance explanation, not campaigning. No new identity or political/government-style seal was designed.

## Saved platform-specific copy

### Facebook bio

> Understand where Kenya’s public money goes. Explore government spending, debt and audit findings, with clear explanations and links to the source data.

The following longer About text was prepared, but was **not separately verified as saved**:

> AuditGava helps people understand Kenya’s public finances. Explore national and county spending, public debt, audit findings and financial data, with clear explanations and links to original sources. Follow for data updates, useful comparisons and public-finance explainers. Explore the full data at https://auditgava.com.

### Instagram bio

```text
Kenya’s public money, made clear.
Spending • debt • audits
Data updates & explainers for everyone.
Explore: auditgava.com
```

### Threads bio

> Kenya’s public money, explained. Follow spending, debt and audit updates with sources and context. Explore the data at auditgava.com.

### TikTok bio

> Kenya’s spending, debt & audits, made clear. Explore the data: auditgava.com

### X bio

> Follow Kenya’s public spending, debt and audit findings. Clear explainers, data updates and source links to help you understand where public money goes.

## Assets

- Profile picture on all five accounts: [original website logo](../../frontend/public/logo-original.png), 1024 × 1024, used without redesign.
- [Facebook cover](assets/auditgava-facebook-cover.png), 2032 × 774.
- [X header](assets/auditgava-x-header.png), 2172 × 724.
- Website reference graphic: [existing OG image](../../frontend/public/og-image.png).
- [Asset generation/provenance notes](assets/README.md).

Header text: “AuditGava”; “Kenya’s public money, explained.”; “Spending · Debt · Audits”; “auditgava.com”. Facebook and X crop previews were checked during the original upload. Instagram, Threads and TikTok do not use these cover assets.

## Meta relationships and cross-posting

Facebook Page Linked Accounts showed Instagram `@auditgava` connected. Meta Business Suite's composer offered both Facebook and Instagram as destinations, with customization available. This enables deliberate cross-posting; aggressive automatic posting was not enabled and no substantive test post was published.

Instagram and Threads are linked, but the Instagram profile-picture update did not propagate in the observed session. Threads received an explicit logo upload. Threads bio/link remain independently maintained; do not assume future synchronization. Their developer credentials also remain separate.

Shared Inbox access to Instagram messages was left off. WhatsApp connection and friend invitations were skipped. No account ownership, recovery email, phone, 2FA or billing changes were made. Profile-photo/cover changes generated the platforms' normal profile-update activity, not editorial social posts.

## Remaining setup and related website work

1. Complete Instagram's dedicated website field in its mobile UI and verify the public clickable link.
2. Check TikTok mobile account/category settings and link eligibility. Do not equate business-profile selection with developer-app approval.
3. Review app/account scopes through the future authorized OAuth project; none are established by browser login alone.
4. Recheck public links when deploying the website footer. The earlier [PR #471](https://github.com/Rodgers31/audit_app/pull/471) added all five platform links/logos; its merge/deployment state was not re-audited in this task.

The browser file-upload restriction was resolved when the user enabled the extension's file-URL permission; logo and header uploads subsequently succeeded. It is not an outstanding blocker.
