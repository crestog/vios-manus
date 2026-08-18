from pathlib import Path
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas import maps, ingest


def test_terms_value_is_defensive():
    assert maps._terms_value(None) == []
    assert maps._terms_value('["person", "screen"]') == ["person", "screen"]
    assert maps._terms_value('plain legacy label') == ['plain legacy label']
    assert maps._terms_value('{broken') == ['{broken']


def test_map_meta_skips_malformed_rows():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    maps.ensure_schema(conn)
    conn.execute(
        "INSERT INTO map_point(level, ref, video_key, x, y, cluster, t_start, source) "
        "VALUES ('video','v1','v1',0,0,0,0,'visual')")
    conn.execute(
        "INSERT INTO map_cluster(level, cluster, label, terms, size, videos, cx, cy) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ('video', 0, 'good', json.dumps(['visual']), 1, 1, 0, 0))
    conn.execute(
        "INSERT INTO map_cluster(level, cluster, label, terms, size, videos, cx, cy) "
        "VALUES ('video','bad','legacy','not-json','bad','bad','bad','bad')")
    conn.commit()
    out = maps.meta(conn, 'video')
    assert out['ok'] is True
    assert out['count'] == 1
    assert len(out['clusters']) == 1
    assert out['clusters'][0]['terms'] == ['visual']


def test_caption_asset_manifest_is_detected():
    assert ingest._looks_like_asset_manifest({
        'file_name': None, 'caption': 'manifest · vios:8'})
    assert ingest._looks_like_asset_manifest({
        'file_name': '8-manifest.json', 'caption': ''})
    assert not ingest._looks_like_asset_manifest({
        'file_name': '8.json', 'caption': 'meta · vios:8'})


def test_hotfix_contracts_are_present():
    engine = (ROOT / 'vios/process/engine.py').read_text()
    audio = (ROOT / 'vios/process/runners/audio.py').read_text()
    server = (ROOT / 'atlas/server.py').read_text()
    media = (ROOT / 'atlas/media.py').read_text()
    js = (ROOT / 'atlas/web/atlas.js').read_text()
    css = (ROOT / 'atlas/web/atlas.css').read_text()
    assert 'VIOS_STAGE_SNAPSHOT_ONLY_FINAL' in engine
    assert 'stage still has queued/running work' in engine
    assert 'Pipeline.from_pretrained(job.component.model, token=token)' in audio
    assert 'def _reconcile_boot' in server
    assert 'poster-missing' in js
    assert 'ATLAS_POSTER_FALLBACK_WAIT' in media
    assert 'width:100vw' in css and 'height:100dvh' in css


if __name__ == '__main__':
    test_terms_value_is_defensive()
    test_map_meta_skips_malformed_rows()
    test_caption_asset_manifest_is_detected()
    test_hotfix_contracts_are_present()
    print('live hotfix tests passed')
