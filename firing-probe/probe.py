# ruff: noqa
"""CodeQL firing probe (NEO-PLAN-2026-004 S10.4) — NEVER MERGE.

Deliberately vulnerable snippet that exists only on this branch to prove the
CodeQL default-setup PR analysis fails the code-scanning results check on a
new high-severity finding. flask is modelled by CodeQL by import name; the
package does not need to be installed for extraction.
"""

import os

from flask import request


def handle():
    # py/command-line-injection: remote flow source -> system command
    os.system("echo " + request.args.get("name", ""))
