"""Offline native Opus streaming, signed-prefix, billing and real-sim checks."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "src"))
import loho_frontier_eval as runner
from loho_anthropic import OpusConversation, send_response, normalized_usage, request_body
from loho_telemetry import AttemptLedger

PRICING = json.loads((workspace/'config/pricing-opus.json').read_text())
USAGE = {'input_tokens': 100, 'cache_read_input_tokens': 200,
         'cache_creation_input_tokens': 50, 'output_tokens': 80}


class Reply:
    ok, status_code, headers = True, 200, {'request-id': 'offline-opus'}

    def __init__(self, name='move_to', arguments=None, stop='tool_use', interrupted=False, usage=None):
        self.name, self.arguments, self.stop, self.interrupted = name, arguments or {'targets': {'x': 0}, 'note': 'test'}, stop, interrupted
        self.usage = USAGE if usage is None else usage

    def iter_lines(self):
        events = [
            {'type': 'message_start', 'message': {'id': 'msg1', 'model': 'claude-opus-5-5', 'usage': dict(self.usage, output_tokens=1)}},
            {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': '', 'signature': ''}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'signature_delta', 'signature': 'signed-prefix'}},
            {'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'tool_use', 'id': 'tool1', 'name': self.name, 'input': {}}},
            {'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(self.arguments)}}]
        for e in events:
            yield b'data: '+json.dumps(e).encode()
        if self.interrupted:
            import requests
            raise requests.exceptions.ReadTimeout('offline interrupted stream')
        yield b'data: '+json.dumps({'type': 'message_delta', 'delta': {'stop_reason': self.stop}, 'usage': {'output_tokens': self.usage['output_tokens']}}).encode()
        yield b'data: '+json.dumps({'type': 'message_stop'}).encode()

    def close(self):
        pass


class Session:
    def __init__(self, reply=None, expensive=False):
        self.reply, self.bodies, self.expensive = reply, [], expensive

    def post(self, url, json, headers, timeout, stream):
        assert url == 'https://api.anthropic.com/v1/messages' and stream
        assert json['output_config']['effort'] == 'max'
        assert json['tool_choice']['type'] == 'auto'
        if 'model' in json:
            assert json['stream'] is True
        self.bodies.append(copy.deepcopy(json))
        if self.reply:
            return self.reply
        if len(self.bodies)==1:
            state=__import__('json').loads(json['messages'][-1]['content'][0]['text'])['measured_absolute_pose']
            usage = dict(USAGE, input_tokens=10000000) if self.expensive else None
            return Reply(arguments={'targets': {'x': state['x']+.01, 'z':state['z']+.01}, 'note':'offline free-space move'}, usage=usage)
        return Reply('give_up', {'reason':'offline complete','hindsight':'test'})

    def close(self):
        pass


class OpusTests(unittest.TestCase):
    def ledger(self):
        return AttemptLedger(pricing=PRICING)

    def test_usage_sums_all_input_categories_once(self):
        u=normalized_usage(USAGE,True)
        self.assertEqual(u['input_tokens'],350)
        ledger=self.ledger(); a=ledger.begin(0,'claude-opus-5-5','default')
        ledger.update(a,'usage',usage=u)
        self.assertAlmostEqual(a['estimated_api_cost_usd'],(100*4+200*.2+50*5+80*20)/1000000)

    def test_stream_preserves_signed_thinking_and_tool_input(self):
        ledger=self.ledger(); a=ledger.begin(0,'claude-opus-5-5','default')
        payload,api=send_response(Session(Reply()),'offline',{'output_config':{'effort':'max'},'tool_choice':{'type':'auto'}},ledger,a)
        self.assertEqual(payload['anthropic_content'][0],{'type':'thinking','thinking':'','signature':'signed-prefix'})
        self.assertEqual(json.loads(payload['output'][0]['arguments'])['targets'],{'x':0})
        self.assertEqual(api['usage']['output_tokens'],80)
        self.assertIsNotNone(a['estimated_api_cost_usd'])

    def test_truncation_keeps_complete_usage(self):
        ledger=self.ledger(); a=ledger.begin(0,'claude-opus-5-5','default')
        with self.assertRaises(RuntimeError):
            send_response(Session(Reply(stop='max_tokens')),'offline',{'output_config':{'effort':'max'},'tool_choice':{'type':'auto'}},ledger,a)
        self.assertEqual(a['outcome'],'incomplete')
        self.assertEqual(a['usage']['output_tokens'],80)
        self.assertIsNotNone(a['estimated_api_cost_usd'])

    def test_nonstream_json_receipt_is_preserved(self):
        reply=Reply()
        reply.headers={'request-id':'json-test','content-type':'application/json'}
        reply.json=lambda:{'id':'json-reply','model':'claude-opus-5-5','stop_reason':'tool_use',
            'usage':USAGE,'content':[{'type':'thinking','thinking':'','signature':'json-sig'},
            {'type':'tool_use','id':'json-tool','name':'move_to','input':{'targets':{'x':0},'note':'test'}}]}
        ledger=self.ledger(); a=ledger.begin(0,'claude-opus-5-5','default')
        payload,api=send_response(Session(reply),'offline',{'output_config':{'effort':'max'},'tool_choice':{'type':'auto'}},ledger,a)
        self.assertEqual(api['usage']['output_tokens'],80)
        self.assertEqual(payload['output'][0]['call_id'],'json-tool')
        self.assertIsNotNone(a['estimated_api_cost_usd'])

    def test_interrupted_stream_is_unresolved_not_free(self):
        ledger=self.ledger(); a=ledger.begin(0,'claude-opus-5-5','default')
        with self.assertRaises(Exception):
            send_response(Session(Reply(interrupted=True)),'offline',{'output_config':{'effort':'max'},'tool_choice':{'type':'auto'}},ledger,a)
        self.assertEqual(a['outcome'],'timeout')
        self.assertIsNone(a['estimated_api_cost_usd'])
        self.assertNotIn('output_tokens',a['usage'])

    def test_append_only_images_and_thinking_with_tool_results(self):
        import numpy as np
        c=OpusConversation('system'); images={'agentview':np.zeros((8,8,3),dtype=np.uint8),'robot0_eye_in_hand':np.ones((8,8,3),dtype=np.uint8)}
        previous_sent=[]
        for index in range(3):
            c.observe('observation'+str(index),images)
            self.assertEqual(c.outgoing()[:len(previous_sent)],previous_sent)
            previous_sent=c.outgoing()
            c.reply([{'type':'thinking','thinking':'','signature':'sig'+str(index)},
                     {'type':'tool_use','id':'call'+str(index),'name':'move_to','input':{'targets':{'x':0},'note':'move'}}])
            c.result('call'+str(index),{'position_error_m':.01})
        self.assertEqual(sum(b['type']=='image' for m in c.outgoing() for b in m['content']),6)
        self.assertEqual(sum(b['type']=='thinking' for m in c.outgoing() for b in m['content']),3)
        self.assertNotIn('signature',json.dumps(c.transcript()))
        self.assertNotIn('base64',json.dumps(c.transcript()))

    def test_real_simulator_native_provider_loop(self):
        repo=Path('/root/projects/LIBERO-LOHO')
        os.environ['MUJOCO_GL']='osmesa'; os.environ['PYOPENGL_PLATFORM']='osmesa'
        base=workspace/'loho_runs/opus_test_posix'; base.mkdir(exist_ok=True)
        out=Path(tempfile.mkdtemp(prefix='run_',dir=str(base)))
        session=Session(expensive=True)
        argv=['src/loho_frontier_eval.py','control','--model','opus','--task','0','--repo',str(repo),'--outdir',str(out)]
        with patch.object(sys,'argv',argv),patch.object(runner,'load_key',lambda variable: 'offline'), \
             patch.object(runner,'runtime_info',lambda unused:{'test':'Opus integration','real_api_calls':0}),patch('requests.Session',lambda:session):
            runner.main()
        r=json.loads((out/'summary.json').read_text())
        self.assertEqual((r['max_decisions'],r['max_action_steps'],r['max_estimated_api_cost_usd']),(80,2000,None))
        self.assertFalse(r['cost_guard_enabled'])
        self.assertGreater(r['estimated_api_cost_usd'],25)
        self.assertNotIn('next_request_cost_reservation_usd',r)
        self.assertTrue(all('request_cost_reservation_usd' not in attempt for attempt in r['api_attempts']))
        self.assertEqual(r['effort'],'max'); self.assertEqual(r['max_output_tokens_per_call'],128000)
        self.assertEqual(r['image_history_observations'],0); self.assertTrue(r['cost_complete'])
        self.assertEqual(r['termination_reason'],'give_up'); self.assertEqual(r['decisions_used'],2)
        self.assertLess(r['decisions'][0]['tool_result']['position_error_m'],.015)
        first,second=session.bodies
        self.assertEqual(second['messages'][:len(first['messages'])],first['messages'])
        self.assertEqual(second['messages'][1]['content'][0]['signature'],'signed-prefix')
        self.assertEqual(second['messages'][2]['content'][0]['type'],'tool_result')
        self.assertNotIn('wooden_cabinet_1_top_region',json.dumps(second))
        from scripts.record_opus_trial import record_trial
        reference=out/'historical_reference'; reference.mkdir()
        baseline=copy.deepcopy(r); baseline['max_estimated_api_cost_usd']=25
        baseline.pop('cost_guard_enabled')
        runner.write_json(reference/'summary.json',baseline)
        record_trial(out,reference)
        result=json.loads((out/'run_result.json').read_text())
        self.assertTrue(result['verification_passed'])
        self.assertFalse(result['cost_guard_enabled'])
        self.assertIsNone(result['max_estimated_api_cost_usd'])
        self.assertEqual(result['budget_policy_change']['reference_max_estimated_api_cost_usd'],25)
        self.assertNotIn('next_request_cost_reservation_usd',result)
        self.assertIn('no spending cap',(out/'STEPS_TAKEN.txt').read_text())
        self.assertFalse(list(out.glob('*.png')))
        self.assertEqual(result['media_mode'],'video_only')
        self.assertFalse(result['png_frames_saved'])
        self.assertEqual(r['decisions'][1]['input_video_frames']['agentview']['frame_index'],r['decisions'][0]['executed_steps'])
        (workspace/'prompts/pose-tools-v1_task0_max.txt').write_text(r['system_prompt']+'\n')
        runner.write_json(base/'test_result.json',{'passed':True,'real_api_calls':0,'run_directory':str(out),'calls':2,'action_steps':r['simulator_action_steps'],'provider':'anthropic','effort':'max'})


if __name__=='__main__':
    unittest.main(verbosity=2)
