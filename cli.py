#!/usr/bin/env python3
"""
CLI mode: write a static HTML snapshot of the Vikunja map to a file.

    VIKUNJA_URL=https://vikunja.example.com \\
    VIKUNJA_TOKEN=xxxxx \\
    python3 cli.py [output.html]

Default output: vikunja-map.html
"""
import os
import sys

import mapgen


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'vikunja-map.html'
    page = mapgen.generate()
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f"Wrote {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == '__main__':
    main()
