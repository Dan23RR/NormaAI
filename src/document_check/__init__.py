"""Check a document's legal references against the official text in force.

Prototype of "controlla un documento": a consultant uploads a document they
already have (privacy notice, AI policy, contract clause, an assistant's
answer) and gets back, for every reference to a provision, whether the
provision exists in the text in force, whether the quoted words are really
there, and whether the article changed after the document was written. The
references checked are recorded in a lock file, so a later run says which
documents to redo when a cited provision changes.

- ``extract``: the references, acts and quotes in a document's text.
- ``official``: the official EU texts by version, from CELLAR, cached on disk.
- ``check``: the comparison, the lock file and the later re-check.
- ``report``: the HTML report and the plain-text summary.

The command line is ``scripts/check_document.py``.
"""
