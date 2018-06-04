import json
import requests
import re
import datetime
import os
import time
from aws_requests_auth.aws_auth import AWSRequestsAuth
from websocket import WebSocketApp, WebSocket

_first_re = re.compile("(.)([A-Z][a-z]+)")
_cap_re = re.compile("([a-z0-9])([A-Z])")
def _to_snake(name):
    s1 = _first_re.sub(r"\1_\2", name)
    return _cap_re.sub(r"\1_\2", s1).lower()


class HQUserLeaderboard:
    def __init__(self, **kwargs):
        self.total_cents = kwargs.get("total_cents")
        self.total = kwargs.get("total")
        self.unclaimed = kwargs.get("unclaimed")
        for p in ("alltime", "weekly"):
            for v in ("wins", "total", "rank"):
                try:
                    setattr(self, f"{p}_{v}", kwargs.get(p).get(v))
                except:
                    pass


class HQUserInfo:
    def __init__(self, **kwargs):
        self.user_id = kwargs.get("user_id")
        self.username = kwargs.get("username")
        self.avatar_url = kwargs.get("avatar_url")
        self.created_timestamp = kwargs.get("created_timestamp")
        self.broadcasts = kwargs.get("broadcasts")  # unused
        self.featured = kwargs.get("featured")  # unused
        self.referral_url = kwargs.get("referral_url")  # property?
        self.high_score = kwargs.get("high_score")
        self.games_played = kwargs.get("games_played")
        self.win_count = kwargs.get("win_count") # different than leaderboard.alltime_wins cuz i dont know, i think this is the accurate one
        self.blocked = kwargs.get("blocked")
        self.blocks_me = kwargs.get("blocks_me")
        try:
            x = kwargs.get("leaderboard")
            if isinstance(x, dict):
                kwargs2 = {}
                for k, v in x.items():
                    kwargs2[_to_snake(k)] = v
                self.leaderboard = HQUserLeaderboard(**kwargs2)
            elif isinstance(x, HQUserLeaderboard):
                self.leaderboard = x
        except Exception as e:
            raise e


class HQMeInfo(HQUserInfo):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.friend_ids = kwargs.get("friend_ids")
        self.stk = kwargs.get("stk")  # unused?
        self.voip = kwargs.get("voip")
        self.device_tokens = kwargs.get("device_tokens")
        self.preferences = kwargs.get("preferences")
        self.lives = kwargs.get("lives")
        self.phone_number = kwargs.get("phone_number")
        self.referred = kwargs.get("referred")


