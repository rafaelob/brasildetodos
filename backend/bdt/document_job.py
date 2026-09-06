"""Register and extract an operator-supplied PDF into the private workbench.

This command does not fetch arbitrary URLs, upload originals or publish text.
OCR remains an explicit optional worker action, separate from native extraction.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from sqlalchemy import select
from .evidence import DocumentInput, initialize_extensions, register_document, store_extraction
from .ingest import file_source
from .storage import Database, User


def ingest_document(database, path: Path, *, operator: str, title: str, dataset: str,
                    url: str, reference_date: str | None = None, max_pages: int = 100) -> dict:
    if not path.is_file() or path.stat().st_size > 32*1024*1024:
        raise ValueError('document_file_missing_or_too_large')
    initialize_extensions(database)
    with database.session() as session:
        user=session.scalar(select(User).where(User.username==operator,User.role=='reviewer'))
        if not user:
            raise ValueError('existing_reviewer_operator_required')
        source=file_source(path,dataset,url,reference_date)
        row=register_document(session,DocumentInput(title=title,source=source),user.id)
        identity=row.id
    return store_extraction(database,identity,path,max_pages=max_pages)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path',type=Path)
    parser.add_argument('--database',default=os.getenv('BDT_DATABASE_URL','sqlite:///data/bdt.db'))
    for name in ('operator','title','dataset','url'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--reference-date')
    parser.add_argument('--max-pages',type=int,default=100,choices=range(1,1001),metavar='1..1000')
    args=parser.parse_args(argv)
    Path(os.getenv('BDT_DATA_DIR','data')).mkdir(parents=True,exist_ok=True)
    database=Database(args.database);database.initialize()
    try:
        result=ingest_document(database,args.path,operator=args.operator,title=args.title,
            dataset=args.dataset,url=args.url,reference_date=args.reference_date,max_pages=args.max_pages)
        print(json.dumps(result,ensure_ascii=False))
    finally:
        database.engine.dispose()


if __name__=='__main__':
    main()
