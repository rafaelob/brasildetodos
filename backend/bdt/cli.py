"""Operator entry point: ingestion and review-user provisioning stay off public HTTP."""
import argparse
import getpass
import json
import os
from pathlib import Path
from .api import password_hash
from .documents import candidates, inspect_pdf, ocr_page
from .ingest import csv_records, file_source, import_finance, import_ibge, import_places, json_records, safe_download, transferegov_rows
from .json_codec import decode
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
    tgov = sub.add_parser("import-transferegov-finance")
    tgov.add_argument("--downloads", type=Path, default=Path("data/downloads/transferegov"))
    tgov.add_argument("--limit-agreements", type=int, default=None)
    tgov.add_argument("--limit-amendments", type=int, default=None)
    tgov.add_argument("--limit-disbursements", type=int, default=None)
    sync_res = sub.add_parser("sync-resources")
    sync_res.add_argument("profile", choices=["pncp_contracts", "transferegov_special_plans", "obrasgov_projects"])
    sync_res.add_argument("--folder", type=Path, required=True)
    sync_res.add_argument("--start")
    sync_res.add_argument("--end")
    sync_res.add_argument("--year", type=int)
    sync_res.add_argument("--identity")
    sync_res.add_argument("--updates", action="store_true")
    sync_res.add_argument("--page-size", type=int, default=100)
    sync_res.add_argument("--max-pages", type=int, default=100)
    sync_res.add_argument("--collect", action="store_true")
    docs = sub.add_parser("extract-pdf")
    docs.add_argument("path", type=Path)
    docs.add_argument("--output", type=Path, required=True)
    docs.add_argument("--ocr-page", type=int)
    docs.add_argument("--language", default="por")
    ocr = sub.add_parser("ocr-queue")
    ocr_sub = ocr.add_subparsers(dest="ocr_command", required=True)
    ocr_enqueue = ocr_sub.add_parser("enqueue")
    ocr_enqueue.add_argument("document")
    ocr_enqueue.add_argument("--operator", required=True)
    ocr_enqueue.add_argument("--pages", type=int, nargs="+", required=True)
    ocr_enqueue.add_argument("--language", default="por")
    ocr_enqueue.add_argument("--timeout", type=int, default=90)
    ocr_enqueue.add_argument("--max-attempts", type=int, default=2)
    ocr_run = ocr_sub.add_parser("run")
    ocr_run.add_argument("--operator", required=True)
    ocr_run.add_argument("--path", type=Path, required=True)
    ocr_run.add_argument("--lease-seconds", type=int, default=300)
    ocr_list = ocr_sub.add_parser("list")
    ocr_list.add_argument("--status")
    ocr_list.add_argument("--limit", type=int, default=50)
    for name in ("cancel", "retry"):
        item = ocr_sub.add_parser(name)
        item.add_argument("job")
        item.add_argument("--operator", required=True)
    ocr_sub.add_parser("reap")
    ocr_purge = ocr_sub.add_parser("purge")
    ocr_purge.add_argument("--days", type=int, default=30)
    ocr_purge.add_argument("--dry-run", action="store_true")
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
            if not page.get("ocr_eligible", page["route"] not in {"native", "inspect_blank_or_graphic"}):
                parser.error("Native extraction or a blank page does not justify OCR")
            text = ocr_page(args.path, args.ocr_page, args.language)
            page["ocr_candidate_text"] = text
            page["ocr_candidates"] = candidates(text)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(args.output))
        return
    elif args.command == "import-transferegov-finance":
        from ops.transferegov_financial_download_and_ingest import run_ingest
        db_path = Path(args.database.removeprefix("sqlite:///"))
        result = run_ingest(db_path, args.downloads, limit_agreements=args.limit_agreements,
                            limit_amendments=args.limit_amendments, limit_disbursements=args.limit_disbursements)
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
        elif args.command == "sync-resources":
            from .resource_profiles import collection_plan
            from .resource_sync import import_resources
            from .sync import atomic_json, collect, digest
            plan = collection_plan(args.profile, start=args.start, end=args.end, year=args.year,
                                   identity=args.identity, updates=args.updates,
                                   page_size=args.page_size, max_pages=args.max_pages)
            if args.collect:
                collect(plan, args.folder)
            stored = decode((args.folder / 'collection.json').read_bytes())
            if stored.get('plan_sha256') != digest(plan.model_dump()):
                raise ValueError('cli_plan_differs_from_collection')
            result = import_resources(database, args.folder)
            atomic_json(args.folder / 'import-result.json', result)
        elif args.command == "ocr-queue":
            from . import ocr_queue
            if args.ocr_command == "enqueue":
                result = ocr_queue.enqueue(database, args.document, operator=args.operator,
                                           pages=args.pages, language=args.language,
                                           timeout=args.timeout, max_attempts=args.max_attempts)
            elif args.ocr_command == "run":
                result = ocr_queue.run_once(database, args.path, operator=args.operator,
                                            lease_seconds=args.lease_seconds)
            elif args.ocr_command == "list":
                result = ocr_queue.list_jobs(database, status=args.status, limit=args.limit)
            elif args.ocr_command == "cancel":
                result = ocr_queue.cancel(database, args.job, operator=args.operator)
            elif args.ocr_command == "retry":
                result = ocr_queue.retry(database, args.job, operator=args.operator)
            elif args.ocr_command == "reap":
                result = ocr_queue.reap_expired(database)
            else:
                result = ocr_queue.purge(database, older_than_days=args.days, dry_run=args.dry_run)
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
                profile = decode(args.profile.read_bytes())
                rows = transferegov_rows(csv_records(args.path, args.member, args.encoding), **profile)
                result = {"inserted": import_finance(database, rows, source)}
    if "database" in locals():
        database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