class HQClient:
    def __init__(self, auth_token: str, client: str="Android/1.6.2", user_agent: str="okhttp/3.8.0", caching=False, cache_time=15):
        self.auth_token = auth_token
        self.headers = {
            "x-hq-client": client,
            "user-agent": user_agent
        }
        self.ws = None
        self.ws_on_message = lambda x: pass
        self.ws_on_error = lambda x: pass
        self.ws_on_close = lambda x: pass
        self.caching = caching # probably could just decorate but im too lazy
        self.cache_time = cache_time
        self._cache = {}

    @property
    def default_headers(self) -> dict:
        return {
            "x-hq-client": self.headers["x-hq-client"],
            "authorization": "Bearer " + self.auth_token,
            "user-agent": self.headers["user-agent"]
        }

    def valid_auth(self) -> bool:
        return "active" in self.schedule()

    def make_it_rain(self) -> bool:
        return requests.post("https://api-quiz.hype.space/easter-eggs/makeItRain", headers=self.default_headers).status_code == 200

    def search_users(self, user: str) -> list:
        if self.caching:
            if "search_users" in self._cache:
                if user in self._cache["search_users"]:
                    if (time.time() - self._cache["search_users"][user]["last_update"]) < self.cache_time:
                        return self._cache["search_users"][user]["value"]
        response = requests.get("https://api-quiz.hype.space/users?q=" + user, headers=self.default_headers)
        ret = []
        for x in response.json()["data"]:
            kwargs = {}
            for k, v in x.items():
                kwargs[_to_snake(k)] = v
            ret.append(HQUserInfo(**kwargs))
        if self.caching:
            if "search_users" not in self._cache:
                self._cache["search_users"] = {}
            self._cache["search_users"][user] = {
                "value": ret,
                "last_update": time.time()
            }
        return ret

    def user_info(self, something) -> HQUserInfo:
        if isinstance(something, str):
            search = self.search_users(something)
            if not search:
                raise Exception("User not found")
            else:
                user_id = search[0].user_id
        elif isinstance(something, int):
            user_id = something
        if self.caching:
            if "user_info" in self._cache:
                if user_id in self._cache["user_info"]:
                    if (time.time() - self._cache["user_info"][user_id]["last_update"]) < self.cache_time:
                        return self._cache["user_info"][user_id]["value"]
        response = requests.get("https://api-quiz.hype.space/users/me", headers=self.default_headers)
        kwargs = {}
        for k, v in response.json().items():
            kwargs[_to_snake(k)] = v
        ret = HQUserInfo(**kwargs)
        if self.caching:
            if "user_info" not in self._cache:
                self._cache["user_info"] = {}
            self._cache["user_info"][user_id] = {
                "value": ret,
                "last_update": time.time()
            }
        return ret

    def me(self) -> HQMeInfo:
        response = requests.get("https://api-quiz.hype.space/users/me", headers=self.default_headers)
        kwargs = {}
        for k, v in response.json().items():
            kwargs[_to_snake(k)] = v
            print(_to_snake(k), v)
        return HQMeInfo(**kwargs)

    def cashout(self, paypal: str) -> bool:
        return requests.post("https://api-quiz.hype.space/users/me/payouts", headers=self.default_headers, data={"email": paypal}).status_code == 200

    def schedule(self) -> dict:
        return requests.get("https://api-quiz.hype.space/shows/now?type=hq", headers=self.default_headers).json()

    def aws_credentials(self) -> dict:
        return requests.get("https://api-quiz.hype.space/credentials/s3", headers=self.default_headers).json()

    def delete_avatar(self) -> str:
        return requests.delete("https://api-quiz.hype.space/users/me/avatarUrl", headers=self.default_headers).json()["avatarUrl"]

    def add_friend(self, something) -> dict:
        if isinstance(something, int):
            user_id = int(something)
        elif isinstance(something, str):
            search = self.search_users(something)
            if not search:
                raise Exception("user not found")
            user_id = search[0].user_id
        elif isinstance(something, HQUserInfo):
            user_id = something.user_id
        response = requests.post(f"https://api-quiz.hype.space/friends/{user_id}/requests", headers=self.default_headers).json()
        return {
            "requested_user": self.user_info(response["requestedUser"]["userId"]),
            "requesting_user": self.user_info(response["requestingUser"]["userId"]),
            "status": response["status"]
        }

    def friend_status(self, something):
        if isinstance(something, int):
            user_id = int(something)
        elif isinstance(something, str):
            search = self.search_users(something)
            if not search:
                raise Exception("user not found")
            user_id = search[0].user_id
        return requests.get(f"https://api-quiz.hype.space/friends/{user_id}/status", headers=self.default_headers).json()["status"]

    def accept_friend(self, something) -> dict:
        if isinstance(something, int):
            user_id = int(something)
        elif isinstance(something, str):
            search = self.search_users(something)
            if not search:
                raise Exception("user not found")
            user_id = search[0].user_id
        response = requests.put(f"https://api-quiz.hype.space/friends/{user_id}/status", headers=self.default_headers, data={
                "status": "ACCEPTED"
            }).json()
        return {
            "requested_user": self.user_info(response["requestedUser"]["userId"]),
            "requesting_user": self.user_info(response["requestingUser"]["userId"]),
            "status": response["status"],
            "accepted_timestamp": response["created"]  # milliseconds(?)
        }

    def remove_friend(self, something) -> bool:
        if isinstance(something, int):
            user_id = int(something)
        elif isinstance(something, str):
            search = self.search_users(something)
            if not search:
                raise Exception("user not found")
            user_id = search[0].user_id
        return requests.delete(f"https://api-quiz.hype.space/friends/{user_id}", headers=self.default_headers).json()["result"]

    def connect(self, socket=None) -> bool:
        schedule = self.schedule()
        m = isinstance(schedule["broadcast"], dict)
        print(m)
        if socket is not None or m:
            if socket is None:
                self.ws = WebSocketApp(schedule["broadcast"]["socketUrl"].replace("https", "wss"))
            else:
                self.ws = WebSocketApp(socket,
                                       on_message=self.ws_on_message,
                                       on_error=self.ws_on_error,
                                       on_close=self.ws_on_close, header=["Authorization: " + self.auth_token])
            self.wst = __import__("threading").Thread(target=self.ws.run_forever)
            self.wst.daemon = True
            self.wst.start()
            return True
        else:
            return False

    def subscribe(self) -> bool:
        if self.ws is None:
            return False
        x = self.schedule()
        self.ws.send(json.dumps({
            "type": "subscribe",
            "broadcastId": x["broadcast"]["broadcastId"]
        }))
        return True

    def answer(self, question_id: int, answer_id: int, broadcast_id=None):
        if self.ws is None:
            return False

        if broadcast_id is None:
            x = self.schedule()
            broadcast_id = x["broadcast"]["broadcastId"]

        self.ws.send(json.dumps({
            "type": "answer",
            "questionId": question_id,
            "broadcastId": broadcast_id,
            "answerId": answer_id
        }))
        return True

    def disconnect(self):
        self.ws.close()
        self.ws = None


def verify(phone: str) -> str:
    try:
        return requests.post("https://api-quiz.hype.space/verifications", data={
            "method": "sms",
            "phone": phone
        }).json()["verificationId"]
    except KeyError:
        raise Exception("invalid phone number")


def submit_code(verification_id: str, code: str) -> bool:
    return requests.post("https://api-quiz.hype.space/verifications/" + verification_id, data={"code": code}).status_code != 404


def username_available(username: str) -> bool:
    return not bool(requests.post("https://api-quiz.hype.space/usernames/available", data={"username": username}).json())


def create_user(username: str, verification_id: str, referral: str="", region: str="US"):
    return requests.post("https://api-quiz.hype.space/users", data={
        "country": "US",
        "language": "en",
        "referringUsername": referral,
        "username": username,
        "verificationId": verification_id
    }).json()
