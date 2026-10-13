"""Native Opus Messages API with append-only signed thinking and durable usage."""
import copy
import json
import time


class OpusConversation:
    def __init__(self, system):
        self.system, self.items = system, []

    def _user(self, content):
        if self.items and self.items[-1]['role'] == 'user':
            self.items[-1]['content'].extend(content)
        else:
            self.items.append({'role': 'user', 'content': content})

    def observe(self, text, images):
        from loho_pose_policy import image_content
        content, hashes = image_content(images)
        converted = [{'type': 'text', 'text': text}]
        for part in content:
            if part['type'] == 'input_text':
                converted.append({'type': 'text', 'text': part['text']})
            else:
                converted.append({'type': 'image', 'source': {'type': 'base64',
                    'media_type': 'image/jpeg', 'data': part['image_url'].split(',', 1)[1]}})
        self._user(converted)
        return hashes

    def reply(self, content):
        # Includes every thinking/signature/redacted block, unchanged and ordered.
        self.items.append({'role': 'assistant', 'content': copy.deepcopy(content)})

    def result(self, call_id, result):
        self._user([{'type': 'tool_result', 'tool_use_id': call_id,
                     'content': json.dumps(result, separators=(',', ':'), allow_nan=False)}])

    def nudge(self, text):
        self._user([{'type': 'text', 'text': text}])

    def outgoing(self):
        # Opus 5.5 binds thinking to the complete original prefix, including images.
        return copy.deepcopy(self.items)

    def transcript(self):
        result = copy.deepcopy(self.items)
        for item in result:
            for index, part in enumerate(item['content']):
                if part['type'] == 'image':
                    item['content'][index] = {'type': 'text', 'text': '[Camera observation is in the recorded MP4 at its input_video_frames index.]'}
                if part['type'] in ('thinking', 'redacted_thinking'):
                    item['content'][index] = {'type': 'text', 'text': '[Opaque thinking replayed unchanged in memory; omitted from readable transcript.]'}
        return [{'role': 'system', 'content': self.system}] + result


def request_body(conversation, schemas, args):
    return {'model': 'claude-opus-5-5', 'max_tokens': args.max_output_tokens, 'stream': True,
            'output_config': {'effort': args.effort}, 'thinking': {'type': 'adaptive'},
            'cache_control': {'type': 'ephemeral'}, 'system': conversation.system,
            'messages': conversation.outgoing(),
            'tools': [{'name': s['name'], 'description': s['description'],
                       'input_schema': s['parameters']} for s in schemas],
            'tool_choice': {'type': 'auto', 'disable_parallel_tool_use': True}}


def normalized_usage(raw, final_output=False):
    if not isinstance(raw, dict):
        return None
    names = ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
    # Anthropic input_tokens excludes both cache categories, unlike OpenAI totals.
    if not all(isinstance(raw.get(n), int) and not isinstance(raw[n], bool) and raw[n] >= 0 for n in names):
        return None
    result = {'input_tokens': sum(raw[n] for n in names), 'input_tokens_details': {
        'cached_tokens': raw['cache_read_input_tokens'], 'cache_write_tokens': raw['cache_creation_input_tokens']}}
    if final_output and isinstance(raw.get('output_tokens'), int) and not isinstance(raw['output_tokens'], bool):
        result['output_tokens'] = raw['output_tokens']
    return result


