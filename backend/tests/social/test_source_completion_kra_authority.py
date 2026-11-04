"""Invisible or unreviewed publisher text cannot establish report authority."""
import pytest

from seeding.native_report_authority import capture_kra_release
from test_b86_native_authority import HTML, receipt


@pytest.mark.parametrize('tag', [
    b'<p hidden>', b'<p aria-hidden="true">', b'<p aria-hidden="TRUE">',
    b'<p style="display:none">', b'<p style="visibility:hidden">',
    b'<p class="unknown-scope">', b'<p hidden aria-hidden="false">',
    b'<p aria-hidden="true" aria-hidden="false">',
], ids=['hidden', 'aria', 'aria-case', 'display', 'visibility', 'unknown-class', 'hidden-with-aria', 'duplicate-aria'])
@pytest.mark.parametrize('location', ['lead', 'day'])
def test_source_completion_kra_hidden_or_unknown_scope_and_day_refuse(tmp_path, tag, location):
    body = (HTML.replace(b'<p>', tag, 1) if location == 'lead'
            else HTML.replace(b'<p>PRESS RELEASE', tag + b'PRESS RELEASE'))
    proof, reason = capture_kra_release(receipt(tmp_path, body))
    assert proof is None and reason == 'native_report_date_or_scope_unavailable'


@pytest.mark.parametrize('wrapper', [
    b'<section hidden>', b'<section aria-hidden="true">',
    b'<section style="display:none">', b'<template>', b'<noscript>',
    b'<dialog>', b'<details>', b'<canvas>', b'<datalist>', b'<iframe>',
], ids=['hidden', 'aria', 'css', 'template', 'noscript', 'dialog', 'details', 'canvas', 'datalist', 'iframe'])
def test_source_completion_kra_hidden_ancestors_refuse(tmp_path, wrapper):
    closing = b'</' + wrapper[1:].split(b'>')[0].split()[0] + b'>'
    assert capture_kra_release(receipt(tmp_path, wrapper + HTML + closing))[0] is None


@pytest.mark.parametrize('body', [
    HTML.replace(b'The Kenya', b'<span hidden>The Kenya</span>'),
    HTML.replace(b'10/07/2025', b'<span hidden>10/07/2025</span>'),
    HTML.replace(b'<p>', b'<div>Unreviewed context</div><p>', 1),
], ids=['nested-hidden-lead', 'nested-hidden-day', 'nonleading-scope'])
def test_source_completion_kra_nested_or_nonleading_authority_refuses(tmp_path, body):
    assert capture_kra_release(receipt(tmp_path, body))[0] is None


@pytest.mark.parametrize('body', [HTML, HTML.replace(b'<p>', b'<p style="text-align: justify;">')],
                         ids=['visible', 'reviewed-alignment'])
def test_source_completion_kra_visible_control_retains_exact_day(tmp_path, body):
    proof, reason = capture_kra_release(receipt(tmp_path, body))
    assert reason is None and proof is not None
    assert proof.value['published_on'] == '2025-07-10'
    assert proof.value['period'] == 'FY 2024/25'


@pytest.mark.parametrize('prefix', [
    b'<style>.blog-content {display:none}</style>',
    b'<style>.bottom-wrapper {display:none}</style>',
    b'<link rel="stylesheet" href="https://www.kra.go.ke/unknown.css">',
    b'<link rel="alternate StyleSheet" href="https://www.kra.go.ke/unknown.css">',
    b'<script>document.body.hidden=true</script>',
], ids=['article-style', 'day-style', 'stylesheet', 'alternate-stylesheet', 'script'])
def test_source_completion_kra_stylesheet_dependent_pages_refuse(tmp_path, prefix):
    assert capture_kra_release(receipt(tmp_path, prefix + HTML))[0] is None


@pytest.mark.parametrize('wrapper', [b'<div class="hidden">', b'<div class="d-none">', b'<div id="unknown">'])
def test_source_completion_kra_unreviewed_ancestor_profile_refuses(tmp_path, wrapper):
    assert capture_kra_release(receipt(tmp_path, wrapper + HTML + b'</div>'))[0] is None


@pytest.mark.parametrize('sibling', [
    b'<img src="x" onerror="document.body.hidden=true">',
    b'<svg onload="document.body.hidden=true"></svg>',
    b'<iframe srcdoc="&lt;script&gt;parent.document.body.hidden=true&lt;/script&gt;"></iframe>',
    b'<iframe src="javascript:parent.document.body.hidden=true"></iframe>',
    b'<meta http-equiv="refresh" content="0;url=/other">',
    b'<div style="position:fixed;inset:0;background:white">Overlay</div>',
    b'<p style="display:none">Unrelated paragraph</p>',
    b'<div class="unreviewed">Unreviewed source context</div>',
    b'<p onclick="document.body.hidden=true">Other text</p>',
    b'<a href="javascript:document.body.hidden=true">Other text</a>',
    b'<object data="/unreviewed"></object>',
    b'<embed src="/unreviewed">',
], ids=['img-event', 'svg-event', 'frame-srcdoc', 'frame-script', 'navigation', 'overlay',
        'paragraph-css', 'unknown-sibling-class', 'paragraph-event', 'script-link', 'object', 'embed'])
def test_source_completion_kra_entire_document_must_match_static_profile(tmp_path, sibling):
    assert capture_kra_release(receipt(tmp_path, HTML + sibling))[0] is None


@pytest.mark.parametrize('prefix', [
    b'<!--><script>document.body.hidden=true</script>-->',
    b'<!--><style>.blog-content{display:none}</style>-->',
    b'<!--><img src=x onerror="document.body.hidden=true">-->',
    b'<![CDATA[<script>document.body.hidden=true</script>]]>',
    b'<?unreviewed processing instruction?>',
    b'<!DOCTYPE html PUBLIC "unreviewed">',
], ids=['abrupt-script', 'abrupt-style', 'abrupt-handler', 'cdata', 'processing', 'external-doctype'])
def test_source_completion_kra_ambiguous_raw_markup_refuses(tmp_path, prefix):
    assert capture_kra_release(receipt(tmp_path, prefix + HTML))[0] is None


@pytest.mark.parametrize('ctype', [
    'text/html; charset=UTF-16', 'text/html; charset=ISO-2022-JP',
    'text/html; charset=UTF-8; charset=UTF-16',
])
def test_source_completion_kra_unreviewed_charset_refuses(tmp_path, ctype):
    assert capture_kra_release(receipt(tmp_path, HTML, ctype=ctype))[0] is None


def test_source_completion_kra_ascii_declaration_cannot_relabel_utf8_body(tmp_path):
    assert capture_kra_release(receipt(tmp_path, HTML + '\N{EN DASH}'.encode(), ctype='text/html; charset=us-ascii'))[0] is None


@pytest.mark.parametrize('ctype', ['text/html', 'text/html; charset=UTF-8', 'text/html; charset="us-ascii"'])
def test_source_completion_kra_same_decoding_and_benign_layout_control(tmp_path, ctype):
    proof, reason = capture_kra_release(receipt(tmp_path, b'<!DOCTYPE html>' + HTML + b'<!-- layout refresh -->', ctype=ctype))
    assert proof is not None and reason is None
    assert proof.value['published_on'] == '2025-07-10'
