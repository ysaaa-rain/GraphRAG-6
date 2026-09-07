"""Convert a small Enron maildir sample to the project's JSONL schema.

The script intentionally keeps raw mail data outside Git. It produces one
normalized document per message and preserves the source path for evidence
auditing. It does not call an LLM.
"""

from __future__ import annotations

import argparse
import json
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Iterable


def _header(message, name: str) -> str:
    value = message.get(name, "")
    return str(value).strip()


def _body(message) -> str:
    if message.is_multipart():
        parts: list[str] = []
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_type() != "text/plain":
                continue
            try:
                content = part.get_content()
            except (LookupError, UnicodeDecodeError):
                payload = part.get_payload(decode=True) or b""
                content = payload.decode("utf-8", errors="replace")
            if content:
                parts.append(str(content).strip())
        return "\n\n".join(part for part in parts if part)
    try:
        return str(message.get_content()).strip()
    except (LookupError, UnicodeDecodeError):
        payload = message.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace").strip()


def iter_mail_files(root: Path) -> Iterable[Path]:
    yield from sorted(path for path in root.rglob("*") if path.is_file())


def convert(input_dir: Path, output_path: Path) -> int:
    parser = BytesParser(policy=policy.default)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as output:
        for path in iter_mail_files(input_dir):
            with path.open("rb") as source:
                message = parser.parse(source)
            relative = path.relative_to(input_dir).as_posix()
            document_id = f"enron-s0:{relative}"
            body = _body(message)
            text = "\n".join(
                part
                for part in (
                    f"From: {_header(message, 'From')}",
                    f"To: {_header(message, 'To')}",
                    f"Cc: {_header(message, 'Cc')}",
                    f"Date: {_header(message, 'Date')}",
                    f"Subject: {_header(message, 'Subject')}",
                    "",
                    body,
                )
                if part
            )
            record = {
                "id": document_id,
                "title": _header(message, "Subject") or document_id,
                "text": text,
                "source_path": relative,
                "message_id": _header(message, "Message-ID"),
                "date": _header(message, "Date"),
                "from": _header(message, "From"),
                "to": _header(message, "To"),
                "cc": _header(message, "Cc"),
            }
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = convert(args.input_dir, args.output)
    print(f"converted={count} output={args.output}")


if __name__ == "__main__":
    main()
