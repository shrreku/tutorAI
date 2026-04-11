import json
import urllib.error
import urllib.request

BASE = 'http://localhost:8000/api/v1'
EMAIL = 'admin+studyagent@example.com'
PASSWORD = 'AdminPass!2026'
RESOURCE_ID = 'd5714985-ff9e-4f5f-bca0-36406a729cdb'


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


_, raw = call('/auth/login', 'POST', {'email': EMAIL, 'password': PASSWORD})
login = json.loads(raw)
token = login['access_token']

settings_code, _ = call(
    '/users/me/settings',
    'PATCH',
    {
        'consent_training_global': False,
        'consent_personalization': True,
        'learning_preferences': {
            'pace': 'moderate',
            'depth': 'balanced',
            'tutoring_style': 'practice-heavy',
            'hint_level': 'gentle',
            'language': 'en',
            'accessibility': {'captions': True, 'short_answers': True},
        },
    },
    token,
)

nb_code, nb_raw = call(
    '/notebooks',
    'POST',
    {
        'title': 'Learner Personalization Smoke Test',
        'goal': 'Validate user, notebook, and session preference alignment.',
        'settings_json': {'default_mode': 'learn'},
        'personalization': {
            'purpose': 'exam_prep',
            'urgency': True,
            'study_pace': 'intensive',
            'study_depth': 'deep',
            'practice_intensity': 'heavy',
            'exam_context': 'Final exam in 2 weeks',
        },
    },
    token,
)
notebook = json.loads(nb_raw)

attach_code, _ = call(
    f"/notebooks/{notebook['id']}/resources",
    'POST',
    {'resource_id': RESOURCE_ID, 'role': 'primary', 'is_active': True},
    token,
)

sess_code, sess_raw = call(
    f"/notebooks/{notebook['id']}/sessions",
    'POST',
    {
        'resource_id': RESOURCE_ID,
        'selected_resource_ids': [RESOURCE_ID],
        'notebook_wide': False,
        'topic': 'Probability measures and axioms',
        'selected_topics': ['Probability measures', 'Axioms'],
        'mode': 'learn',
        'consent_training': False,
        'resume_existing': False,
        'personalization': {
            'time_budget_minutes': 45,
            'today_goal': 'Review the axioms and practice one worked example.',
            'interaction_style': 'practice-heavy',
            'confidence': 'somewhat',
            'want_hints': True,
            'want_examples': True,
        },
    },
    token,
)
created_session = json.loads(sess_raw)
session_id = created_session['session']['id']

session_code, session_raw = call(f'/sessions/{session_id}', token=token)
session = json.loads(session_raw)
notebook_code, notebook_raw = call(f"/notebooks/{notebook['id']}", token=token)
notebook_detail = json.loads(notebook_raw)

summary = {
    'login_user': login['user'],
    'settings_code': settings_code,
    'notebook_code': nb_code,
    'attach_code': attach_code,
    'session_code': sess_code,
    'session_detail_code': session_code,
    'notebook_detail_code': notebook_code,
    'notebook_personalization': notebook_detail.get('personalization'),
    'session_personalization_snapshot': (session.get('plan_state') or {}).get('learner_personalization'),
    'session_topic': session.get('topic'),
    'turn_count': session.get('turn_count'),
}
print(json.dumps(summary, indent=2))
