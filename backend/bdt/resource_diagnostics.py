"""Minimized validation diagnostics; never retain the rejected text or record."""
from __future__ import annotations
import re

TEXT_FIELDS = frozenset({
    'unspecified', 'timestamp', 'objetoContrato', 'orgaoEntidade.razaoSocial',
    'numeroContratoEmpenho', 'codigo_plano_acao', 'nome_objeto',
    'situacao_plano_acao', 'desc_nome', 'situacao',
    'investimentos_previstos.desc_nome_fonte_recurso',
})


class ResourceTextError(ValueError):
    """A validation failure with bounded structural facts, not a text excerpt."""
    def __init__(self, field: str, value: object, limit: int):
        super().__init__('invalid_resource_text')
        self.field = field if field in TEXT_FIELDS else 'unspecified'
        self.value_type = ('null' if value is None else 'string' if isinstance(value, str)
                           else 'boolean' if isinstance(value, bool) else 'number'
                           if isinstance(value, (int, float)) else 'other')
        self.length = len(value) if isinstance(value, str) else None
        self.trimmed_length = len(value.strip()) if isinstance(value, str) else None
        self.limit = limit
        self.rule = ('required_missing' if value is None else 'wrong_type'
                     if not isinstance(value, str) else 'blank'
                     if not value.strip() else 'too_long')
        self.reference = None

    def with_reference(self, profile: str, identity: str, page_hash: str):
        if profile == 'pncp_contracts' and re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}-2-[0-9]{6}/[0-9]{4}', identity):
            self.reference = {'profile': profile, 'record_id': identity}
            if re.fullmatch(r'[0-9a-f]{64}', page_hash):
                self.reference['snapshot_sha256'] = page_hash
        return self

    def public_diagnostic(self) -> dict:
        return {'field': self.field, 'rule': self.rule, 'value_type': self.value_type,
                'length': self.length, 'trimmed_length': self.trimmed_length,
                'accepted_limit': self.limit, 'reference': self.reference,
                'raw_value_included': False}


PUBLIC_MODEL_FIELDS = frozenset({'id','kind','title','municipality_id','attributes',
    'source','source.dataset','source.record_id','source.url','source.reference_date',
    'source.collected_at','source.snapshot_sha256'})
PUBLIC_ERROR_CODES = frozenset({'resource_schema_changed','pncp_identity_disagrees_with_fields',
    'unknown_or_conflicting_buyer_territory','invalid_resource_identity','invalid_resource_date',
    'pncp_update_timestamp_required','inconsistent_pncp_timestamp_timezones','pncp_initial_amount_required',
    'invalid_pncp_revenue_indicator','invalid_decimal_resource_amount','resource_amount_out_of_range',
    'record_outside_requested_buyer','record_outside_requested_dates','record_outside_requested_identity',
    'record_outside_requested_year','resource_title_profile_limit','resource_metadata_too_large'})


def public_validation(error, profile, identity, page_hash):
    """Only known field paths and constraint metadata; no error messages or inputs."""
    from pydantic import ValidationError
    context = ResourceTextError('unspecified', None, 0).with_reference(profile, identity, page_hash).reference
    if isinstance(error, ResourceTextError):
        return error.with_reference(profile, identity, page_hash).public_diagnostic()
    if isinstance(error, ValidationError):
        issues=[]
        for entry in error.errors(include_url=False, include_context=True)[:8]:
            path='.'.join(str(part) for part in entry['loc'])
            kind=entry.get('type','')
            kind=kind if re.fullmatch('[a-z_]{1,80}',kind) else 'validation_error'
            value=entry.get('input')
            ctx=entry.get('ctx',{})
            constraints={key:ctx[key] for key in ('min_length','max_length')
                         if type(ctx.get(key)) is int and 0 <= ctx[key] <= 1_000_000}
            issues.append({'field':path if path in PUBLIC_MODEL_FIELDS else 'unspecified',
                'rule':kind,'length':len(value) if isinstance(value,str) else None,
                'constraints':constraints})
        return {'validation_type':'model','issues':issues,'reference':context,'raw_value_included':False}
    code=str(error) if type(error) is ValueError and str(error) in PUBLIC_ERROR_CODES else 'validation_failure'
    return {'validation_type':'profile','rule':code,'reference':context,'raw_value_included':False}
