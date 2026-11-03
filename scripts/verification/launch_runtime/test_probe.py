"""Offline refusal and exact product-image controls; no deployment acceptance."""
import base64
import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('launch_probe',Path(__file__).with_name('probe.py'))
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
SOURCE='f'*40

class ProbeTests(unittest.TestCase):
    def test_exact_source_and_every_held_flag(self):
        valid={'RENDER_GIT_COMMIT':SOURCE}
        self.assertEqual(set(probe.held_flags(valid,SOURCE)),set(probe.FLAGS))
        for key in probe.FLAGS:
            for bad in ('true','False','0',0,True,None,'','<unset>'):
                with self.subTest(key=key,value=bad),self.assertRaises(ValueError):
                    probe.held_flags({**valid,key:bad},SOURCE)
        for source in (None,'',True,'g'*40,'f'*39):
            with self.subTest(source=source),self.assertRaises(ValueError):probe.held_flags(valid,source)
        with self.assertRaises(ValueError):probe.held_flags({'RENDER_GIT_COMMIT':'a'*40},SOURCE)

    def test_exact_finite_counters(self):
        self.assertEqual(probe.counter('536870912'),536870912)
        for value in ('','01','-1','NaN','inf','1.0','1e3',True,0,None,'9'*30):
            with self.subTest(value=value),self.assertRaises(ValueError):probe.counter(value)
        for value in (True,False,0.0,float('nan'),float('inf'),-1,None):
            with self.subTest(value=value),self.assertRaises(ValueError):probe.exact_integer(value)

    def test_endpoint_projection_contains_no_credentials(self):
        a=probe.endpoint_metadata('postgresql://alice:never-project-me@aws-1.pooler.supabase.com:6543/postgres?secret=hidden')
        b=probe.endpoint_metadata('postgresql://alice:other@aws-1.pooler.supabase.com:6543/postgres')
        self.assertEqual(a,b);self.assertEqual(a['family'],'transaction_pooler')
        self.assertNotIn('alice',str(a));self.assertNotIn('never-project-me',str(a));self.assertNotIn('hidden',str(a))
        self.assertEqual(probe.endpoint_metadata(None),{'present':False})
        for value in ('','http://bad','postgresql://x@host:0/db',True,0,'postgresql://x@host:bad/db'):
            with self.subTest(value=value),self.assertRaises(ValueError):probe.endpoint_metadata(value)

    def test_cgroup_measurements_and_unavailable_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'memory.current').write_text('104857600\n')
            (root/'memory.max').write_text('536870912\n')
            (root/'cpu.max').write_text('50000 100000\n')
            (root/'memory.events').write_text('low 0\noom 0\n')
            value=probe.cgroup_snapshot(root)
            self.assertEqual(value['memory.current'],104857600)
            self.assertEqual(value['cpu.max'],{'quota_usec':50000,'period_usec':100000})
            self.assertEqual(value['cpu.stat'],{'available':False})
            for raw in ('low 0\nlow 0\n','oom NaN\n','oops\n',' \n'):
                (root/'memory.events').write_text(raw)
                with self.assertRaises(ValueError):probe.cgroup_snapshot(root)

    def test_missing_process_tree_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):probe.process_inventory(Path(directory)/'absent')
            with self.assertRaises(ValueError):probe.process_inventory(Path(directory))

    def test_process_without_rss_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);process=root/'42';process.mkdir()
            (process/'status').write_text('Name: zombie\nThreads: 1\n')
            (process/'comm').write_text('zombie\n');(process/'cmdline').write_bytes(b'')
            result=probe.process_inventory(root)
            self.assertIsNone(result[0]['rss_bytes'])
            (process/'status').write_text('VmRSS: 12 kB\nThreads: 1\n')
            self.assertEqual(probe.process_inventory(root)[0]['rss_bytes'],12288)

    def test_packet_is_bounded_strict_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'packet.json'
            with self.assertRaises(FileNotFoundError):probe.read_packet(path)
            for raw in (b'',b'{}',b'[]',b'null',b'{',b' '*1048577,
                        b'{"fixtures":[],"fixtures":[],"product_sha256":{}}',
                        b'{"fixtures":[NaN],"product_sha256":{}}',
                        b'{"fixtures":[],"product_sha256":{"a":1,"a":2}}'):
                path.write_bytes(raw)
                with self.subTest(raw=raw[:80]),self.assertRaises(ValueError):probe.read_packet(path)
            path.write_text('{"fixtures":[],"product_sha256":{}}')
            self.assertEqual(probe.read_packet(path),{'fixtures':[],'product_sha256':{}})

    def test_real_product_images_and_malformed_refusal(self):
        from PIL import Image
        media=Path(__file__).resolve().parents[3]/'backend/social/media'
        fixtures=[]
        for fmt,mime in [('PNG','image/png'),('JPEG','image/jpeg')]:
            buffer=BytesIO();Image.new('RGB',(64,32),'green').save(buffer,format=fmt)
            raw=buffer.getvalue()
            fixtures.append({'mime':mime,'width':64,'height':32,'base64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()})
        hashes={name:hashlib.sha256((media/name).read_bytes()).hexdigest() for name in probe.MEDIA_FILES}
        result=probe.inspect_images(media,fixtures,hashes)
        self.assertEqual({r['mime_type'] for r in result['images']},{'image/jpeg','image/png'})
        self.assertTrue(result['temporary_files_removed'])
        self.assertIs(result['production_upload_or_delivery_accepted'],False)
        self.assertTrue(all(r['negative_controls_refused']==['wrong_mime','wrong_length','malformed'] for r in result['images']))
        for rows,pins in [(fixtures[:1],hashes),([],hashes),(None,hashes),([fixtures[0]]*2,hashes),
                          (fixtures,{**hashes,'inspection.py':'f'*64}),
                          ([{**fixtures[0],'sha256':'f'*64},fixtures[1]],hashes),
                          ([{**fixtures[0],'width':True},fixtures[1]],hashes)]:
            with self.subTest(rows=rows is None,pins=bool(pins)),self.assertRaises(ValueError):probe.inspect_images(media,rows,pins)

if __name__=='__main__':unittest.main(verbosity=2)
