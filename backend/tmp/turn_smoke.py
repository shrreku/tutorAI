import json
import urllib.error
import urllib.request

BASE = 'http://localhost:8000/api/v1'
EMAIL = 'admin+studyagent@example.com'
PASSWORD = 'AdminPass!2026'
NOTEBOOK_ID = '655df721-3a96-4cd7-bd45-025c0e9d2bd5'
SESSION_ID = '5335ed40-d01e-42de-9afb-94b2b45e69f4'


def call(path, method='GET', data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.getcode(), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


_, login_raw = call('/auth/login', 'POST', {'email': EMAIL, 'password': PASSWORD})
login = json.loads(login_raw)
token = login['access_token']

messages = [
    'I want a quick check on the axioms with one practice question.',
    'I think sigma fields are like collections closed under complements and countable unions. What should I do next?',
    'Give me one more problem, but keep the hint short.',
]

for index, message in enumerate(messages, 1):
    code, raw = call(
        f'/tutor/notebooks/{NOTEBOOK_ID}/turn',
        'POST',
        {'session_id': SESSION_ID, 'message': message},
        token,
    )
    payload = json.loads(raw)
    print(f'\nTURN {index} STATUS {code}')
    print(json.dumps({
        'response': payload.get('response'),
        'tutor_question': payload.get('tutor_question'),
        'current_step': payload.get('current_step'),
        'current_step_index': payload.get('current_step_index'),
        'objective_title': payload.get('objective_title'),
        'step_transition': payload.get('step_transition'),
        'focus_concepts': payload.get('focus_concepts'),
        'session_complete': payload.get('session_complete'),
        'awaiting_evaluation': payload.get('awaiting_evaluation'),
        'selected_model_id': payload.get('selected_model_id'),
    }, indent=2))

session_code, session_raw = call(f'/sessions/{SESSION_ID}', token=token)
session = json.loads(session_raw)
print('\nSESSION AFTER TURNS')
print(json.dumps({
    'status': session.get('status'),
    'topic': session.get('topic'),
    'turn_count': session.get('turn_count'),
    'current_step': session.get('current_step'),
    'plan_personalization': (session.get('plan_state') or {}).get('learner_personalization'),
}, indent=2))
