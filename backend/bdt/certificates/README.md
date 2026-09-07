# Reviewed public intermediate certificate (not a trust anchor)

`rnp-icpedu-gr46-2025.pem` is the public RNP ICPEdu GR46 OV TLS CA 2025
intermediate published by DETIC/Unicamp, not a private key or a new root CA.
Source page: https://www.detic.unicamp.br/documento/certificados-digitais-das-acs/
Exact file: https://www.detic.unicamp.br/wp-content/uploads/sites/38/2026/05/intermediate_2025.pem
DER SHA-256: `e10747d4da7bab09cba9952f019d3534cb9fba070bf13d8791b1699cd2ff59dd`.
PEM SHA-256: `c5bdf436a7984e244eeacc7d500469d651d13df28d0267e84264f2d94e59443e`.
Public certificate material retains its issuer identity; the software AGPL
notice does not assert authorship over the certificate.

The previous INEP receipt identified this issuer but no complete chain.
`education_tls.py` supplements only the download.inep.gov.br client context.
The complete chain must end at a root already present in certifi. Partial-chain
trust is explicitly disabled (Python otherwise enables it in recent releases).
Certificate signatures, validity periods and hostname checks remain mandatory.
No new root is installed, no AIA URL is fetched and no global store is changed.
A replacement certificate needs a reviewed source and new fingerprint, not an
automatic update from an unverified remote response.

The supplied intermediate passed `openssl verify -x509_strict -CAfile <certifi>`
in the development environment. End-to-end tests perform actual cryptographic
handshakes with ephemeral roots and intermediates and reject an unrelated root,
expired certificates and hostname mismatches. This is not a claim of successful
INEP dataset download; consult the official intake receipt for that result.
