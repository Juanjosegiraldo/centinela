import os, requests, json
email = os.environ.get('JIRA_EMAIL')
token = os.environ.get('JIRA_TOKEN')
if not email or not token:
    print(json.dumps({'error': 'missing_credentials'}))
    raise SystemExit(1)
url = 'https://juangira15.atlassian.net/rest/api/3/search/jql'
params = {
    'jql': 'assignee=currentUser() AND project=VOR',
    'fields': 'key,summary,status,assignee,updated,description,labels',
    'maxResults': '100'
}
resp = requests.get(url, params=params, auth=(email, token))
out = None
try:
    out = resp.json()
except Exception:
    out = {'error': 'bad_response', 'status_code': resp.status_code, 'text': resp.text}

with open('tests/jira_issues.json', 'w', encoding='utf-8') as f:
    json.dump(out, f)
print(json.dumps({'ok': True, 'saved': 'tests/jira_issues.json'}))
