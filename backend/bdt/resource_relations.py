"""Read-only consumers for official rows that are not part of the public catalog.

These routes expose exact published rows for a reviewer. They never create a
place, never sum phases, never turn an empenho into payment and never infer a
recipient or institutional link.
"""
from __future__ import annotations

import re

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, select

from .evidence import Resource
from .pdde import PddePayment, initialize_pdde
from .pncp_documents import PncpContractDocument, PncpDocumentRevision
from .storage import Place
from .transferegov_especiais import TransferegovEspeciaisEmpenho, initialize_transferegov_especiais
from .transferegov_parcerias import TransferegovParceria, initialize_transferegov_parcerias
from .transferegov_parceria_empenhos import (
    TransferegovParceriaEmpenho, initialize_transferegov_parceria_empenhos)

SPECIAL_PLAN_DATASET = 'transferegov_special_plans'
PNCP_DATASET = 'pncp_contracts'
_PNCP_CONTROL = re.compile(r'([A-Z0-9]{12}\d{2})-2-(\d{6})/(\d{4})\Z')


def _plan_id(resource):
    if not isinstance(resource.source, dict) or resource.source.get('dataset') != SPECIAL_PLAN_DATASET:
        raise LookupError('resource_not_special_plan')
    raw = resource.source.get('record_id')
    if not isinstance(raw, str) or not raw.isdigit() or int(raw) < 1:
        raise LookupError('resource_not_special_plan')
    return int(raw)


