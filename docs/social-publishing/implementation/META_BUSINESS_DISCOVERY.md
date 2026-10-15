# Business-owned Page discovery

The 15 October 2026 owned-account Chrome comparison reproduced `/me/accounts`
returning zero Pages with the original five permissions, despite independently
validating the exact Page token and linked professional Instagram identity.
After separate owner approval, the same app/user with `business_management`
returned the approved AuditGava Page with `CREATE_CONTENT` and `MANAGE` tasks.
Explicit selection connected that Page and its linked Instagram account;
publishing remained disabled and no publishing adapter was installed.

`META_BUSINESS_DISCOVERY_ENABLED=true` opts the connection flow into this
additional permission. Missing/other environment values keep the original
five-permission flow. Configure it only after approval for the intended business;
the permission grants broad Business Manager read/write access even though the
connection code only uses read-only discovery. The consent must exclude future
businesses, Pages and Instagram accounts and select the intended owned assets.

The resolved configuration supplies the same requested scopes to service
status, both OAuth URL builders and token inspection. In business mode, absence
from either token inspection or actual granted permissions refuses discovery
with `PERMISSIONS_REQUIRED`. This does not make business access a publishing
capability: existing Page/Instagram scopes, provider content tasks, derived-token
identity, subject and asset-specific checks still control eligibility. No
fallback trusts a directly entered Page ID or fabricates tasks.

The regression exercises real start, provider exchange/discovery and explicit
selection against a fake business-owned Page: without the repair, normal start
asks for only five permissions and the Page disappears. The original source
produced three specific failures and four passing default controls. The repair
passes those controls plus denied-grant, actual-permission, malformed direct
configuration and missing-content-task controls. All provider calls are fake;
local tests do not themselves certify a live grant.

Callers covered: `ConnectionService.start` for initial/reconnect flows,
`MetaProvider.authorize_url` for direct callers, `ConnectionService.status` for
UI disclosure, and `MetaProvider.inspect_token`/`discover` for both ordinary and
ownership-recording discovery. Account selection and capability refresh retain
their existing publishing requirements. Privacy callbacks, maintenance, media
and worker startup do not create OAuth requests and are unchanged.

Deployment: ship code with the setting absent/off first; explicitly enable it
only for the approved existing app/service. Inspect the resolved six scopes and
fresh owned-account discovery, and verify publishing remains disabled. Rollback
the setting to false to stop requesting business access, or redeploy backend
`d6db95eb4cf9005c6fb0e01c5c50aed2c20b65d4`. Neither step revokes an already
granted Meta permission; use the provider's reviewed consent/revocation flow for
that. Keep privacy handlers and key custody active while grants exist. Abort on
unexpected assets, subject mismatch, missing tasks or unintended publishing.

Meta's [permissions reference](https://developers.facebook.com/documentation/development/permissions)
describes Business Manager read/write authority and its possible use as a
dependency of `pages_show_list`. The [User/accounts reference](https://developers.facebook.com/docs/graph-api/reference/user/accounts/)
defines tasks as an edge-added field. These documents explain the contracts;
the owned-account comparison establishes this application's observed need.

This repair does not complete worker/media acceptance, privacy retention or
deletion execution, upstream logging acceptance, cost-headroom measurements or
the public-route paint/layout performance checklist. No new paid resource,
scheduler, Actions execution or public post is introduced.
