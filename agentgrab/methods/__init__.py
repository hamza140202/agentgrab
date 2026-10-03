"""Method registry. Add a method: import it, append the instance to ALL_METHODS."""
from __future__ import annotations

from ..models import DownloadRequest
from ..truth import TruthStore
from .base import DownloadMethod
from .ig_cobalt import IgCobaltMethod
from .ig_graphql import IgGraphqlMethod
from .ig_instaloader import IgInstaloaderMethod
from .loaderto import LoadertoMethod
from .ytdlp_instagram import YtdlpInstagramMethod
from .ytdlp_pot import YtdlpPotMethod

# initial policy order per platform (the truth agent re-ranks dynamically)
CHAIN_POLICY: dict[str, list] = {
    "youtube": [
        YtdlpPotMethod(),   # tier 1: fast, best quality, flaky on flagged IPs
        LoadertoMethod(),   # tier 2: verified workhorse (clean-IP resolver farm)
        YtdlpPotMethod(),   # tier 3: retry — flag windows open non-deterministically
    ],
    "instagram": [
        IgGraphqlMethod(),      # tier 1: fastest when it works (direct CDN urls)
        IgInstaloaderMethod(),  # tier 2: verified anonymous workhorse
        IgCobaltMethod(),       # tier 3: independent family; verifier rejects .jpg degrade
        YtdlpInstagramMethod(), # tier 4: works on clean IPs
    ],
}

ALL_METHODS: list[DownloadMethod] = [
    YtdlpPotMethod(), LoadertoMethod(),
    IgGraphqlMethod(), IgInstaloaderMethod(), IgCobaltMethod(), YtdlpInstagramMethod(),
]


def chain_for(platform: str, req: DownloadRequest, truth: TruthStore) -> list[DownloadMethod]:
    """Build the execution chain for a request. Honors forced --method."""
    if req.method:
        forced = [m for m in ALL_METHODS if m.name == req.method]
        if not forced:
            raise KeyError(
                f"unknown method {req.method!r}; available: {sorted({m.name for m in ALL_METHODS})}"
            )
        return forced
    base = CHAIN_POLICY.get(platform)
    if not base:
        return []
    ranked = rank_chain(base, truth)
    return ranked


def rank_chain(base: list, truth: TruthStore) -> list:
    """Rank the policy chain by truth data, preserving the retry-round semantics."""
    ranked_names = truth.rank(list(dict.fromkeys(m.name for m in base)))
    ranked: list[DownloadMethod] = []
    seen = set()
    for name in ranked_names:
        first = next(m for m in base if m.name == name)
        ranked.append(first)
        seen.add(name)
    # keep the YouTube retry round (ytdlp_pot twice) when it is still trusted
    if platform_is_youtube(seen) and "ytdlp_pot" in seen:
        yt_instances = [m for m in base if m.name == "ytdlp_pot"]
        if ranked and ranked[0].name == "ytdlp_pot" and len(yt_instances) > 1:
            ranked.append(yt_instances[1])
        elif not ranked or ranked[-1].name != "ytdlp_pot":
            ranked.append(yt_instances[0])
    return ranked


def platform_is_youtube(seen: set) -> bool:
    return "ytdlp_pot" in seen or "loaderto" in seen


def describe_methods() -> list[dict]:
    return [
        {"name": m.name, "platforms": list(m.platforms), "default_timeout": m.default_timeout}
        for m in ALL_METHODS
    ]