def send_response(session, key, body, ledger, attempt):
    import requests
    started, payload, blocks, argument_chunks = time.monotonic(), {}, {}, {}
    raw_usage, final_usage, stopped = {}, False, False
    try:
        response = session.post('https://api.anthropic.com/v1/messages', json=body,
            headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                     'X-Client-Request-Id': attempt['attempt_id']},
            timeout=(15, 600), stream=True)
        ledger.update(attempt, 'response_headers', http_status=response.status_code,
                      request_id=response.headers.get('request-id'), outcome='response_received')
        if not response.ok:
            payload = response.json()
            raw_usage = payload.get('usage', {})
            final_usage = 'output_tokens' in raw_usage
            message = str(payload.get('error', {}).get('message', 'Anthropic request failed')).replace(key, '[REDACTED]')
            ledger.update(attempt, 'http_failed', api_latency_seconds=time.monotonic()-started,
                outcome='api_error', error=message, usage=normalized_usage(raw_usage, final_usage),
                raw_usage=raw_usage, returned_model=payload.get('model'), returned_service_tier='default')
            raise RuntimeError('Anthropic HTTP {}: {}'.format(response.status_code, message))
        # Accept a complete JSON response too, preserving its usage even if a
        # gateway ignores the requested streaming mode.
        if 'application/json' in response.headers.get('content-type', '').lower():
            native = response.json()
            events = [{'type': 'message_start', 'message': native}]
            events += [{'type': 'content_block_start', 'index': i, 'content_block': b}
                       for i, b in enumerate(native.get('content', []))]
            events += [{'type': 'message_delta', 'delta': {'stop_reason': native.get('stop_reason')},
                        'usage': native.get('usage', {})}, {'type': 'message_stop'}]
            lines = (b'data: ' + json.dumps(e).encode() for e in events)
        else:
            lines = response.iter_lines()
        for line in lines:
            if not line or not line.startswith(b'data:'):
                continue
            event = json.loads(line[5:].strip())
            kind = event.get('type')
            if kind == 'message_start':
                payload = event['message']
                raw_usage.update(payload.get('usage', {}))
                ledger.update(attempt, 'stream_started', response_id=payload.get('id'),
                    returned_model=payload.get('model'), returned_service_tier='default',
                    usage=normalized_usage(raw_usage), raw_usage=copy.deepcopy(raw_usage))
            elif kind == 'content_block_start':
                blocks[event['index']] = copy.deepcopy(event['content_block'])
            elif kind == 'content_block_delta':
                index, delta = event['index'], event['delta']
                block = blocks[index]
                if delta['type'] == 'input_json_delta':
                    argument_chunks[index] = argument_chunks.get(index, '') + delta['partial_json']
                else:
                    field = {'text_delta': 'text', 'thinking_delta': 'thinking', 'signature_delta': 'signature'}.get(delta['type'])
                    if field:
                        block[field] = block.get(field, '') + delta[field]
            elif kind == 'message_delta':
                payload.update(event.get('delta', {}))
                raw_usage.update(event.get('usage', {}))
                final_usage = 'output_tokens' in event.get('usage', {})
                ledger.update(attempt, 'stream_usage', usage=normalized_usage(raw_usage, final_usage),
                              raw_usage=copy.deepcopy(raw_usage), response_status=payload.get('stop_reason'))
            elif kind == 'message_stop':
                stopped = True
            elif kind == 'error':
                raise RuntimeError(str(event.get('error', {}).get('message', 'Anthropic stream error')).replace(key, '[REDACTED]'))
        latency = time.monotonic()-started
        ledger.update(attempt, 'response_metadata', api_latency_seconds=latency,
            usage=normalized_usage(raw_usage, final_usage), raw_usage=raw_usage,
            response_status=payload.get('stop_reason'))
        if not stopped or payload.get('stop_reason') not in ('tool_use', 'end_turn'):
            ledger.update(attempt, 'response_incomplete', outcome='incomplete')
            raise RuntimeError('Opus response incomplete: {}'.format(payload.get('stop_reason')))
        for index, value in argument_chunks.items():
            blocks[index]['input'] = json.loads(value)
        content = [blocks[index] for index in sorted(blocks)]
        calls = [{'type': 'function_call', 'call_id': b['id'], 'name': b['name'],
                  'arguments': json.dumps(b['input'])} for b in content if b['type'] == 'tool_use']
        return {'output': calls, 'anthropic_content': content}, {
            'attempt_id': attempt['attempt_id'], 'request_id': response.headers.get('request-id'),
            'response_id': payload.get('id'), 'returned_model': payload.get('model'),
            'usage': normalized_usage(raw_usage, final_usage), 'raw_usage': raw_usage,
            'returned_service_tier': 'default', 'api_latency_seconds': latency}
    except BaseException as exc:
        if attempt.get('outcome') not in ('api_error', 'incomplete'):
            ledger.update(attempt, 'transport_failed', api_latency_seconds=time.monotonic()-started,
                outcome='timeout' if isinstance(exc, requests.exceptions.Timeout) else 'transport_error',
                error_type=type(exc).__name__, error=str(exc).replace(key, '[REDACTED]'),
                usage=normalized_usage(raw_usage, final_usage), raw_usage=raw_usage)
        raise
    finally:
        if 'response' in locals():
            response.close()
