import requests
import re
import html
import secrets
import jose.jwt
import urllib
import pkce

class GroheApi(object):

    def login(self, username, password):
        
        # generate secret for pkce login
        verifier = pkce.generate_code_verifier(length=64)
        challenge = pkce.get_code_challenge(verifier)
        state = secrets.token_urlsafe(16)
        nonce = secrets.token_urlsafe(16)

        # assemble url
        login_url = "https://idp2-apigw.cloud.grohe.com/v1/sso/auth/realms/idm-apigw/protocol/openid-connect/auth?redirect_uri=grohewatersystems%3A%2F%2Fidp2-apigw.cloud.grohe.com%2Fv3%2Fiot%2Foidc%2Ftoken&client_id=iot&response_type=code"
        login_url += "&state=%s&nonce=%s&scope=openid&code_challenge=%s&code_challenge_method=S256" %(state, nonce, challenge)

        # create session
        s = requests.Session()
        s.headers.update({'user-agent' : 'Mozilla/5.0 (Linux; Android 7.1.1; Android SDK built for x86_64 Build/NYC) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Mobile Safari/537.36'})

        # get login form and extra submit url
        form = s.get(login_url, allow_redirects=False)
        matches = re.search('<form onsubmit="login.disabled = true; return true;" action="(.*)" method="post">', form.text)
        submit_url = html.unescape(matches.group(1))

        # then login
        login = s.post(submit_url, {'username': username, 'password': password, 'rememberMe':'on'}, allow_redirects=False)

        # decode keycloak token from cookies and extract user id
        token = jose.jwt.decode(s.cookies['KEYCLOAK_IDENTITY'], '', options={'verify_signature':False})
        self.user_id = token['sub']

        # get login code from response
        response = urllib.parse.urlparse(login.headers['Location'])
        code = urllib.parse.parse_qs(response.query)['code'][0]

        # make a new session for app access
        s = requests.Session()
        s.headers.update({'user-agent' : 'Dalvik/2.1.0 (Linux; U; Android 7.1.1; Android SDK built for x86_64 Build/NYC)'})

        # create request
        request = {'client_id' : 'iot',
                   'code_verifier' : verifier,
                   'redirect_uri' : 'grohewatersystems://idp2-apigw.cloud.grohe.com/v3/iot/oidc/token',
                   'code' : code,
                   'grant_type' : 'authorization_code'}

        # and login with it
        token = s.post("https://idp2-apigw.cloud.grohe.com/v3/iot/oidc/token", request)

        # and make headers with token
        s.headers.update({
            'authorization' :   "Bearer " + token.json()['access_token'],
            'client-id':	'iot',
            'device-type':	'smartphone',
            'device-os-number':	'7.1.1',
            'device-os':	'android',
            'app-version':	'1.0.1',
            'accept-language':	'en_US',
            'content-type':	'application/json; charset=UTF-8',
            'user-agent':	'okhttp/4.2.2'})

        self.session = s

    def read_dashboard(self):
        
        # try and get dashboard
        dashboard = self.session.get("https://idp2-apigw.cloud.grohe.com/v3/iot/dashboard")

        # save stuff presharedkey
        self.dashboard = dashboard.json()
        self.presharedkey = self.dashboard['locations'][0]['rooms'][0]['appliances'][0]['presharedkey']
