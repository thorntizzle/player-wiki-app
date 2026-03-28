# Campaign Content

This repository keeps application code under version control, but it does not commit live campaign content.

Place local campaign folders under `campaigns/<campaign-slug>/` on your machine as needed for development, local testing, or deployment builds. Those folders are intentionally ignored by Git so proprietary wiki pages, character files, and other campaign-owned assets stay out of the shared repo.

The automated test suite uses the sanitized fixture set under `tests/fixtures/sample_campaigns/` instead of anything in this directory.
