"""C-file -> face note: a Benefits Documents stub with synthetic C-files, extraction, and the template."""

from agent.cfile.extract import OfflineExtractor, extract_cfile, make_dspy_extractor
from agent.cfile.facenote import FaceNote, render
from agent.cfile.facts import CfileFacts, truth_facts
from agent.cfile.synth import DocumentsStub, build_documents

__all__ = [
    "CfileFacts",
    "DocumentsStub",
    "FaceNote",
    "OfflineExtractor",
    "build_documents",
    "extract_cfile",
    "make_dspy_extractor",
    "render",
    "truth_facts",
]
