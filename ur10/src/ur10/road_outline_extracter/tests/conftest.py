"""Put src/ur10 on sys.path so `import road_outline_extracter` resolves.

The package now lives nested under the ur10 package (src/ur10/road_outline_extracter),
so pytest's rootdir-based sys.path insertion isn't enough for the tests' bare
`import road_outline_extracter`. parents[2] is src/ur10.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
