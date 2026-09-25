"""Schema for the server's published certificate authority."""

from pydantic import BaseModel, Field


class TlsAuthorityOut(BaseModel):
    """The certificate authority that issued the server's own certificate.

    `sha256` is the SHA-256 of the certificate's DER form in lowercase hex:
    the value an administrator compares between the panel and the agent's
    window before an agent trusts the authority. A station computes the
    fingerprint again itself and does not rely on this field.
    """

    pem: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
