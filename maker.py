"""Offline, rights-safe slide-based vertical Shorts renderer."""
from pathlib import Path
import subprocess, shutil, uuid, wave, contextlib, re, json
from PIL import Image, ImageDraw, ImageFont
BASE=Path(__file__).resolve().parent
OUT=BASE/'exports'
def font_path():
    candidates=[Path('C:/Windows/Fonts/malgunbd.ttf'),Path('C:/Windows/Fonts/malgun.ttf'),Path('/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    return next((str(x) for x in candidates if x.exists()),None)
def wrap(text,font,draw,width):
    lines=[]
    for para in text.splitlines():
        line=''
        for char in para:
            if draw.textbbox((0,0),line+char,font=font)[2]>width and line:
                lines.append(line);line=char
            else:line+=char
        lines.append(line)
    return lines
def frame(path,heading,body,index,total):
    im=Image.new('RGB',(720,1280),(17,26,44));d=ImageDraw.Draw(im)
    d.rounded_rectangle((45,95,675,1185),radius=34,fill=(33,49,72),outline=(80,160,150),width=3)
    d.rounded_rectangle((82,155,638,170),radius=7,fill=(83,201,176))
    f=font_path();h=ImageFont.truetype(f,58) if f else ImageFont.load_default()
    b=ImageFont.truetype(f,45) if f else ImageFont.load_default()
    s=ImageFont.truetype(f,29) if f else ImageFont.load_default()
    y=310
    for line in wrap(heading,h,d,510)[:4]:
        bb=d.textbbox((0,0),line,font=h);d.text(((720-(bb[2]-bb[0]))/2,y),line,font=h,fill='white');y+=82
    y=max(625,y+45)
    for line in wrap(body,b,d,510)[:7]:
        bb=d.textbbox((0,0),line,font=b);d.text(((720-(bb[2]-bb[0]))/2,y),line,font=b,fill=(171,232,219));y+=65
    d.text((290,1090),f'{index} / {total}',font=s,fill=(190,203,221))
    im.save(path)
def voice(text,path):
    import pyttsx3
    engine=pyttsx3.init()
    # Use Windows SAPI5 installed voice; availability and Korean pronunciation depend on OS voice pack.
    engine.setProperty('rate',165)
    engine.save_to_file(text,str(path));engine.runAndWait()
    if not path.exists() or path.stat().st_size<100:raise RuntimeError('TTS 파일 생성 실패: Windows 음성 팩을 확인하세요.')
def make(title,script,seconds=20,with_voice=False):
    if not shutil.which('ffmpeg'):raise RuntimeError('FFmpeg가 설치되지 않았거나 PATH에 없습니다.')
    if not title.strip() or not script.strip():raise ValueError('제목과 대본이 필요합니다.')
    chunks=[x.strip() for x in re.split(r'\n\s*\n',script.strip()) if x.strip()]
    if len(chunks)>8:raise ValueError('장면은 최대 8개입니다. 빈 줄로 장면을 구분하세요.')
    seconds=int(seconds)
    if not 8<=seconds<=60:raise ValueError('영상 길이는 8~60초입니다.')
    OUT.mkdir(exist_ok=True)
    task=OUT/('render_'+uuid.uuid4().hex[:10]);task.mkdir()
    images=[]
    for i,chunk in enumerate(chunks,1):
        p=task/f'slide_{i:02}.png';frame(p,title,chunk,i,len(chunks));images.append(p)
    duration=seconds/len(images)
    manifest=task/'slides.txt'
    manifest.write_text(''.join("file '"+p.as_posix().replace("'","'\\''")+"'\nduration "+str(duration)+"\n" for p in images)+"file '"+images[-1].as_posix()+"'\n",encoding='utf-8')
    output=OUT/('short_'+uuid.uuid4().hex[:10]+'.mp4')
    cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(manifest)]
    if with_voice:
        audio=task/'voice.wav'
        voice(' '.join(chunks),audio)
        cmd+=['-i',str(audio),'-map','0:v:0','-map','1:a:0','-af','apad','-c:a','aac','-b:a','128k']
    else:
        cmd+=['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=44100','-map','0:v:0','-map','1:a:0','-c:a','aac','-b:a','96k']
    cmd+=['-t',str(seconds),'-vf','fps=24,format=yuv420p','-c:v','libx264','-preset','veryfast','-crf','23','-movflags','+faststart',str(output)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
    if p.returncode or not output.exists():raise RuntimeError('영상 렌더링 실패: '+p.stderr[-1500:])
    (task/'metadata.json').write_text(json.dumps({'title':title,'script':script,'seconds':seconds,'voice':with_voice,'output':str(output)},ensure_ascii=False,indent=2),encoding='utf-8')
    return output


"""무료 오프라인 쇼츠 대본 초안 생성기. 외부 API 및 네트워크 호출 없음."""
import re

def offline_generate(topic, seconds=30, style="정보형"):
    topic=" ".join(str(topic).strip().split())
    if not topic:
        raise ValueError("주제를 입력하세요.")
    if len(topic)>80:
        raise ValueError("주제는 80자 이내로 입력하세요.")
    if seconds not in (15,30,60):
        raise ValueError("15초, 30초, 60초 중 선택하세요.")
    safe=re.sub(r"[\\r\\n\\t]+"," ",topic).strip()
    titles=[f"{safe}, 핵심만 빠르게",f"처음 알아보는 {safe}",f"{safe} 알아보기"]
    if style=="질문형":
        scenes=[f"{safe}, 어디서부터 알아보면 좋을까요?",
                f"먼저 {safe}의 기본 개념을 확인해 보세요.",
                "상황에 따라 달라지는 조건을 살펴보세요.",
                "정확한 정보는 신뢰할 수 있는 자료로 확인하세요."]
    elif style=="체크리스트형":
        scenes=[f"{safe}를 알아볼 때 확인할 세 가지",
                "첫째, 목적과 상황을 먼저 정리하세요.",
                "둘째, 중요한 조건과 기준을 비교하세요.",
                "셋째, 최신 자료와 출처를 확인하세요."]
    else:
        scenes=[f"오늘의 주제는 {safe}입니다.",
                f"주제의 기본 개념부터 살펴보세요: {safe}",
                "핵심 기준을 비교하고 자신의 상황에 적용해 보세요.",
                "자세한 내용은 신뢰할 수 있는 자료로 확인하세요."]
    if seconds==15:scenes=[scenes[0],scenes[1],scenes[-1]]
    if seconds==60:scenes=scenes[:2]+[
        "어떤 조건에서 차이가 나는지 차근차근 정리해 보세요.",
        "사례나 수치를 사용할 때는 원문과 작성일을 확인하세요.",
        "예외 사항이 있는지도 함께 살펴보세요."]+scenes[2:]
    return {"titles":titles,"script":"\n\n".join(scenes),"duration":seconds,
            "notice":"템플릿 기반 초안입니다. 사실·수치·건강 정보는 직접 검증하고 수정하세요."}
