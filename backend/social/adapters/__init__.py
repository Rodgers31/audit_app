"""Opt-in native adapters. Importing this package registers no provider."""

from .config import MetaAdapterConfig
from .facebook import FacebookPageAdapter
from .instagram import InstagramFacebookLoginAdapter
from .threads import ThreadsAdapter, ThreadsAdapterConfig
from .x import XAdapter, XAdapterConfig
from .tiktok import TikTokAccountsAdapter, TikTokAdapterConfig

__all__ = ("MetaAdapterConfig", "FacebookPageAdapter", "InstagramFacebookLoginAdapter")
