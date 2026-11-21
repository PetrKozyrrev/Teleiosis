"""Bounded subprocess for structural validation of untrusted, static PDFs."""
import io
import resource
import sys

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

BLOCKED_NAMES = {
    "/A", "/AA", "/AcroForm", "/Action", "/AF", "/Annots", "/EF", "/EmbeddedFile", "/EmbeddedFiles",
    "/F", "/FDecodeParms", "/FFilter", "/FileAttachment", "/Filespec", "/GoToE", "/GoToR",
    "/ImportData", "/JavaScript", "/JS", "/Launch",
    "/Movie", "/OpenAction", "/RichMedia", "/Rendition", "/Sound", "/SubmitForm",
    "/URI", "/XFA", "/3D",
}


def is_static_pdf(data: bytes) -> bool:
    reader = PdfReader(io.BytesIO(data), strict=True, xref_stream_maximum_entries=30_000)
    if reader.is_encrypted or "/Prev" in reader.trailer:
        return False
    stack = [reader.trailer.raw_get("/Root")]
    visited = set()
    elements = pages = 0
    while stack:
        elements += 1
        if elements > 100_000:
            return False
        item = stack.pop()
        if isinstance(item, IndirectObject):
            key = (item.idnum, item.generation)
            if key not in visited:
                visited.add(key)
                stack.append(item.get_object())
        elif isinstance(item, DictionaryObject):
            if BLOCKED_NAMES.intersection(item.keys()):
                return False
            if item.get("/Type") == "/Page":
                pages += 1
                if pages > 1000:
                    return False
            if len(stack) + len(item) > 100_000:
                return False
            stack.extend(item.values())
        elif isinstance(item, ArrayObject):
            if len(stack) + len(item) > 100_000:
                return False
            stack.extend(item)
        elif isinstance(item, NameObject) and item in BLOCKED_NAMES:
            return False
    return pages > 0 and len(reader.pages) == pages


def main() -> int:
    resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        return 0 if is_static_pdf(sys.stdin.buffer.read(10 * 1024**2 + 1)) else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
