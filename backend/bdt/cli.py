"""Operator entry point: ingestion and review-user provisioning stay off public HTTP."""
import argparse
import getpass
import json
import os
from pathlib import Path
from .api import password_hash
from .documents import candidates, inspect_pdf, ocr_page
from .ingest import csv_records, file_source, import_finance, import_ibge, import_places, json_records, safe_download, transferegov_rows
from .storage import Database, User


def main():
    parser = argparse.ArgumentParser(prog="bdt")
    parser.add_argument("--database", default=os.getenv("BDT_DATABASE_URL", "sqlite:///data/bdt.db"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    user = sub.add_parser("create-user")
    user.add_argument("username")
    user.add_argument("--role", choices=["contributor", "reviewer"], default="contributor")
    download = sub.add_parser("download")
    download.add_argument("url")
    download.add_argument("path", type=Path)
    download.add_argument("--max-bytes", type=int, default=256*1024*1024)
    for command in ("import-ibge", "import-cnes", "import-inep", "import-places", "import-finance", "import-transferegov"):
        item = sub.add_parser(command)
        item.add_argument("path", type=Path)
        item.add_argument("--url", required=True)
        item.add_argument("--reference-date", required=True)
        item.add_argument("--member")
        item.add_argument("--encoding", default="utf-8-sig")
        item.add_argument("--root")
        if command == "import-transferegov":
            item.add_argument("--profile", type=Path, required=True)
    docs = sub.add_parser("extract-pdf")
    docs.add_argument("path", type=Path)
    docs.add_argument("--output", type=Path, required=True)
    docs.add_argument("--ocr-page", type=int)
    docs.add_argument("--language", default="por")
    args = parser.parse_args()
    Path(os.getenv("BDT_DATA_DIR", "data")).mkdir(parents=True, exist_ok=True)
    if args.command == "download":
        result = safe_download(args.url, args.path, args.max_bytes)
    elif args.command == "extract-pdf":
        result = inspect_pdf(args.path)
        if args.ocr_page:
            if not 1 <= args.ocr_page <= len(result["pages"]):
                parser.error("Page outside document")
            page = result["pages"][args.ocr_page - 1]
            if page["route"] == "native":
                parser.error("Native extraction already works; OCR not justified")
            text = ocr_page(args.path, args.ocr_page, args.language)
            page["ocr_candidate_text"] = text
            page["ocr_candidates"] = candidates(text)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(args.output))
        return
    else:
        database = Database(args.database)
        database.initialize()
        if args.command == "init-db":
            result = {"schema_version": 1}
        elif args.command == "create-user":
            from .api import Credentials
            password = getpass.getpass("Password (minimum 12 characters): ")
            credentials = Credentials(username=args.username, password=password)
            with database.session() as session:
                session.add(User(username=credentials.username.lower(), password_hash=password_hash(password), role=args.role))
            result = {"created": credentials.username.lower(), "role": args.role}
        else:
            dataset = args.command.removeprefix("import-")
            source = file_source(args.path, dataset, args.url, args.reference_date)
            if dataset == "ibge":
                result = {"municipalities": import_ibge(database, args.path, source), "scope": "provided_file"}
            elif dataset in {"cnes", "inep", "places"}:
                rows = csv_records(args.path, args.member, args.encoding) if dataset == "inep" or args.path.suffix.lower() == ".csv" else json_records(args.path, args.root)
                result = import_places(database, rows, source, dataset)
            elif dataset == "finance":
                result = {"inserted": import_finance(database, json_records(args.path), source)}
            else:
                profile = json.loads(args.profile.read_text())
                rows = transferegov_rows(csv_records(args.path, args.member, args.encoding), **profile)
                result = {"inserted": import_finance(database, rows, source)}
    if "database" in locals():
        database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
