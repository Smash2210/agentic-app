"""Policy passages for retrieval (spec 003 FR-301): one per numbered section of every policy file."""

import re
from dataclasses import dataclass
from pathlib import Path

_TITLE = re.compile(r"^# (.+)$", re.MULTILINE)
_DOC_ID = re.compile(r"^doc_id:\s*(\S+)\s*$", re.MULTILINE)
_SECTION = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    id: str  # "<doc_id>#<section>", e.g. POL-MEALS#2
    doc_id: str
    section: str
    doc_title: str
    title: str
    body: str

    @property
    def text(self) -> str:
        """What is searched and embedded: where the passage sits, then what it says."""
        return f"{self.doc_title} — {self.title}: {self.body}"


def load_chunks(policy_dir: Path) -> list[Chunk]:
    chunks = []
    for path in sorted(Path(policy_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title, doc_id = _TITLE.search(text), _DOC_ID.search(text)
        if title is None or doc_id is None:
            raise ValueError(f"{path.name}: needs a '# Title' line and a 'doc_id:' line")
        starts = list(_SECTION.finditer(text))
        for i, match in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
            chunks.append(Chunk(
                id=f"{doc_id.group(1)}#{match.group(1)}",
                doc_id=doc_id.group(1),
                section=match.group(1),
                doc_title=title.group(1).strip(),
                title=match.group(2).strip(),
                body=" ".join(text[match.end():end].split()),
            ))
    return chunks
