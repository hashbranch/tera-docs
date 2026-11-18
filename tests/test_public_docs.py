import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_docs', ROOT / 'scripts/public_docs.py')
public_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public_docs)


def test_exports_are_current_and_legacy_notices_survive_regeneration(tmp_path):
    for name in ['docs.json', 'introduction.mdx', 'quickstart.mdx', 'authentication.mdx', 'privacy.mdx', 'pricing.mdx']:
        shutil.copy(ROOT / name, tmp_path / name)
    for name in ['models', 'concepts', 'guides', 'api-reference', 'legal']:
        shutil.copytree(ROOT / name, tmp_path / name)
    public_docs.refresh(tmp_path)
    for name in ['llms.txt', 'llms-full.txt', 'skill.md']:
        assert (tmp_path / name).read_text() == (ROOT / name).read_text()
        assert 'dedicated GPU' in (tmp_path / name).read_text()
        assert 'being deprecated' in (tmp_path / name).read_text()
    public_docs.refresh(tmp_path)
    for path in public_docs.page_paths(json.loads((tmp_path / 'docs.json').read_text())['navigation']):
        text = (tmp_path / (path + '.mdx')).read_text()
        if path != 'introduction':
            assert text.count(public_docs.NOTICE) == 1
            assert 'description: "Deprecated inference API reference' in text


def test_new_generated_pages_are_marked_legacy():
    page = '---\ntitle: Test\ndescription: "Model guide"\n---\n\nAPI examples'
    result = public_docs.legacy_page(page)
    assert result.count(public_docs.NOTICE) == 1
    assert 'Deprecated inference API reference. Model guide' in result
    assert public_docs.legacy_page(result) == result
