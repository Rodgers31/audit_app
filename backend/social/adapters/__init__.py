"""Opt-in native adapters. Importing this package registers no provider."""

from .config import MetaAdapterConfig
from .facebook import FacebookPageAdapter
from .instagram import InstagramFacebookLoginAdapter

__all__ = ("MetaAdapterConfig", "FacebookPageAdapter", "InstagramFacebookLoginAdapter")
