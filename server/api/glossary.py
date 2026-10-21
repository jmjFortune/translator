"""Glossary endpoints backed by the existing GlossaryManager."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..models import GlossaryOut, GlossaryPatch, GlossaryTermIn

router = APIRouter(prefix="/glossary", tags=["glossary"])


def _manager():
    from ui.glossary_manager import GlossaryManager

    return GlossaryManager


def _payload() -> GlossaryOut:
    manager = _manager()
    return GlossaryOut(terms=manager.load(), presets=manager.get_preset_names())


@router.get("", response_model=GlossaryOut)
async def get_glossary() -> GlossaryOut:
    return _payload()


@router.put("", response_model=GlossaryOut)
async def replace_glossary(patch: GlossaryPatch) -> GlossaryOut:
    _manager().save(dict(patch.terms))
    return _payload()


@router.post("/terms", response_model=GlossaryOut)
async def add_term(term: GlossaryTermIn) -> GlossaryOut:
    _manager().add_term(term.term.strip(), term.zh.strip())
    return _payload()


@router.delete("/terms", response_model=GlossaryOut)
async def delete_term(term: str = Query(..., description="要删除的原文术语")) -> GlossaryOut:
    _manager().remove_term(term)
    return _payload()
