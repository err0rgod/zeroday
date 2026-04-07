import sys
sys.path.append(r'd:\zeroday')
from lib.blob_store import load_subscribers
import pprint
import json
subs = load_subscribers()
with open('d:\\zeroday\\output.txt', 'w') as f:
    json.dump(subs, f, indent=2)
