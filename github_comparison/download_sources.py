"""Fetch only the pinned, reviewed example policies, enum and license.

This script performs downloads, not installation or execution of upstream code.
The benchmark loads the two policy classes after removal of their enum import.
"""
from pathlib import Path
import base64,hashlib,json,urllib.request

ROOT=Path(__file__).resolve().parent/'upstream/neuron_poker'
FILES={
 'LICENSE':'af5406fc351b8a28fa90bf2bae5c19d33fe94911',
 'agents/agent_consider_equity.py':'3cfeda015fc77f6889522dc3fdbeaedee4206929',
 'agents/agent_random.py':'687e87e4e00de81f68514820c3458141dca0531d',
 'gym_env/enums.py':'8f925dd330dfa3f08500e68a69c12ee514973084',
}
for path,sha in FILES.items():
    req=urllib.request.Request('https://api.github.com/repos/dickreuter/neuron_poker/git/blobs/'+sha,
                               headers={'User-Agent':'poker-policy-comparison'})
    with urllib.request.urlopen(req,timeout=30) as response:r=json.load(response)
    data=base64.b64decode(r['content'])
    actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if actual!=sha:raise RuntimeError('Git blob hash mismatch: '+path)
    dest=ROOT/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    print('Verified',path)
