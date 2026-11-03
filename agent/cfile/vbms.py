"""The simulated VBMS (L22, L24, L26): a case's synthetic C-file as typed documents whose pages
carry one global page number.

`pull` builds the persona's synthetic C-file (agent/cfile/synth.py) and, once the firm's own
21-22a is filed, that form too: VA files it into the C-file, which is why the C-file is pulled
only after it. Each PDF page's text layer is read, SSNs are stripped right there (so no tool can
return one), and each document is typed in code (`triage`). The documents are concatenated in
order with page offsets, so every page has one number across the whole C-file and a citation is
just `p. N`. Read-only: nothing here changes a C-file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

from pypdf import PdfReader

from agent.cfile.extract import DocType, _iso, strip_ssns, triage
from agent.cfile.facts import PriorRep, truth_facts
from agent.cfile.synth import build_documents
from agent.personas import get_persona

_US_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")


@dataclass(frozen=True)
class Document:
    doc_id: str
    type: DocType
    subject: str
    date: str | None  # YYYY-MM-DD, from the eFolder listing (the subject), when it has one
    first_page: int
    pages: tuple[str, ...]  # text per page, SSNs already stripped

    @property
    def page_numbers(self) -> range:
        return range(self.first_page, self.first_page + len(self.pages))

    def page(self, n: int) -> str:
        return self.pages[n - self.first_page]

    def summary(self) -> dict:
        last = self.first_page + len(self.pages) - 1
        span = f"p. {self.first_page}" if last == self.first_page else f"pp. {self.first_page}-{last}"
        return {"doc_id": self.doc_id, "type": self.type, "subject": self.subject, "date": self.date, "pages": span}


@dataclass(frozen=True)
class CFile:
    docs: tuple[Document, ...]

    @property
    def page_count(self) -> int:
        return sum(len(d.pages) for d in self.docs)

    def doc(self, doc_id: str) -> Document:
        for d in self.docs:
            if d.doc_id == doc_id:
                return d
        raise KeyError(f"no document {doc_id!r}; ids: {', '.join(d.doc_id for d in self.docs)}")

    def owner(self, page: int) -> Document:
        for d in self.docs:
            if page in d.page_numbers:
                return d
        raise KeyError(f"no page {page}; the C-file has pages 1-{self.page_count}")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Keyword search over pages: pages with the most query words first, a snippet each."""
        words = [w for w in re.findall(r"[a-z0-9%-]+", query.lower()) if len(w) > 1]
        hits = []
        for d in self.docs:
            for n in d.page_numbers:
                low = d.page(n).lower()
                found = [w for w in words if w in low]
                if found:
                    at = low.index(found[0])
                    snippet = " ".join(d.page(n)[max(0, at - 80) : at + 160].split())
                    hits.append((len(found), {"doc_id": d.doc_id, "type": d.type, "page": n, "snippet": snippet}))
        hits.sort(key=lambda h: -h[0])
        return [h for _, h in hits[:limit]]


def _pages(pdf: bytes) -> tuple[str, ...]:
    return tuple(strip_ssns(p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages)


@lru_cache(maxsize=32)
def pull(persona_id: str, firm_rep: tuple[str, str] | None = None) -> CFile:
    """The persona's C-file. `firm_rep`: (name, date signed) of the firm's own filed 21-22a."""
    persona = get_persona(persona_id)
    facts = truth_facts(persona)
    if firm_rep:
        name, signed = firm_rep
        facts.prior_reps.append(PriorRep(name=name, kind="attorney", signed=signed))
    docs, page = [], 1
    for n, (_, subject, pdf) in enumerate(build_documents(persona, facts), 1):
        pages = _pages(pdf)
        dated = _US_DATE.search(subject)
        docs.append(Document(f"D{n}", triage(pages[0]), subject, _iso(dated.group()) if dated else None, page, pages))
        page += len(pages)
    return CFile(tuple(docs))
