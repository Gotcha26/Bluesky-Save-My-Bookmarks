#!/usr/bin/env python3
"""
Module déprécié : utiliser api.quote_resolver.QuoteResolver.

Un « repost » n'est jamais bookmarké ; ce que l'ancien code appelait ainsi est une
citation (quote post). Seul le nom RepostResolver est conservé, comme alias.
"""
import warnings

from api.quote_resolver import QuoteResolver as RepostResolver  # noqa: F401

warnings.warn(
    "api.repost_resolver est déprécié : importer QuoteResolver depuis api.quote_resolver",
    DeprecationWarning,
    stacklevel=2,
)
