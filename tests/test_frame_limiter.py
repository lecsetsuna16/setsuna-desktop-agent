from pathlib import Path
import shutil
import subprocess
import unittest


class FrameLimiterTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for renderer source tests')
    def test_visible_and_hidden_limits_and_animation_clock(self):
        root = Path(__file__).resolve().parents[1] / 'resona_desktop_pet/live2d/web/v081'
        source = (root / 'frame-limiter.js').read_text(encoding='utf-8')
        source += '\n' + (root / 'frame-driver.js').read_text(encoding='utf-8')
        source += '''
import assert from 'node:assert/strict';
const limiter=createFrameLimiter(30,5);
let visible=0,hidden=0,animation=0,last=0;
const advance=createFrameDriver({resetBase(){},updateMotion(dt){animation+=dt;},
  updatePhysics(){},stabilizePhysics(){}});
for(let i=0;i<=240;i++){
  const now=i*1000/120,shown=now<1000;
  if(limiter.due(now,shown)){
    if(shown)visible++;else hidden++;
    advance((now-last)/1000);last=now;
  }
}
assert.ok(visible>=29&&visible<=31,`visible frames: ${visible}`);
assert.ok(hidden>=4&&hidden<=6,`hidden frames: ${hidden}`);
assert.ok(Math.abs(animation-last/1000)<1e-8,'animation lost elapsed time');
assert.ok(limiter.due(2020,true),'showing again should render promptly');
'''
        result = subprocess.run([shutil.which('node'), '--input-type=module', '-e', source],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
