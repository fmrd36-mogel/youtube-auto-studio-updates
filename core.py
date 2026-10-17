import os, sqlite3, json, hashlib, datetime, pathlib
BASE=pathlib.Path(__file__).resolve().parent
DB=BASE/'data'/'studio.db'
def conn():
    DB.parent.mkdir(exist_ok=True)
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c
def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY,name TEXT NOT NULL,topic TEXT NOT NULL,channel_id TEXT DEFAULT '',enabled INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,channel_id INTEGER NOT NULL REFERENCES channels(id),title TEXT NOT NULL,description TEXT DEFAULT '',video_path TEXT NOT NULL,license_ok INTEGER DEFAULT 0,approved INTEGER DEFAULT 0,status TEXT DEFAULT 'draft',youtube_id TEXT DEFAULT '',error TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(channel_id,video_path));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,job_id INTEGER,action TEXT,detail TEXT,at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if not c.execute("SELECT COUNT(*) FROM channels").fetchone()[0]:
            c.executemany("INSERT INTO channels(name,topic) VALUES(?,?)",[('채널 1','지역·여행'),('채널 2','정보·상식'),('채널 3','AI 콘텐츠')])
def channels():
    with conn() as c:return [dict(x) for x in c.execute('SELECT * FROM channels ORDER BY id')]
def jobs():
    with conn() as c:return [dict(x) for x in c.execute('SELECT j.*,ch.name channel_name FROM jobs j JOIN channels ch ON ch.id=j.channel_id ORDER BY j.id DESC')]
def add_job(channel_id,title,description,path,license_ok):
    p=pathlib.Path(path).expanduser().resolve()
    if not p.is_file() or p.suffix.lower() not in ('.mp4','.mov','.mkv'):raise ValueError('실제 동영상 파일 경로(.mp4/.mov/.mkv)를 입력하세요.')
    if not license_ok:raise ValueError('라이선스 및 사용 권한 확인이 필요합니다.')
    with conn() as c:
        c.execute('INSERT INTO jobs(channel_id,title,description,video_path,license_ok) VALUES(?,?,?,?,?)',(channel_id,title,description,str(p),int(license_ok)))
def set_approval(job_id,approved):
    with conn() as c:c.execute("UPDATE jobs SET approved=?,status='draft' WHERE id=? AND status IN ('draft','failed')",(int(approved),job_id))
def log(c,job_id,action,detail):
    c.execute('INSERT INTO events(job_id,action,detail) VALUES(?,?,?)',(job_id,action,detail))
def oauth_file(channel_pk):return BASE/'secrets'/f'token_channel_{channel_pk}.json'
def get_service(channel_pk,interactive=False):
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    scope=['https://www.googleapis.com/auth/youtube.upload','https://www.googleapis.com/auth/youtube.readonly']
    token=oauth_file(channel_pk);client=BASE/'secrets'/'client_secret.json'
    creds=Credentials.from_authorized_user_file(str(token),scope) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request());token.write_text(creds.to_json(),encoding='utf-8')
    if not creds or not creds.valid:
        if not interactive:raise RuntimeError('채널 OAuth 연결이 필요합니다.')
        if not client.exists():raise RuntimeError('secrets/client_secret.json 파일이 없습니다.')
        flow=InstalledAppFlow.from_client_secrets_file(str(client),scope)
        creds=flow.run_local_server(port=0,open_browser=True)
        token.write_text(creds.to_json(),encoding='utf-8')
    return build('youtube','v3',credentials=creds,cache_discovery=False)
def connect_channel(pk):
    svc=get_service(pk,True)
    res=svc.channels().list(part='snippet',mine=True).execute()
    items=res.get('items',[])
    if len(items)!=1:raise RuntimeError('인증된 채널을 하나로 식별할 수 없습니다. 계정/채널 선택을 확인하세요.')
    ch=items[0]
    with conn() as c:
        other=c.execute('SELECT id FROM channels WHERE channel_id=? AND id!=?',(ch['id'],pk)).fetchone()
        if other:raise RuntimeError('이 YouTube 채널은 이미 다른 슬롯에 연결되어 있습니다.')
        c.execute('UPDATE channels SET channel_id=? WHERE id=?',(ch['id'],pk))
    return ch['snippet']['title'],ch['id']
def upload(job_id):
    from googleapiclient.http import MediaFileUpload
    with conn() as c:
        job=c.execute('SELECT j.*,ch.channel_id youtube_channel FROM jobs j JOIN channels ch ON ch.id=j.channel_id WHERE j.id=?',(job_id,)).fetchone()
        if not job:raise ValueError('작업 없음')
        if job['status']=='uploaded' or not job['approved'] or not job['license_ok']:raise ValueError('승인 및 라이선스 확인이 필요하거나 이미 업로드된 작업입니다.')
        if not job['youtube_channel']:raise ValueError('채널 OAuth 연결이 필요합니다.')
        p=pathlib.Path(job['video_path'])
        if not p.is_file():raise ValueError('영상 파일을 찾을 수 없습니다.')
        c.execute("UPDATE jobs SET status='uploading',error='' WHERE id=?",(job_id,))
    try:
        svc=get_service(job['channel_id'])
        actual=svc.channels().list(part='id',mine=True).execute().get('items',[])
        if len(actual)!=1 or actual[0]['id']!=job['youtube_channel']:raise RuntimeError('OAuth 토큰의 실제 채널이 등록된 채널과 다릅니다.')
        media=MediaFileUpload(str(p),mimetype='video/*',resumable=True,chunksize=8*1024*1024)
        request=svc.videos().insert(part='snippet,status',body={'snippet':{'title':job['title'],'description':job['description'],'categoryId':'22'},'status':{'privacyStatus':'private','selfDeclaredMadeForKids':False}},media_body=media)
        response=None
        while response is None:
            _,response=request.next_chunk()
        with conn() as c:
            c.execute("UPDATE jobs SET status='uploaded',youtube_id=? WHERE id=?",(response['id'],job_id));log(c,job_id,'uploaded',response['id'])
        return response['id']
    except Exception as e:
        with conn() as c:
            c.execute("UPDATE jobs SET status='failed',error=? WHERE id=?",(str(e)[:1000],job_id));log(c,job_id,'failed',str(e)[:1000])
        raise
def metrics(channel_pk):
    svc=get_service(channel_pk)
    return svc.channels().list(part='statistics,snippet',mine=True).execute().get('items',[])
