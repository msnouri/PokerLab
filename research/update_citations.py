"""Refresh only previously verified OpenAlex records; never fuzzy-match titles."""
import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('papers.updated.json'))
    args = parser.parse_args()
    data = json.loads(Path(__file__).with_name('papers.json').read_text())
    for paper in data['papers']:
        if not paper.get('openalex_id'):
            continue  # An unavailable count is better than an unrelated match.
        url = 'https://api.openalex.org/works/'+paper['openalex_id'].rsplit('/', 1)[-1]
        request = urllib.request.Request(url, headers={'User-Agent': 'PokerLab literature updater'})
        with urllib.request.urlopen(request, timeout=30) as response:
            work = json.load(response)
        if SequenceMatcher(None, work['title'].lower(), paper['indexed_title'].lower()).ratio() < .95:
            raise ValueError('OpenAlex title changed; review manually: '+paper['id'])
        paper['citation_count'] = work['cited_by_count']
        paper['metadata_url'] = url
    data['retrieved_at_utc'] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
    print('Saved', args.output, '- review before replacing the published snapshot.')


if __name__ == '__main__':
    main()
