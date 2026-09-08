"""Convert the extracted Enron maildir into a reproducible JSONL corpus.

This is a local, streaming preprocessing step.  It does not call an LLM and
does not assign thematic labels.  The original mailbox user/folder hierarchy
is retained so that a later experiment can declare its denominator explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator


DEFAULT_KEYWORDS = (
    "crisis",
    "california",
    "energy",
    "power",
    "british airways",
    "continental airlines",
)
WHITESPACE_RE = re.compile(r"[ \t]+")
SUBJECT_PREFIX_RE = re.compile(r"^(?:(?:re|fw|fwd)\s*:\s*)+", re.IGNORECASE)
MESSAGE_PARSER = BytesParser(policy=policy.default)


class _HTMLToText(HTMLParser):
    """Small dependency-free HTML-to-text converter for email bodies."""

    BLOCK_TAGS = {
        "br",
        "div",
        "li",
        "p",
        "section",
        "td",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def text(self) -> str:
        return "".join(self.parts)


def decode_text(value: bytes | str | None, charset: str | None = None) -> str:
    """Decode a possibly malformed MIME payload without aborting the corpus."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    candidates = [charset, "utf-8", "iso-8859-1"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return value.decode(candidate, errors="replace")
        except LookupError:
            continue
    return value.decode("utf-8", errors="replace")


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError, ValueError):
        return value


