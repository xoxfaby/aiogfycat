import asyncio
import aiohttp
import aiofiles
import io
import mimetypes

from time import monotonic


class Client:
    def __init__(self, id, secret, loop=None, session=None, debug=False):
        self._id = id
        self._secret = secret
        self._expiration = 0
        self._loop = loop
        self._session = session or aiohttp.ClientSession(loop=loop)
        self._token = ""
        self._debug = debug

    async def _auth(self):
        data = {
            "client_id": self._id,
            "client_secret": self._secret,
            "grant_type": "client_credentials"
        }
        async with self._session.post('https://api.gfycat.com/v1/oauth/token', json=data) as rt:
            if self._debug:
                print(rt)
            rtjson = await rt.json()
            self._token = f"Bearer {rtjson['access_token']}"
            self._expiration = monotonic() + int(rtjson['expires_in'])

    async def _auth_request(self, *args, **kwargs):
        if monotonic() > self._expiration:
            await self._auth()

        if 'headers' in kwargs:
            kwargs['headers']["Authorization"] = self._token
        else:
            kwargs['headers'] = {"Authorization": self._token}
        for _ in range(5):
            async with self._session.request(*args, **kwargs) as r:
                if 500 <= r.status <= 599:
                    await asyncio.sleep(1)
                elif r.status == 401:
                    await self._auth()
                    kwargs['headers']["Authorization"] = self._token
                elif r.status == 200:
                    return await r.json()
                else:
                    print(await r.json())
                    raise ConnectionError("Something went wrong")

    async def upload(self, file, type=None):
        """Upload a new gfy"""
        headers = {'Content-Type': 'application/json'}
        rjson = await self._auth_request('post', 'https://api.gfycat.com/v1/gfycats', headers=headers)
        if rjson['isOk']:
            if isinstance(file, str):
                async with aiofiles.open(file, mode='rb', loop=self._loop) as f:
                    fgfy = await f.read()
            elif isinstance(file, io.BytesIO):
                if type is None:
                    raise ValueError(
                        "Filelike objects need mimetype specified")
                fgfy = file.read()
            else:
                raise TypeError("file needs to be of type str or io.BytesIO")
            data = aiohttp.FormData()
            data.add_field('key', rjson['gfyname'])
            data.add_field('file',
                           fgfy,
                           filename=rjson['gfyname'],
                           content_type=type or mimetypes.guess_type(file)[0])
            async with self._session.request('post', 'https://filedrop.gfycat.com', data=data) as r2:
                return rjson['gfyname']
        else:
            print(rjson)

    async def status(self, name):
        """Get the status of a gfy"""
        return await self._auth_request('get', f'https://api.gfycat.com/v1/gfycats/fetch/status/{name}')

    async def wait_for(self, name):
        """Wait for a gfy to finish uploading"""
        while True:
            gfystatus = await self.status(name)
            if 'gfyname' in gfystatus:
                return gfystatus['gfyname']
            elif 'errorMessage' in gfystatus:
                return False
            await asyncio.sleep(1)
