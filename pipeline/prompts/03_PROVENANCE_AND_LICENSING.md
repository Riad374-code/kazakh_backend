# Step 03 — Source Registry, Provenance, and Licence Gates

## Read first

Source sections 1.1-1.7 and 7-9; Steps 01-02 and shared contract.

## Build

Implement `metadata/source_registry.yaml` and validated registry services with
every section 7 field. Seed entries for Copernicus Data Space, Open-Meteo,
Copernicus Marine, OSM/Overpass, EMODnet, Global Fishing Watch, and candidate oil
infrastructure sources. Verify current official terms; never guess. Unknown facts
must be `licence_status: unresolved`, quarantined, warned, and excluded from
redistributable builds.

Preserve OSM attribution/ODbL/query/time/IDs/tags; per-dataset EMODnet source,
coverage, date and licence; Open-Meteo model and endpoint terms including any
non-commercial limitation; Copernicus citations; GFW access and allowed fields;
and original infrastructure IDs/confidence. Separate source-data licences from
software licences.

Create a build-time licence policy, machine-readable report data, and
`licence_report.md` generator. It must report commercial use, redistribution,
modification/share-alike, account/API requirements, rate limits, citations,
limitations, terms-check time, and archived-text/checksum reference.

## Tests and gates

- Resolved compatible sources pass; unresolved or incompatible redistribution is
  quarantined and causes a visible warning/failure according to config.
- Attribution survives manifest export.
- Tests use local registry fixtures; no live terms are invented.
- Document sources needing registration, credentials, or manual approval.
