"""
Builds an OWL ontology (rdflib.Graph) from a cleaned provider DataFrame.

Ontology design:
  Classes:     Provider > {Physician, NursePractitioner}
               Credential > {MedicalLicense, BoardCertification, DEARegistration}
               Specialty, State, Organization
  Object props: hasCredential, hasSpecialty, worksAt, licensedIn
  Data props:   npi, fullName, credentialStatus, licenseNumber, expirationDate

Shared URIs for Specialty / State / Organization mean providers with the same
specialty converge on one node — demonstrating linked-data benefits visually.
"""

import re
import pandas as pd
from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, Literal, URIRef

# ── Namespaces ─────────────────────────────────────────────────────────────────
CERT  = Namespace("http://healthcare-demo.example.org/ontology#")
PROV  = Namespace("http://healthcare-demo.example.org/provider/")
CRED  = Namespace("http://healthcare-demo.example.org/credential/")
SPEC  = Namespace("http://healthcare-demo.example.org/specialty/")
STATE = Namespace("http://healthcare-demo.example.org/state/")
ORG   = Namespace("http://healthcare-demo.example.org/org/")


def _uri_slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", str(text).strip()).strip("_")


def _declare_schema(g: Graph) -> None:
    """Add OWL class and property declarations (called once)."""
    classes = [
        (CERT.Provider,             None),
        (CERT.Physician,            CERT.Provider),
        (CERT.NursePractitioner,    CERT.Provider),
        (CERT.Credential,           None),
        (CERT.MedicalLicense,       CERT.Credential),
        (CERT.BoardCertification,   CERT.Credential),
        (CERT.DEARegistration,      CERT.Credential),
        (CERT.Specialty,            None),
        (CERT.State,                None),
        (CERT.Organization,         None),
    ]
    for cls, parent in classes:
        g.add((cls, RDF.type, OWL.Class))
        if parent:
            g.add((cls, RDFS.subClassOf, parent))

    for prop in [CERT.hasCredential, CERT.hasSpecialty, CERT.worksAt, CERT.licensedIn]:
        g.add((prop, RDF.type, OWL.ObjectProperty))

    for prop in [CERT.npi, CERT.fullName, CERT.credentialStatus,
                 CERT.licenseNumber, CERT.expirationDate]:
        g.add((prop, RDF.type, OWL.DatatypeProperty))


def _provider_class(role) -> URIRef:
    if str(role).upper() in ("NP", "PA", "RN", "LPN"):
        return CERT.NursePractitioner
    return CERT.Physician


def _add_provider_triples(g: Graph, row: pd.Series, idx: int) -> None:
    """Emit all triples for a single provider row."""
    npi  = row.get("npi")
    name = row.get("name")

    # Provider URI
    if pd.notna(npi) and npi:
        prov_uri = PROV[str(npi)]
    elif pd.notna(name) and name:
        prov_uri = PROV[f"unknown_{_uri_slug(name)}"]
    else:
        prov_uri = PROV[f"unknown_{idx}"]

    # Type
    g.add((prov_uri, RDF.type, _provider_class(row.get("role", ""))))

    # Data properties
    if pd.notna(npi) and npi:
        g.add((prov_uri, CERT.npi, Literal(str(npi), datatype=XSD.string)))
    if pd.notna(name) and name:
        g.add((prov_uri, CERT.fullName, Literal(str(name), datatype=XSD.string)))
        g.add((prov_uri, RDFS.label, Literal(str(name))))

    # ── Credential ────────────────────────────────────────────────────────────
    cred_type = row.get("credential_type")
    if pd.notna(cred_type) and cred_type:
        cred_class = getattr(CERT, cred_type, CERT.Credential)
        slug = f"{str(npi) if pd.notna(npi) and npi else idx}_{_uri_slug(str(cred_type))}"
        cred_uri = CRED[slug]
        g.add((cred_uri, RDF.type, cred_class))
        g.add((prov_uri, CERT.hasCredential, cred_uri))

        lic = row.get("license_number")
        if pd.notna(lic) and lic:
            g.add((cred_uri, CERT.licenseNumber, Literal(str(lic), datatype=XSD.string)))
            g.add((cred_uri, RDFS.label, Literal(str(lic))))
        else:
            g.add((cred_uri, RDFS.label, Literal(str(cred_type))))

        expiry = row.get("license_expiry")
        if pd.notna(expiry):
            ts = pd.Timestamp(expiry)
            g.add((cred_uri, CERT.expirationDate,
                   Literal(ts.date().isoformat(), datatype=XSD.date)))
            status = "Active" if ts > pd.Timestamp.now() else "Expired"
            g.add((cred_uri, CERT.credentialStatus,
                   Literal(status, datatype=XSD.string)))

    # ── Specialty ─────────────────────────────────────────────────────────────
    spec = row.get("specialty")
    if pd.notna(spec) and spec:
        spec_uri = SPEC[_uri_slug(str(spec))]
        g.add((spec_uri, RDF.type, CERT.Specialty))
        g.add((spec_uri, RDFS.label, Literal(str(spec))))
        g.add((prov_uri, CERT.hasSpecialty, spec_uri))

    # ── State ─────────────────────────────────────────────────────────────────
    state = row.get("state")
    if pd.notna(state) and state:
        state_uri = STATE[str(state)]
        g.add((state_uri, RDF.type, CERT.State))
        g.add((state_uri, RDFS.label, Literal(str(state))))
        g.add((prov_uri, CERT.licensedIn, state_uri))

    # ── Organization ──────────────────────────────────────────────────────────
    org = row.get("organization")
    if pd.notna(org) and org:
        org_uri = ORG[_uri_slug(str(org))]
        g.add((org_uri, RDF.type, CERT.Organization))
        g.add((org_uri, RDFS.label, Literal(str(org))))
        g.add((prov_uri, CERT.worksAt, org_uri))


def build_ontology(df: pd.DataFrame) -> Graph:
    """Build and return an rdflib Graph from a clean provider DataFrame."""
    g = Graph()
    g.bind("cert",  CERT)
    g.bind("prov",  PROV)
    g.bind("cred",  CRED)
    g.bind("spec",  SPEC)
    g.bind("state", STATE)
    g.bind("org",   ORG)
    g.bind("owl",   OWL)

    _declare_schema(g)

    for idx, row in df.iterrows():
        _add_provider_triples(g, row, idx)

    return g
