"""The user-approved Chinese/Latin font profile for standalone builds only."""

from pathlib import Path

PROFILE_NAME = "simplified-chinese-latin-fallback"
FONT_NAMES = frozenset({
    "LXGWWenKaiGB-Regular.1.520.ttf",
    "SourceHanSansCN-Regular.ttf", "SourceHanSansCN-Bold.ttf",
    "SourceHanSerifCN-Regular.ttf", "SourceHanSerifCN-Bold.ttf",
    "NotoSans-Regular.ttf", "NotoSans-Bold.ttf",
    "NotoSans-Italic.ttf", "NotoSans-BoldItalic.ttf",
    "NotoSerif-Regular.ttf", "NotoSerif-Bold.ttf",
    "NotoSerif-Italic.ttf", "NotoSerif-BoldItalic.ttf",
    "GoNotoKurrent-Regular.ttf", "GoNotoKurrent-Bold.ttf",
})


def restrict_metadata_file(path: Path) -> dict:
    """Patch the bundled copy, including spawn children and asset warmup.

    BabelDOC 0.6.2 adds every regional family to every other family's fallback
    list at import time. Filtering only the asset archive would redownload the
    removed fonts. Filter those lists and their download metadata together.
    """
    source = path.read_text()
    marker = "# translator simplified font profile (D-028)"
    if marker in source or "def __cleanup_unused_font_metadata():" not in source:
        raise ValueError("Unexpected BabelDOC font metadata; review the font profile patch")
    patch = (
        f"\n\n{marker}\n"
        f"_translator_font_names = frozenset({tuple(sorted(FONT_NAMES))!r})\n"
        "if not _translator_font_names <= EMBEDDING_FONT_METADATA.keys():\n"
        "    raise RuntimeError('BabelDOC is missing a required translator font')\n"
        "for _translator_family in ALL_FONT_FAMILY.values():\n"
        "    for _translator_kind, _translator_fonts in _translator_family.items():\n"
        "        _translator_family[_translator_kind] = [\n"
        "            name for name in _translator_fonts if name in _translator_font_names]\n"
        "__cleanup_unused_font_metadata()\n"
    )
    path.write_text(source + patch)
    return {"name": PROFILE_NAME, "fonts": sorted(FONT_NAMES),
            "upstream": "BabelDOC 0.6.2; regional fallback lists and download metadata filtered"}