def special_plan_empenhos(database, resource_id: str, *, page: int = 1, limit: int = 50) -> dict:
    with database.session() as session:
        resource = session.get(Resource, resource_id)
        if resource is None:
            raise LookupError('resource_not_found')
        plan_id = _plan_id(resource)
        condition = TransferegovEspeciaisEmpenho.id_plano_acao == plan_id
        total = session.scalar(select(func.count()).select_from(
            TransferegovEspeciaisEmpenho).where(condition))
        rows = session.scalars(select(TransferegovEspeciaisEmpenho).where(condition)
                               .order_by(TransferegovEspeciaisEmpenho.data_emissao,
                                         TransferegovEspeciaisEmpenho.empenho_id)
                               .offset((page - 1) * limit).limit(limit + 1)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [{'empenho_id': row.empenho_id,
                  'numero_empenho': row.numero_empenho,
                  'situacao': row.situacao,
                  'descricao_situacao': row.descricao_situacao,
                  'data_emissao': row.data_emissao,
                  'valor_empenho_publicado': row.payload.get('valor_empenho'),
                  'ug_responsavel': row.ug_responsavel,
                  'ug_emitente': row.ug_emitente,
                  'fonte_recurso': row.fonte_recurso,
                  'plano_interno': row.plano_interno,
                  'id_plano_acao': row.id_plano_acao,
                  'source': row.source} for row in rows]
        return {'resource_id': resource.id, 'plan_id': plan_id, 'count': len(items),
                'page': page, 'limit': limit, 'total_rows': total, 'has_more': has_more,
                'items': items, 'aggregate': None,
                'scope': 'exact_published_empenhos_for_one_plan_not_a_total_or_payment'}


def place_pdde(database, place_id: str, *, page: int = 1, limit: int = 50) -> dict:
    with database.session() as session:
        place = session.get(Place, place_id)
        if place is None or place.kind != 'school':
            raise LookupError('school_place_not_found')
        condition = PddePayment.school_place_id == place_id
        total = session.scalar(select(func.count()).select_from(PddePayment).where(condition))
        rows = session.scalars(select(PddePayment).where(condition)
                               .order_by(PddePayment.exercise.desc(), PddePayment.key)
                               .offset((page - 1) * limit).limit(limit + 1)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [{'exercise': row.exercise,
                  'school_code': row.school_code,
                  'recipient_cnpj': row.recipient_cnpj,
                  'recipient_name': row.recipient_name,
                  'values': row.values,
                  'source': row.source} for row in rows]
        return {'place_id': place_id, 'count': len(items), 'page': page, 'limit': limit,
                'total_rows': total, 'has_more': has_more, 'items': items, 'aggregate': None,
                'scope': 'exact_published_pdde_rows_for_school_place_not_a_total',
                'note': 'receiver_is_executing_unit_or_entity_not_proof_of_school_payment'}


def _pncp_key(resource):
    if not isinstance(resource.source, dict) or resource.source.get('dataset') != PNCP_DATASET:
        raise LookupError('resource_not_pncp_contract')
    raw = resource.source.get('record_id')
    match = _PNCP_CONTROL.fullmatch(raw) if isinstance(raw, str) else None
    if match is None:
        raise LookupError('resource_not_pncp_contract')
    return match.group(1), int(match.group(3)), int(match.group(2))


def pncp_documents(database, resource_id: str, *, page: int = 1, limit: int = 50) -> dict:
    with database.session() as session:
        resource = session.get(Resource, resource_id)
        if resource is None:
            raise LookupError('resource_not_found')
        cnpj, year, sequence = _pncp_key(resource)
        condition = ((PncpContractDocument.cnpj == cnpj)
                     & (PncpContractDocument.ano_contract == year)
                     & (PncpContractDocument.sequencial_contract == sequence))
        total = session.scalar(select(func.count()).select_from(
            PncpContractDocument).where(condition))
        rows = session.scalars(select(PncpContractDocument).where(condition)
                               .order_by(PncpContractDocument.sequencial_document)
                               .offset((page - 1) * limit).limit(limit + 1)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [{'id': row.id,
                  'sequencial_document': row.sequencial_document,
                  'title': row.title,
                  'document_type': row.document_type,
                  'published_at': row.published_at,
                  'source_url': row.source_url,
                  'snapshot_sha256': row.snapshot_sha256,
                  'byte_size': row.byte_size,
                  'status': row.status,
                  'revision': row.revision,
                  'first_seen_at': row.first_seen_at,
                  'last_seen_at': row.last_seen_at} for row in rows]
        return {'resource_id': resource.id,
                'contract': {'cnpj': cnpj, 'ano': year, 'sequencial': sequence},
                'count': len(items), 'page': page, 'limit': limit, 'total_rows': total,
                'has_more': has_more, 'items': items,
                'publication_allowed': False, 'review_required': True,
                'scope': 'official_document_metadata_and_private_store_hashes_not_publication'}


def parceria(database, parceria_id: str) -> dict:
    with database.session() as session:
        row = session.get(TransferegovParceria, str(parceria_id))
        if row is None:
            raise LookupError('parceria_not_found')
        return {'id': row.id, 'cd_parceria': row.cd_parceria,
                'id_proposta': row.id_proposta, 'situacao': row.situacao,
                'payload': row.payload, 'source': row.source,
                'publication_allowed': False, 'review_required': True,
                'scope': 'exact_published_partnership_header_not_proof_of_execution'}


def parceria_empenhos(database, parceria_id: str, *, page: int = 1, limit: int = 50) -> dict:
    with database.session() as session:
        condition = TransferegovParceriaEmpenho.id_parceria == str(parceria_id)
        total = session.scalar(select(func.count()).select_from(
            TransferegovParceriaEmpenho).where(condition))
        rows = session.scalars(select(TransferegovParceriaEmpenho).where(condition)
                               .order_by(TransferegovParceriaEmpenho.data_emissao,
                                         TransferegovParceriaEmpenho.id_empenho_parceria)
                               .offset((page - 1) * limit).limit(limit + 1)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [{'id_empenho_parceria': row.id_empenho_parceria,
                  'id_parceria': row.id_parceria,
                  'nr_empenho': row.nr_empenho,
                  'aa_empenho': row.aa_empenho,
                  'data_emissao': row.data_emissao,
                  'situacao_siafi': row.situacao_siafi,
                  'favorecido_nome': row.favorecido_nome,
                  'favorecido_id': row.favorecido_id,
                  'valor_empenho_publicado': row.payload.get('valor_empenho'),
                  'payload': row.payload,
                  'source': row.source} for row in rows]
        return {'parceria_id': str(parceria_id), 'count': len(items), 'page': page,
                'limit': limit, 'total_rows': total, 'has_more': has_more, 'items': items,
                'aggregate': None,
                'scope': 'exact_published_empenhos_for_one_partnership_not_a_payment_or_total'}


def install(app, database, reviewer):
    initialize_transferegov_especiais(database)
    initialize_pdde(database)
    initialize_transferegov_parcerias(database)
    initialize_transferegov_parceria_empenhos(database)
    PncpContractDocument.__table__.create(database.engine, checkfirst=True)
    PncpDocumentRevision.__table__.create(database.engine, checkfirst=True)

    @app.get('/api/workbench/resources/{resource_id:path}/empenhos')
    def resource_empenhos(resource_id: str, page: int = Query(1, ge=1, le=100000),
                          limit: int = Query(50, ge=1, le=200), _=Depends(reviewer)):
        try:
            return special_plan_empenhos(database, resource_id, page=page, limit=limit)
        except LookupError:
            raise HTTPException(404, 'resource_not_found') from None

    @app.get('/api/workbench/places/{place_id:path}/pdde')
    def place_pdde_rows(place_id: str, page: int = Query(1, ge=1, le=100000),
                        limit: int = Query(50, ge=1, le=200), _=Depends(reviewer)):
        try:
            return place_pdde(database, place_id, page=page, limit=limit)
        except LookupError:
            raise HTTPException(404, 'school_place_not_found') from None

    @app.get('/api/workbench/resources/{resource_id:path}/documentos')
    def resource_documents(resource_id: str, page: int = Query(1, ge=1, le=100000),
                           limit: int = Query(50, ge=1, le=200), _=Depends(reviewer)):
        try:
            return pncp_documents(database, resource_id, page=page, limit=limit)
        except LookupError:
            raise HTTPException(404, 'resource_not_found') from None

    @app.get('/api/workbench/parcerias/{parceria_id}')
    def partnership(parceria_id: str, _=Depends(reviewer)):
        try:
            return parceria(database, parceria_id)
        except LookupError:
            raise HTTPException(404, 'parceria_not_found') from None

    @app.get('/api/workbench/parcerias/{parceria_id}/empenhos')
    def partnership_commitments(parceria_id: str, page: int = Query(1, ge=1, le=100000),
                                limit: int = Query(50, ge=1, le=200), _=Depends(reviewer)):
        return parceria_empenhos(database, parceria_id, page=page, limit=limit)
