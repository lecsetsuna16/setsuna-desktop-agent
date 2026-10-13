import asyncio
import json
import math
import sys
import threading
import time
import wave
import faulthandler
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "TEMP" / "live2d_verification"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QUrl, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from resona_desktop_pet.live2d.canvas import Live2DCanvas
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from resona_desktop_pet.config import ConfigManager
from resona_desktop_pet.ui.luna.main_window import MainWindow
from resona_desktop_pet.backend.mcp_manager import MCPManager
from resona_desktop_pet.live2d.tools import install_live2d_tools
from resona_desktop_pet.live2d.audio import AudioLipSync, pcm_level
from resona_desktop_pet.live2d.protocol import validate_perform, live2d_prompt_path

app = QApplication([])
class TestConfig(ConfigManager):
    @property
    def enable_ip_context(self):
        return False

    @property
    def skills_enabled(self):
        return False

config = TestConfig(str(ROOT / 'config.cfg'))
config.pack_manager.set_active_pack('setsuna')
config.config.set('Physics', 'enabled', 'false')
window = MainWindow(config)
window.setWindowTitle('雪菜 Live2D · 自动验证')
window.show(); window.move(100, 80)
character = window.character
canvas = character._live2d
manager = MCPManager(config)
install_live2d_tools(manager, character)
loop = asyncio.new_event_loop()
thread = threading.Thread(target=loop.run_forever, daemon=True)
thread.start()
checks = []


def qwait(milliseconds):
    events = QEventLoop()
    QTimer.singleShot(milliseconds, events.quit)
    events.exec()