def normalize_whitespace(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in value.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(value: str) -> str:
    parser = _HTMLToText()
    try:
        parser.feed(value)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed HTML must not stop preprocessing
        return value
    return parser.text()


def part_text(part: Any) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        payload = raw_payload if isinstance(raw_payload, (bytes, str)) else ""
    return decode_text(payload, part.get_content_charset())


def extract_body(message: Any) -> tuple[str, int, int, bool]:
    """Return cleaned body, pre-cleaning chars, skipped attachments, multipart flag."""

    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachment_count = 0
    is_multipart = message.is_multipart()

    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type().lower()
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if disposition == "attachment" or filename:
            attachment_count += 1
            continue
        if content_type == "text/plain":
            plain_parts.append(part_text(part))
        elif content_type == "text/html":
            html_parts.append(part_text(part))

    raw_body = "\n\n".join(plain_parts or [html_to_text(item) for item in html_parts])
    cleaned_body = normalize_whitespace(raw_body)
    return cleaned_body, len(raw_body), attachment_count, is_multipart


def normalize_addresses(value: str | None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for display_name, address in getaddresses([value or ""]):
        clean_address = address.strip().lower()
        clean_name = normalize_whitespace(decode_header_value(display_name))
        if clean_address or clean_name:
            result.append({"name": clean_name, "email": clean_address})
    return result


def parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def normalized_subject(value: str) -> str:
    return SUBJECT_PREFIX_RE.sub("", normalize_whitespace(value)).lower()


def stable_id(source_path: str, message_id: str) -> str:
    if message_id:
        return message_id.strip().strip("<>")
    digest = hashlib.sha1(source_path.encode("utf-8")).hexdigest()  # noqa: S324
    return f"path:{digest}"


def thread_id(subject: str, message_id: str, source_path: str) -> str:
    key = normalized_subject(subject)
    if not key:
        key = message_id or source_path
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()  # noqa: S324
    return f"subject:{digest[:20]}"


def iter_mail_paths(input_root: Path) -> Iterator[Path]:
    for root, _directories, filenames in os.walk(input_root):
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            path = Path(root) / filename
            if path.is_file():
                yield path


def format_addresses(addresses: list[dict[str, str]]) -> str:
    return ", ".join(
        item["email"] or item["name"] for item in addresses if item["email"] or item["name"]
    )


def build_text(record: dict[str, Any]) -> str:
    lines = [
        f"Source path: {record['source_path']}",
        f"Folder: {record['folder']}",
        f"Date: {record['date_raw']}",
        f"From: {format_addresses(record['from'])}",
        f"To: {format_addresses(record['to'])}",
        f"Cc: {format_addresses(record['cc'])}",
        f"Subject: {record['subject']}",
        "",
        record["body"],
    ]
    return "\n".join(lines).strip()


def parse_message(raw: bytes, source_path: str, input_root: Path) -> dict[str, Any]:
    message = MESSAGE_PARSER.parsebytes(raw)
    relative = Path(source_path).relative_to(input_root)
    path_parts = relative.parts
    path_offset = 1 if path_parts and path_parts[0] == "maildir" else 0
    mailbox_user = path_parts[path_offset] if len(path_parts) > path_offset + 1 else ""
    folder = "/".join(path_parts[path_offset + 1 : -1]) if len(path_parts) > path_offset + 2 else ""
    subject = normalize_whitespace(decode_header_value(message.get("Subject")))
    raw_date = normalize_whitespace(decode_header_value(message.get("Date")))
    message_id = normalize_whitespace(decode_header_value(message.get("Message-ID")))
    body, body_chars_before, attachment_count, is_multipart = extract_body(message)
    record: dict[str, Any] = {
        "record_id": stable_id(relative.as_posix(), message_id),
        "source_path": relative.as_posix(),
        "mailbox_user": mailbox_user,
        "folder": folder,
        "filename": path_parts[-1] if path_parts else "",
        "message_id": message_id or None,
        "date_raw": raw_date or None,
        "date": parse_date(raw_date),
        "from": normalize_addresses(message.get("From")),
        "to": normalize_addresses(message.get("To")),
        "cc": normalize_addresses(message.get("Cc")),
        "subject": subject,
        "thread_id": thread_id(subject, message_id, relative.as_posix()),
        "body": body,
        "body_chars_before_cleaning": body_chars_before,
        "body_chars": len(body),
        "attachment_count": attachment_count,
        "is_multipart": is_multipart,
        "raw_bytes": len(raw),
    }
    record["text"] = build_text(record)
    return record


def folder_key(record: dict[str, Any]) -> str:
    return f"{record['mailbox_user']}/{record['folder']}".strip("/")


def update_folder_stats(
    stats: dict[str, dict[str, Any]], record: dict[str, Any], keyword_values: dict[str, int]
) -> None:
    key = folder_key(record)
    item = stats.setdefault(
        key,
        {
            "mailbox_user": record["mailbox_user"],
            "folder": record["folder"],
            "mail_count": 0,
            "raw_bytes": 0,
            "body_chars": 0,
            "keyword_mail_hits": Counter(),
            "keyword_occurrences": Counter(),
        },
    )
    item["mail_count"] += 1
    item["raw_bytes"] += record["raw_bytes"]
    item["body_chars"] += record["body_chars"]
    for keyword, occurrences in keyword_values.items():
        if occurrences:
            item["keyword_mail_hits"][keyword] += 1
            item["keyword_occurrences"][keyword] += occurrences


def json_ready_folder_stats(stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for key in sorted(stats):
        item = dict(stats[key])
        item["keyword_mail_hits"] = dict(item["keyword_mail_hits"])
        item["keyword_occurrences"] = dict(item["keyword_occurrences"])
        item["folder_key"] = key
        result.append(item)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("data/raw/enron/source/maildir"),
        help="Extracted Enron maildir root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/enron/full"),
        help="Directory for normalized JSONL and audit statistics.",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=list(DEFAULT_KEYWORDS),
        help="Case-insensitive keywords used only for folder-level audit counts.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process at most N files for a smoke test.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing generated outputs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_root = args.input_root.resolve()
    output_dir = args.output_dir.resolve()
    if not input_root.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_root}")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "messages.jsonl"
    stats_path = output_dir / "preprocessing_stats.json"
    folder_path = output_dir / "folder_stats.json"
    errors_path = output_dir / "parse_errors.jsonl"
    generated = (output_path, stats_path, folder_path, errors_path)
    if not args.overwrite and any(path.exists() for path in generated):
        raise SystemExit(f"Generated output already exists under {output_dir}; use --overwrite to replace it.")

    temporary_output = output_dir / "messages.jsonl.partial"
    temporary_errors = output_dir / "parse_errors.jsonl.partial"
    for path in (temporary_output, temporary_errors):
        if path.exists():
            path.unlink()

    keywords = [item.lower() for item in args.keywords]
    folder_stats: dict[str, dict[str, Any]] = {}
    keyword_totals = Counter()
    keyword_occurrences = Counter()
    message_ids = Counter()
    counters: Counter[str] = Counter()
    raw_bytes_total = 0
    body_chars_before_total = 0
    body_chars_after_total = 0
    text_chars_total = 0
    processed = 0
    print(f"Input: {input_root}", file=sys.stderr)

    try:
        with temporary_output.open("w", encoding="utf-8", newline="\n") as output, temporary_errors.open(
            "w", encoding="utf-8", newline="\n"
        ) as errors:
            for path in iter_mail_paths(input_root):
                if args.limit is not None and processed >= args.limit:
                    break
                counters["input_files_seen"] += 1
                relative = path.relative_to(input_root).as_posix()
                try:
                    raw = path.read_bytes()
                    record = parse_message(raw, str(path), input_root.parent)
                except Exception as exc:  # noqa: BLE001 - preserve the bad path for audit
                    counters["parse_failures"] += 1
                    errors.write(json.dumps({"source_path": f"maildir/{relative}", "error": repr(exc)}, ensure_ascii=False) + "\n")
                    continue

                processed += 1
                counters["processed_records"] += 1
                raw_bytes_total += record["raw_bytes"]
                body_chars_before_total += record["body_chars_before_cleaning"]
                body_chars_after_total += record["body_chars"]
                text_chars_total += len(record["text"])
                if not record["message_id"]:
                    counters["missing_message_id"] += 1
                else:
                    message_ids[record["message_id"]] += 1
                if not record["date"]:
                    counters["missing_or_unparseable_date"] += 1
                if not record["subject"]:
                    counters["missing_subject"] += 1
                if not record["body"]:
                    counters["empty_clean_body"] += 1
                if record["attachment_count"]:
                    counters["records_with_attachments"] += 1
                if record["is_multipart"]:
                    counters["multipart_records"] += 1

                searchable = " ".join(
                    [
                        record["subject"],
                        record["body"],
                        format_addresses(record["from"]),
                        format_addresses(record["to"]),
                        format_addresses(record["cc"]),
                    ]
                ).lower()
                keyword_values = {keyword: searchable.count(keyword) for keyword in keywords}
                for keyword, occurrences in keyword_values.items():
                    if occurrences:
                        keyword_totals[keyword] += 1
                        keyword_occurrences[keyword] += occurrences
                update_folder_stats(folder_stats, record, keyword_values)
                output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                if processed % 10_000 == 0:
                    print(f"processed={processed}", file=sys.stderr, flush=True)

        counters["duplicate_message_ids"] = sum(count - 1 for count in message_ids.values() if count > 1)
        for key in (
            "parse_failures",
            "missing_message_id",
            "missing_or_unparseable_date",
            "empty_clean_body",
            "records_with_attachments",
            "multipart_records",
        ):
            counters.setdefault(key, 0)
        output_bytes = temporary_output.stat().st_size
        parse_error_bytes = temporary_errors.stat().st_size
        temporary_output.replace(output_path)
        temporary_errors.replace(errors_path)

        status = "limited_smoke_test" if args.limit is not None else "full_maildir"
        stats = {
            "schema_version": "enron-normalized-v1",
            "status": status,
            "input_root": str(input_root),
            "input_source_path_prefix": "maildir/",
            "output_file": str(output_path),
            "keywords_for_folder_audit": keywords,
            "counts": dict(counters),
            "raw_bytes_total": raw_bytes_total,
            "body_chars_before_cleaning_total": body_chars_before_total,
            "body_chars_after_cleaning_total": body_chars_after_total,
            "body_chars_removed_by_cleaning": body_chars_before_total - body_chars_after_total,
            "text_chars_total": text_chars_total,
            "output_jsonl_bytes": output_bytes,
            "parse_error_jsonl_bytes": parse_error_bytes,
            "cleaning_rules": [
                "decode MIME text parts with charset fallback",
                "prefer text/plain and fall back to HTML converted to text",
                "remove NUL bytes",
                "normalize line endings and horizontal whitespace",
                "collapse runs of more than two blank lines",
                "skip attachment payloads but retain attachment_count",
                "preserve quoted body lines; no thematic relabeling or folder reassignment",
            ],
        }
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        folder_path.write_text(
            json.dumps(
                {
                    "keywords": keywords,
                    "folder_count": len(folder_stats),
                    "folders": json_ready_folder_stats(folder_stats),
                    "keyword_totals": {
                        "mail_count": dict(keyword_totals),
                        "occurrences": dict(keyword_occurrences),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"completed records={processed} parse_failures={counters['parse_failures']} output={output_path}",
            file=sys.stderr,
        )
    except Exception:
        for path in (temporary_output, temporary_errors):
            if path.exists():
                path.unlink()
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
