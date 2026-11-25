# Public test fixtures

These are reduced, anonymized metadata fixtures created for deterministic unit tests.
They contain no source recording paths, real device/object identifiers, operator details,
or camera-vendor deployment commands. Large MKV media files are intentionally omitted.

- sample1_flat/: finalized flat recording with one camera, metadata, a compact timing CSV,
  and a minimal start/stop log.
- sample2_primary/: finalized recording_primary_* example.
- sample2_live/: two hidden .live_* examples with restart evidence; one is stopped and
  one remains incomplete.

All identifiers, dates, camera labels, and clock values in these fixtures are synthetic.
The CSV timing values preserve representative monotonic spans for parser tests only.
