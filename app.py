import streamlit as st
import pandas as pd
import core
st.set_page_config(page_title='YouTube Auto Studio',page_icon='🎬',layout='wide')
core.init()
st.title('🎬 YouTube Auto Studio · v2.2.0')
st.caption('3채널 독립 인증 · 작업 대기열 · 권한 확인 · 비공개 업로드 · 기본 통계')
tabs=st.tabs(['대시보드','채널 연결','쇼츠 제작','업로드 작업','작업 기록','소스 안내'])
with tabs[0]:
    ch=core.channels(); js=core.jobs()
    a,b,c=st.columns(3)
    a.metric('채널 슬롯',len(ch));b.metric('대기 작업',sum(j['status']=='draft' for j in js));c.metric('업로드 성공',sum(j['status']=='uploaded' for j in js))
    st.dataframe(pd.DataFrame(ch),hide_index=True,use_container_width=True)
with tabs[1]:
    st.warning('채널별로 Google 로그인/채널 선택을 수행합니다. 인증 파일은 이 컴퓨터의 secrets 폴더에만 보관하세요.')
    for ch in core.channels():
        with st.expander(f"{ch['name']} · {ch['topic']} · {ch['channel_id'] or '미연결'}"):
            with st.form(f'channel_{ch["id"]}'):
                name=st.text_input('표시 이름',ch['name'])
                topic=st.text_input('채널 주제',ch['topic'])
                save=st.form_submit_button('설정 저장')
                if save:
                    with core.conn() as db:db.execute('UPDATE channels SET name=?,topic=? WHERE id=?',(name,topic,ch['id']))
                    st.success('저장 완료')
            if st.button('Google OAuth로 채널 연결/재연결',key=f'auth_{ch["id"]}'):
                try:
                    name,cid=core.connect_channel(ch['id']);st.success(f'연결: {name} ({cid})')
                except Exception as e:st.error(str(e))
            if ch['channel_id'] and st.button('채널 통계 조회',key=f'm_{ch["id"]}'):
                try:
                    for x in core.metrics(ch['id']):st.json({'title':x['snippet']['title'],'statistics':x['statistics']})
                except Exception as e:st.error(str(e))
with tabs[2]:
    st.subheader('쇼츠 자동 렌더링')
    st.caption('무료 오프라인 템플릿으로 대본 초안을 만들고 수정한 뒤 세로형 MP4를 제작합니다. 외부 AI API는 사용하지 않습니다.')
    import maker
    with st.expander('무료 오프라인 대본 초안 생성', expanded=True):
        topic=st.text_input('주제 한 줄',key='offline_topic',placeholder='예: 탄수화물의 역할')
        seconds=st.select_slider('초안 길이',options=[15,30,60],value=30,key='offline_seconds')
        style=st.selectbox('구성 방식',['정보형','질문형','체크리스트형'],key='offline_style')
        if st.button('제목과 대본 초안 만들기',key='offline_generate'):
            try:
                result=maker.offline_generate(topic,seconds,style)
                st.session_state['draft_titles']=result['titles']
                st.session_state['make_title']=result['titles'][0]
                st.session_state['make_script']=result['script']
                st.session_state['make_duration']=result['duration']
                st.info(result['notice'])
            except ValueError as e:st.error(str(e))
        if st.session_state.get('draft_titles'):
            st.caption('제목 후보: '+' / '.join(st.session_state['draft_titles']))
    st.session_state.setdefault('make_title','탄단지 첫 자동 제작 쇼츠')
    st.session_state.setdefault('make_script','오늘의 탄단지 이야기\\n\\n하나씩 차근차근 시작해요\\n\\n다음 영상에서 만나요!')
    st.session_state.setdefault('make_duration',20)
    with st.form('render'):
        make_channel=st.selectbox('제작 대상 채널',[f"{c['id']}: {c['name']}" for c in core.channels()])
        make_title=st.text_input('쇼츠 제목',key='make_title')
        make_script=st.text_area('장면별 대본 (빈 줄로 장면 구분)',value='오늘의 탄단지 이야기\n\n하나씩 차근차근 시작해요\n\n다음 영상에서 만나요!',height=170)
        duration=st.slider('길이 (초)',8,60,key='make_duration')
        use_tts=st.checkbox('Windows 음성으로 내레이션 추가 (설치된 한국어 음성 필요)',value=False)
        render=st.form_submit_button('MP4 자동 제작')
    if render:
        try:
            video=maker.make(make_title,make_script,duration,use_tts)
            st.session_state['last_video']=str(video)
            st.success('제작 완료: '+str(video))
        except Exception as e:st.error(str(e))
    if st.session_state.get('last_video'):
        st.video(st.session_state['last_video'])
        st.code(st.session_state['last_video'])
        st.info('업로드 작업 탭에서 이 경로를 등록하고 사용 권한을 확인한 뒤 승인하세요.')
with tabs[3]:
    st.subheader('완성된 영상 등록')
    with st.form('newjob'):
        options={f"{c['id']}: {c['name']}":c['id'] for c in core.channels()}
        selected=st.selectbox('대상 채널',list(options))
        title=st.text_input('영상 제목',max_chars=100)
        desc=st.text_area('설명 / 출처 표기')
        path=st.text_input('Windows 영상 파일의 전체 경로',placeholder=r'C:\Videos\shorts_001.mp4')
        license_ok=st.checkbox('영상·음원·이미지·초상권 등 사용 권한과 출처를 확인했습니다.')
        submit=st.form_submit_button('작업 대기열에 추가')
        if submit:
            try:
                if not title.strip():raise ValueError('제목을 입력하세요.')
                core.add_job(options[selected],title.strip(),desc,path,license_ok);st.success('작업 등록 완료')
            except Exception as e:st.error(str(e))
    st.divider()
    st.subheader('승인 및 업로드')
    st.info('v2는 안전을 위해 승인 후 비공개 업로드만 지원합니다. 유튜브 스튜디오에서 확인 후 공개하세요.')
    for j in core.jobs():
        if j['status'] not in ('draft','failed'):continue
        with st.expander(f"#{j['id']} · {j['channel_name']} · {j['title']} · {j['status']}"):
            st.write(j['video_path']);st.caption(j['error'])
            approved=st.checkbox('업로드 최종 승인',value=bool(j['approved']),key=f"approve_{j['id']}")
            if st.button('승인 상태 저장',key=f"save_{j['id']}"):
                core.set_approval(j['id'],approved);st.success('저장됨')
            if st.button('비공개 업로드 실행',key=f"up_{j['id']}",disabled=not bool(j['approved'])):
                try:st.success('업로드 ID: '+core.upload(j['id']))
                except Exception as e:st.error(str(e))
with tabs[4]:
    st.dataframe(pd.DataFrame(core.jobs()),hide_index=True,use_container_width=True)
    with core.conn() as db:
        events=[dict(x) for x in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]
    st.dataframe(pd.DataFrame(events),hide_index=True,use_container_width=True)
with tabs[5]:
    st.write('assets 폴더에 첨부된 전주 쇼츠 소스 목록 원본을 보관했습니다.')
    st.warning('엑셀에 적힌 소스 후보가 자동으로 사용 허가를 뜻하지는 않습니다. 실제 자료 페이지와 라이선스를 확인하세요.')
    st.write('v2에서는 입력 대본을 기반으로 Pillow + FFmpeg 세로 쇼츠를 제작합니다. 실제 외부 소스 자동 수집은 하지 않습니다.')
