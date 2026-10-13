"""Real-sim/fake-API max profile and explicit-effort fallback accounting."""
import copy,json,os
from pathlib import Path
import sys,tempfile
from unittest.mock import patch
workspace=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(workspace))
import loho_frontier_eval as runner


class Reply:
    headers={'x-request-id':'offline-astra-max'}
    def __init__(self,status,usage=None,expensive=False):
        self.status_code,self.ok,self.usage,self.expensive=status,status==200,usage,expensive
    def json(self):
        if self.ok:
            if self.expensive:
                return {'id':'expensive-test','status':'completed','model':'gpt-6-astra','service_tier':'default',
                    'usage':{'input_tokens':3000000,'output_tokens':100000,
                        'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':0}},
                    'output':[{'type':'reasoning','id':'large-history','summary':[],
                               'encrypted_content':'opaque-history-'+'x'*2000000},
                              {'type':'function_call','call_id':'hold1','name':'move_to',
                               'arguments':'{"targets":{"gripper":1},"note":"offline hold"}'}]}
            return {'id':'max-test','status':'completed','model':'gpt-6-astra','service_tier':'default',
                'usage':{'input_tokens':100,'output_tokens':10,'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':0}},
                'output':[{'type':'function_call','call_id':'done1','name':'done','arguments':'{"summary":"offline","hindsight":"test"}'}]}
        return {'error':{'code':'unsupported_value' if self.status_code==400 else 'rate_limit',
            'param':'reasoning.effort' if self.status_code==400 else None,
            'message':'Unsupported reasoning effort max' if self.status_code==400 else 'Rate limited'},
            'usage':self.usage}


class Session:
    def __init__(self,scenario): self.scenario,self.bodies=scenario,[]
    def post(self,url,json,headers,timeout):
        self.bodies.append(copy.deepcopy(json))
        if self.scenario=='expensive_history' and len(self.bodies)==1:return Reply(200,expensive=True)
        if self.scenario=='default' or len(self.bodies)>1:return Reply(200)
        if self.scenario=='ordinary_error':return Reply(429)
        usage={'input_tokens':0,'output_tokens':0,'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':0}} if self.scenario=='known_failure' else None
        return Reply(400,usage)
    def close(self):pass


os.environ['MUJOCO_GL']='osmesa'; os.environ['PYOPENGL_PLATFORM']='osmesa'
base=workspace/'loho_runs/astra_max_test_posix'; base.mkdir(exist_ok=True)
out=Path(tempfile.mkdtemp(prefix='run_',dir=str(base))); results=[]
for name in ['default','expensive_history','unknown_failure','known_failure','call_cap','ordinary_error']:
    session=Session(name); folder=out/name
    argv=['loho_frontier_eval.py','control','--repo','/root/projects/LIBERO-LOHO','--task','0','--outdir',str(folder)]
    if name=='call_cap':argv+=['--max-decisions','1']
    with patch.object(sys,'argv',argv),patch.object(runner,'load_key',lambda:'offline'), \
         patch.object(runner,'runtime_info',lambda unused:{'test':'Astra max fallback','real_api_calls':0}),patch('requests.Session',lambda:session):
        try:runner.main()
        except RuntimeError:assert name=='ordinary_error'
    r=json.loads((folder/'summary.json').read_text())
    assert r['model_id']=='gpt-6-astra' and r['effort']=='max' and r['effort_fallback']=='xhigh'
    assert r['image_history_observations']==0 and r['max_output_tokens_per_call']==128000
    assert r['max_action_steps']==2000 and r['max_estimated_api_cost_usd'] is None
    assert r['cost_guard_enabled'] is False
    assert r['media_mode']=='video_only' and r['png_frames_saved'] is False
    assert not list(folder.glob('*.png'))
    assert 'next_request_cost_reservation_usd' not in r and 'unresolved_request_cost_reservation_usd' not in r
    assert all('request_cost_reservation_usd' not in a and 'unsupported_effort_cost_reservation_usd' not in a for a in r['api_attempts'])
    assert session.bodies[0]['reasoning']['effort']=='max'
    if name in ('unknown_failure','known_failure'):
        assert len(session.bodies)==2 and session.bodies[1]['reasoning']['effort']=='xhigh'
        assert r['decisions_used']==2 and len(r['fallback_events'])==1
        assert r['effective_effort']=='xhigh'
        if name=='unknown_failure':
            assert not r['cost_complete'] and r['estimated_api_cost_usd'] is None
            assert r['api_attempts'][0]['usage'] is None
        else:assert r['cost_complete']
    elif name=='call_cap':
        assert len(session.bodies)==1 and r['termination_reason']=='decision_budget'
        assert r['effective_effort']=='max' and 'fallback_attempt_id' not in r['fallback_events'][0]
    elif name=='ordinary_error':
        assert len(session.bodies)==1 and not r['fallback_events'] and r['termination_reason']=='error'
    elif name=='expensive_history':
        assert len(session.bodies)==2 and r['termination_reason']=='model_done'
        assert r['cost_complete'] and r['estimated_api_cost_usd']>25
        assert any(len(item.get('encrypted_content',''))>2000000 for item in session.bodies[1]['input'])
    else:
        assert len(session.bodies)==1 and not r['fallback_events'] and r['termination_reason']=='model_done'
    results.append({'scenario':name,'passed':True,'calls':r['decisions_used'],'stop':r['termination_reason']})
    print('Astra max '+name+' passed',flush=True)
runner.write_json(base/'test_result.json',{'passed':True,'real_api_calls':0,'run_directory':str(out),'scenarios':results})