def wait(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qwait(25)
        if predicate():
            return
    raise AssertionError('Timed out: ' + json.dumps(canvas.snapshot, ensure_ascii=False))


def call(name, args=None):
    task = asyncio.run_coroutine_threadsafe(manager.call_tool(name, args or {}), loop)
    wait(task.done)
    return json.loads(task.result())


def perform(**overrides):
    args = dict(expression='neutral', motion='none', look='center', intensity=.6, hold_ms=1800, pack_id='setsuna')
    args.update(overrides)
    result = call('setsuna_perform', args)
    assert result.get('ok') and result.get('status') == 'started', result
    return result


def sample(seconds):
    end = time.monotonic() + seconds
    values = []
    while time.monotonic() < end:
        qwait(35)
        values.append(dict(call('setsuna_status').get('parameters', {})))
    return values


def check(name, value):
    assert value, name
    checks.append(name)
    print('PASS', name, flush=True)


try:
    wait(lambda: canvas.snapshot.get('ready'), 35)
    result = call('setsuna_status')
    check('real_v081_model', result.get('profile') == 'v081l-b' and result.get('model', {}).get('parameters', 0) > 0)
    qwait(350)
    window.grab().save(str(OUT / '01_idle.png'))
    samples = sample(3)
    check('autonomous_breath', max(s['ParamBreath'] for s in samples)-min(s['ParamBreath'] for s in samples) > .03)
    for motion, param, minimum in [('nod','ParamAngleY',3),('shake','ParamAngleX',3),('blink','ParamEyeLOpen',.4)]:
        perform(motion=motion)
        values = sample(2.7)
        amplitude = max(s[param] for s in values)-min(s[param] for s in values)
        check('motion_'+motion, amplitude > minimum)
        check('completed_'+motion, call('setsuna_status').get('action', {}).get('status') == 'completed')
    perform(expression='smile', look='left', hold_ms=2200)
    qwait(650)
    result = call('setsuna_status')
    check('smile_preset', result['expression'] == 'smile')
    check('gaze_left', result['parameters']['ParamEyeBallX'] < -.2)
    window.grab().save(str(OUT / '02_smile_left.png'))
    perform(expression='shy', look='right')
    qwait(650)
    check('gaze_right', call('setsuna_status')['parameters']['ParamEyeBallX'] > .2)
    before = call('setsuna_status')['revision']
    check('reject_unknown_motion', not call('setsuna_perform', {'motion':'wave'})['ok'])
    check('reject_wrong_character', not call('setsuna_perform', {'pack_id':'other'})['ok'])
    check('reject_out_of_range', not call('setsuna_perform', {'intensity':2})['ok'])
    check('invalid_did_not_mutate', call('setsuna_status')['revision'] == before)
    call('setsuna_reset'); qwait(1200)
    check('reset_neutral', call('setsuna_status')['expression'] == 'neutral')
    perform(motion='nod',hold_ms=3000); qwait(650)
    reset_result=call('setsuna_reset')
    check('reset_acknowledged_with_finite_pose', reset_result.get('ok') and all(math.isfinite(v) for v in reset_result['parameters'].values()))
    qwait(1000)
    check('reset_returns_to_idle', call('setsuna_status')['idle']['playing'])
    window.start_thinking(); qwait(600)
    check('thinking_state', call('setsuna_status')['state'] == 'thinking')
    window.set_listening(True); qwait(300)
    check('listening_state', call('setsuna_status')['state'] == 'listening')
    window.set_listening(False); window.finish_processing(); call('setsuna_reset')
    prompt = live2d_prompt_path(config)
    check('separate_live2d_prompt_selected', prompt.name == 'character_prompt_live2d_v003.txt')
    # Silence, audible signal, silence, then stop/interrupt during another signal.
    audio = OUT / 'mouth_test.wav'
    sr = 24000
    samples = array('h', [int(11000*math.sin(2*math.pi*220*i/sr)) if .6 < i/sr < 2.5 else 0 for i in range(sr*3)])
    with wave.open(str(audio), 'wb') as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(sr); file.writeframes(samples.tobytes())
    player = QMediaPlayer(); output = QAudioOutput(); output.setVolume(0); player.setAudioOutput(output)
    lipsync = AudioLipSync(player); lipsync.level.connect(character.set_live2d_audio)
    audio_levels = []; lipsync.level.connect(lambda level, playing: audio_levels.append((level, playing)))
    faulthandler.enable(); faulthandler.dump_traceback_later(15)
    player.setSource(QUrl.fromLocalFile(str(audio))); print('AUDIO_SOURCE_SET',flush=True); player.play(); print('AUDIO_PLAY_RETURNED',flush=True)
    values = sample(3.7)
    check('audio_buffers_observed', any(level > .2 for level, playing in audio_levels))
    check('audio_moves_actual_mouth', max(s['ParamMouthOpenY'] for s in values) > .2)
    check('audio_end_closes_mouth', call('setsuna_status')['parameters']['ParamMouthOpenY'] < .02)
    player.setPosition(800); player.play(); qwait(650); player.stop(); qwait(500)
    check('audio_interrupt_closes_mouth', call('setsuna_status')['parameters']['ParamMouthOpenY'] < .02)
    faulthandler.cancel_dump_traceback_later()
    check('silent_pcm_zero', pcm_level(bytes(1024), 'int16') == 0)
    # All preset combinations must remain finite and acknowledge actual draws.
    from resona_desktop_pet.live2d.protocol import EXPRESSIONS
    for expression in EXPRESSIONS:
        perform(expression=expression); qwait(200)
        check('preset_finite_'+expression, all(math.isfinite(v) for v in call('setsuna_status')['parameters'].values()))
        if expression in ('smile','sad','angry','thinking'):
            qwait(350)
            window.grab().save(str(OUT / ('expression_'+expression+'.png')))
    call('setsuna_reset'); qwait(700)
    window.grab().save(str(OUT / '03_reset.png'))
    # Check the real local player without changing the user's library or volume.
    from resona_desktop_pet.live2d.playlist import Playlist
    from concurrent.futures import Future
    import shutil
    music_dir = OUT / 'test_music'
    music_dir.mkdir(exist_ok=True)
    shutil.copyfile(audio, music_dir / 'test.wav')
    local = character.local_music
    local.playlist = Playlist(music_dir)
    local.set_volume(0)
    local.refresh()
    future = Future()
    local.dispatch({'command': 'play', 'path': 'test.wav'}, future, defer_for_reply=False)
    wait(future.done)
    check('local_music_plays', future.result().get('ok') and local.has_track)
    qwait(400)
    check('local_music_drives_singing', call('setsuna_status')['singing']['music_bound'])
    future = Future()
    local.dispatch({'command': 'stop'}, future)
    check('local_music_stops', future.result().get('ok') and not local.has_track)
    # Keep renderer heartbeats and acknowledgements alive while hidden.
    canvas.hide()
    qwait(600)
    hidden_start = call('setsuna_status')['rendering']['frames']
    qwait(1200)
    hidden = call('setsuna_status')
    check('hidden_frame_limit', not hidden['rendering']['visible'] and
          hidden['rendering']['frames'] - hidden_start <= 9)
    canvas.show()
    qwait(600)
    check('visible_render_resumes', call('setsuna_status')['rendering']['visible'])
    report = {'passed':checks,'snapshot':call('setsuna_status')}
    if '--public-api-test' in sys.argv:
        from resona_desktop_pet.backend.llm_backend import LLMBackend
        from resona_desktop_pet.live2d.protocol import tool_definitions
        # Do not collect OCR, screen context, memories or history for this test.
        for section in config.config.sections():
            for key in ('enable_ip_context', 'skills_enabled'):
                if config.config.has_option(section, key):
                    config.config.set(section, key, 'false')
        backend = LLMBackend(config, mcp_manager=manager)
        llm_config = config.get_llm_config()
        requests = []
        dispatch = manager.call_tool
        async def record_call(name, args):
            result = await dispatch(name, args)
            requests.append({'name': name, 'arguments': args, 'result': json.loads(result)})
            return result
        manager.call_tool = record_call
        # Fixed synthetic test text only. Never send the private character card,
        # user profile, memories, history, OCR, or screen content in this test.
        messages = [{'role':'system', 'content':'You are a software integration test agent. Use the provided tool when requested. After the tool result, return only a JSON object with emotion (use <E:smile>), text_display (Chinese), and text_tts (Japanese).'},
                    {'role':'user', 'content':'Test the rendered sample model: call setsuna_perform once with expression smile, motion nod, look center, intensity 0.6, hold_ms 1800. Then reply with a short test-completed sentence.'}]
        operation = backend._query_with_tools(messages, llm_config['model_name'], llm_config['model_type'],
            llm_config['api_key'], llm_config.get('base_url',''), tools=tool_definitions(), max_tool_rounds=4,
            temperature=.6, max_tokens=1200, pack_id='setsuna', original_question=messages[-1]['content'])
        task = asyncio.run_coroutine_threadsafe(operation, loop)
        wait(task.done, timeout=100)
        response = task.result()
        check('deepseek_final_response', not response.error and bool(response.text_display) and bool(response.text_tts))
        check('deepseek_called_actual_motion', any(r['name']=='setsuna_perform' and r['arguments'].get('motion')=='nod' and r['result'].get('ok') for r in requests))
        window.show_response(response.text_display, response.emotion)
        qwait(500)
        window.grab().save(str(OUT / '04_deepseek_response.png'))
        report['deepseek']={'test_scope':'synthetic public test; no private character prompt sent', 'configured_model':llm_config['model_name'], 'tool_calls':requests,
                            'emotion':response.emotion,'text_display':response.text_display,'text_tts':response.text_tts}
    config.pack_manager.pack_data['character']['live2d']['enabled'] = False
    character._setup_live2d()
    check('static_fallback', character._live2d is None and not character._pixmap.isNull())
    window.grab().save(str(OUT / '05_static_fallback.png'))
    (OUT/'smoke_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ALL', len(checks), 'CHECKS PASSED', flush=True)
finally:
    canvas.dispose()
    window.close()
    loop.call_soon_threadsafe(loop.stop)
