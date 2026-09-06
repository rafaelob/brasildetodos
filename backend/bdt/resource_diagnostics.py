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
        """Only profile-validated public identifiers and byte hashes may be added."""
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
