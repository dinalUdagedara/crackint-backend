"""
Incremental extraction of one string field from a JSON object that arrives in chunks.

Agents ask the model for JSON (e.g. {"feedback": "...", "score": 80}). When streaming, we want
to show the "feedback" text as it is generated, before the object is complete. Feed raw
chunks to JsonStringFieldExtractor and it returns the newly decoded text of that field.
"""

import json
import re
from typing import Optional

_SIMPLE_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


class JsonStringFieldExtractor:
    """Decode the value of a top-level string field from streamed JSON text."""

    def __init__(self, field: str) -> None:
        self._start_re = re.compile(r'"' + re.escape(field) + r'"\s*:\s*"')
        self._buf = ""
        self._pos: Optional[int] = None  # index in _buf of the next undecoded value char
        self.done = False

    def feed(self, chunk: str) -> str:
        """Add a chunk; return the field text decoded from it (may be empty)."""
        if self.done or not chunk:
            return ""
        self._buf += chunk
        if self._pos is None:
            m = self._start_re.search(self._buf)
            if m is None:
                return ""
            self._pos = m.end()

        out = []
        buf, i = self._buf, self._pos
        while i < len(buf):
            ch = buf[i]
            if ch == '"':
                self.done = True
                i += 1
                break
            if ch != "\\":
                out.append(ch)
                i += 1
                continue
            # Escape sequence: wait for the rest of it if the chunk ended mid-escape.
            if i + 1 >= len(buf):
                break
            esc = buf[i + 1]
            if esc == "u":
                if i + 6 > len(buf):
                    break
                decoded = _decode_unicode_escape(buf, i)
                if decoded is None:
                    break  # high surrogate waiting for its low half
                text, consumed = decoded
                out.append(text)
                i += consumed
                continue
            out.append(_SIMPLE_ESCAPES.get(esc, esc))
            i += 2
        self._pos = i
        return "".join(out)


def _decode_unicode_escape(buf: str, i: int) -> Optional[tuple[str, int]]:
    """Decode \\uXXXX at buf[i], combining surrogate pairs. None if more input is needed."""
    code = int(buf[i + 2 : i + 6], 16)
    if 0xD800 <= code <= 0xDBFF:  # high surrogate: needs the following \\uXXXX
        if i + 12 > len(buf):
            return None
        pair = buf[i : i + 12]
        try:
            return json.loads('"' + pair + '"'), 12
        except json.JSONDecodeError:
            return chr(code), 6
    return chr(code), 6
