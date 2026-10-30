"""Inert format catalogue for composition while delivery adapters stay off.

These are implemented formats, not a permission/capability or readiness grant.
Only the ordinary registered validation and dispatch gates admit publication.
"""


def draft_formats(platform, product):
    if (platform, product) == ('facebook', 'facebook_pages'):
        from .adapters.meta_validation import FacebookPageValidation
        return FacebookPageValidation.formats
    if (platform, product) == ('instagram', 'instagram_graph_facebook_login'):
        from .adapters.meta_validation import InstagramFacebookLoginValidation
        return InstagramFacebookLoginValidation.formats
    if (platform, product) == ('threads', 'threads'):
        from .adapters.threads import ThreadsAdapter
        return ThreadsAdapter.formats
    if (platform, product) == ('x', 'x_api_v2'):
        from .adapters.x import XAdapter
        return XAdapter.formats
    if (platform, product) == ('tiktok', 'tiktok_accounts_api'):
        from .adapters.tiktok import TikTokAccountsAdapter
        return TikTokAccountsAdapter.formats
    return ()
