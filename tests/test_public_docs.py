import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_docs', ROOT / 'scripts/public_docs.py')
public_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public_docs)


def test_exports_match_current_positioning_without_changing_reference_pages(tmp_path):
    for name in ['docs.json', 'introduction.mdx', 'quickstart.mdx', 'authentication.mdx', 'privacy.mdx', 'pricing.mdx']:
        shutil.copy(ROOT / name, tmp_path / name)
    for name in ['models', 'concepts', 'guides', 'api-reference', 'legal']:
        shutil.copytree(ROOT / name, tmp_path / name)
    originals = {p: p.read_text() for p in tmp_path.rglob('*.mdx')}
    for _ in range(2):
        public_docs.refresh(tmp_path)
        for name in ['llms.txt', 'llms-full.txt', 'skill.md']:
            content = (tmp_path / name).read_text()
            assert content == (ROOT / name).read_text()
            assert 'dedicated GPU' in content
            assert 'inference API remains available' in content
            assert 'being deprecated' not in content
        assert all(p.read_text() == content for p, content in originals.items())


def test_exports_include_new_navigation_pages_but_not_unlisted_files(tmp_path):
    (tmp_path / 'docs.json').write_text(json.dumps({'navigation': {'pages': ['introduction', 'new-guide']}}))
    (tmp_path / 'introduction.mdx').write_text('---\ntitle: Tera\n---\nCurrent services')
    (tmp_path / 'new-guide.mdx').write_text('---\ntitle: New guide\ndescription: "API guide"\n---\nPublic API instructions')
    (tmp_path / 'private.mdx').write_text('Unlisted draft must not be exported')
    public_docs.refresh(tmp_path)
    assert 'https://docs.tera.gw/new-guide.md' in (tmp_path / 'llms.txt').read_text()
    assert 'Public API instructions' in (tmp_path / 'llms-full.txt').read_text()
    assert 'Unlisted draft' not in (tmp_path / 'llms-full.txt').read_text()
