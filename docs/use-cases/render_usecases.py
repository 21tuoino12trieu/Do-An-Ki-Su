"""Xuất ba khối PlantUML trong README.md thành SVG.

Chạy từ thư mục gốc: python docs/use-cases/render_usecases.py
Mã nguồn luôn lấy từ Markdown, không sửa tay các file .puml đã trích xuất.
"""
import argparse
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
VERSION="1.2026.9"
DEFAULT_JAR=Path.home()/f".codex/tmp/usecase-plantuml/plantuml-{VERSION}.jar"


def layout_actor_diagram(root, block):
    """Giữ hình PlantUML; định tuyến riêng từng liên kết, không dùng đường trục chung."""
    ns = 'http://www.w3.org/2000/svg'
    def tag(name):
        return f'{{{ns}}}{name}'
    def add(parent, name, attrs, text=None):
        child = ET.SubElement(parent, tag(name), {k: str(v) for k, v in attrs.items()})
        child.text = text
        return child
    entities = {g.get('id'): g for g in root.iter() if g.get('class') == 'entity'}
    actors = [g for g in entities.values() if g.find(tag('ellipse')) is not None and g.find(tag('path')) is not None]
    if len(actors) != 1:
        raise ValueError('Moi so do phai co dung mot tac nhan')
    actor = actors[0]
    cases = {}
    for node in entities.values():
        first = node.find(tag('text'))
        code = first.text if first is not None else ''
        if re.fullmatch(r'UC\d+', code or ''):
            cases[code] = node
    order = [code for code in ('UC10','UC01','UC02','UC11','UC04','UC05','UC08') if code in cases]
    ys = {code: 150 + 120 * index + (60 if code in ('UC04','UC05','UC08') else 0)
          for index, code in enumerate(order)}
    ys['UC03'] = ys.get('UC02', ys['UC11'])
    if 'UC09' in cases:
        ys['UC09'] = ys['UC08']
    height = max(ys.values()) + 130
    result = ET.Element(tag('svg'), {
        'width': '1320', 'height': str(height), 'viewBox': f'0 0 1320 {height}',
        'role': 'img', 'aria-label': 'So do Use Case theo tac nhan',
    })
    add(result, 'rect', {'x': 350,'y': 70,'width': 950,'height': height-115,
                       'fill': 'white','stroke': '#9AA8B7','stroke-width': 1.2})
    add(result, 'text', {'x': 825,'y': 101,'text-anchor': 'middle','font-family': 'Arial',
                       'font-size': 18,'font-weight': 'bold','fill': '#253746'},
        'Hệ thống kho tri thức doanh nghiệp')
    centers = {}
    for code, node in cases.items():
        ellipse = node.find(tag('ellipse'))
        x = 1030 if code in ('UC03','UC09') else 550
        y = ys[code]
        cx, cy, rx, ry = (float(ellipse.get(k)) for k in ('cx','cy','rx','ry'))
        node.set('transform',f'translate({x-cx:.3f},{y-cy:.3f})')
        centers[code] = (x,y,rx,ry)
    actor_y = (min(ys[c] for c in order)+max(ys[c] for c in order))/2
    head = actor.find(tag('ellipse'))
    # Nhãn tác nhân nằm ngoài hành lang các đường tham gia.
    dx, dy = 110-float(head.get('cx')), actor_y-16-float(head.get('cy'))
    actor.set('transform',f'translate({dx:.3f},{dy:.3f})')
    actor_id = actor.get('id')
    alias_codes = {node.get('data-qualified-name').split('.')[-1]: code for code,node in cases.items()}
    links = [g for g in root.iter() if g.get('class') == 'link']
    relation_layer = add(result,'g',{'id':'relations'})
    main_above = sorted([c for c in order if ys[c] < actor_y],key=lambda c:ys[c])
    main_below = sorted([c for c in order if ys[c] >= actor_y],key=lambda c:-ys[c])
    rails = {code:220+18*index for side in (main_above,main_below) for index,code in enumerate(side)}
    for old_link in links:
        first, second = (entities[old_link.get(k)] for k in ('data-entity-1','data-entity-2'))
        if actor in (first, second):
            node = second if first is actor else first
            code = next(c for c,g in cases.items() if g is node)
            x,y,rx,ry = centers[code]
            route = f'M 130 {actor_y} H {rails[code]} V {y} H {x-rx}'
            link = add(relation_layer,'g',{'class':'association','data-actor':actor_id,'data-usecase':code})
            add(link,'path',{'d':route,'fill':'none','stroke':'#526171','stroke-width':1.2,'stroke-linejoin':'round'})
            endpoint = x-rx
            add(link,'path',{'d':f'M {endpoint-10} {y-5} L {endpoint} {y} L {endpoint-10} {y+5}',
                             'fill':'none','stroke':'#526171','stroke-width':1.2})
    # Mỗi quan hệ extend giữ đường và nhãn riêng trong khoảng giữa hai cột.
    for source_alias,target_alias in re.findall(
        r'(\w+) \.\.> (\w+) : <<extend>>\s*$',block,re.M):
        source_code,target_code = alias_codes[source_alias],alias_codes[target_alias]
        point = {'UC01':'EP01','UC02':'EP02','UC11':'EP11','UC08':'EP08'}[target_code]
        sx,sy,srx,sry = centers[source_code]
        tx,ty,trx,try_ = centers[target_code]
        # Cắt từng đường thẳng theo biên hai elip. Mỗi quan hệ có điểm ra
        # riêng trên UC mở rộng, không chồng đoạn hoặc ghép thành nhánh.
        dx, dy = tx-sx, ty-sy
        source_scale = 1 / math.sqrt((dx/srx)**2 + (dy/sry)**2)
        target_scale = 1 / math.sqrt((dx/trx)**2 + (dy/try_)**2)
        start_x, start_y = sx+dx*source_scale, sy+dy*source_scale
        end_x, end_y = tx-dx*target_scale, ty-dy*target_scale
        path = f'M {start_x:.3f} {start_y:.3f} L {end_x:.3f} {end_y:.3f}'
        link = add(relation_layer,'g',{'class':'extend','data-source':source_code,'data-target':target_code,'data-extension-point':point})
        add(link,'path',{'d':path,'fill':'none','stroke':'#253746','stroke-width':1.2,'stroke-dasharray':'6 5'})
        length = math.hypot(end_x-start_x, end_y-start_y)
        ux, uy = (end_x-start_x)/length, (end_y-start_y)/length
        left_x, left_y = end_x-10*ux-5*uy, end_y-10*uy+5*ux
        right_x, right_y = end_x-10*ux+5*uy, end_y-10*uy-5*ux
        add(link,'path',{'d':f'M {left_x:.3f} {left_y:.3f} L {end_x:.3f} {end_y:.3f} L {right_x:.3f} {right_y:.3f}',
                         'fill':'none','stroke':'#253746','stroke-width':1.2})
        add(link,'text',{'x':(start_x+end_x)/2,'y':(start_y+end_y)/2-12,'text-anchor':'middle',
                         'font-family':'Arial','font-size':15,'fill':'#253746'},
            '«extend»')
    result.append(actor)
    for code in cases:
        result.append(cases[code])
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar",type=Path,default=DEFAULT_JAR)
    parser.add_argument("--smetana",action="store_true",help="Dùng bộ bố trí Java khi không có Graphviz")
    args=parser.parse_args()
    if not args.jar.is_file():
        raise SystemExit("Chưa có PlantUML jar; xem hướng dẫn tải trong README của thư mục này.")
    source=(HERE/"README.md").read_text(encoding="utf-8")
    blocks=re.findall(r"```plantuml\s*\n(.*?)```",source,re.S)
    if len(blocks)!=3:raise SystemExit("Cần đúng ba sơ đồ use case trong Markdown.")
    out=HERE/"diagrams"
    out.mkdir(parents=True,exist_ok=True)
    for block in blocks:
        name=re.search(r"^@startuml\s+([a-z0-9-]+)\s*$",block,re.M)
        if not name or "@enduml" not in block:raise SystemExit("Tên hoặc khối PlantUML không hợp lệ.")
        (out/(name[1]+".puml")).write_text(block.strip()+"\n",encoding="utf-8")
    java=shutil.which("java")
    if java and (shutil.which("dot") or args.smetana):
        command=[java,"-Djava.awt.headless=true","-jar",str(args.jar.resolve()),"-charset","UTF-8","-tsvg",str(out/"*.puml")]
    else:
        docker=shutil.which("docker")
        if not docker:
            docker_path=Path.home()/"AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe"
            if docker_path.is_file():docker=str(docker_path)
        if not docker:raise SystemExit("Cần Java hoặc Docker Desktop đang chạy.")
        renderer_image="doan-uml-renderer:1.0"
        exists=subprocess.run([docker,"image","inspect",renderer_image],capture_output=True).returncode==0
        if not exists:
            subprocess.run([docker,"build","-t",renderer_image,str(HERE/"renderer")],check=True,timeout=240)
        font_args=[]
        java_font=[]
        if os.name=="nt":
            # Dùng cùng font Arial ở bước đo chữ Java và khi xem SVG trên Windows.
            font_dir=args.jar.resolve().parent/"fonts"
            font_dir.mkdir(exist_ok=True)
            system_fonts=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"
            for filename in ("arial.ttf","arialbd.ttf","ariali.ttf","arialbi.ttf"):
                if (system_fonts/filename).is_file():shutil.copyfile(system_fonts/filename,font_dir/filename)
            font_args=["-v",f"{font_dir}:/fonts:ro"]
            java_font=["-Dsun.java2d.fontpath=/fonts"]
        # Chỉ dùng Java trong image sẵn có; không khởi động Kafka broker.
        command=[docker,"run","--rm","--network","none","--entrypoint","java",
                 "-v",f"{args.jar.resolve()}:/tools/plantuml.jar:ro",
                 "-v",f"{out.resolve()}:/work",*font_args,
                 renderer_image,"-Djava.awt.headless=true",*java_font,"-jar","/tools/plantuml.jar",
                 "-charset","UTF-8","-tsvg","/work/*.puml"]
    if args.smetana:
        command.append("-Playout=smetana")
    subprocess.run(command,check=True,timeout=120)
    for block in blocks:
        name=re.search(r"^@startuml\s+([a-z0-9-]+)\s*$",block,re.M)[1]
        svg=out/(name+".svg")
        text=svg.read_text(encoding="utf-8")
        if "Syntax Error" in text:raise SystemExit("PlantUML báo lỗi trong "+name)
        # CSS background ở thẻ svg không được mọi trình raster hóa hỗ trợ.
        # Thêm nền trắng thật để chữ/tác nhân vẫn rõ trên Markdown dark mode.
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        root=ET.fromstring(text)
        root=layout_actor_diagram(root,block)
        root.insert(0,ET.Element("{http://www.w3.org/2000/svg}rect",{"width":"100%","height":"100%","fill":"#FFFFFF"}))
        ET.ElementTree(root).write(svg,encoding="utf-8",xml_declaration=False)
        print("OK:",svg.relative_to(HERE))


if __name__=="__main__":main()
